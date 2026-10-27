                                                                                   
import asyncio
from base64 import b64decode
from copy import deepcopy
from contextlib import closing
from unittest.mock import patch
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from app import MatchSession
from demonstration_store import DemoWriter,DemoReader,summary_key
from full_match_acceptance import ai_failure_audit,language_audit,overlay_audit,replay_audit,summaries_audit
from match_report import MatchReport
from raster import render
from simulation import GeneratorSettings
from vision_evaluation import RecognitionEvaluation


class FinalizationTests(unittest.TestCase):
    def test_last_unmatured_event_is_counted_without_extra_frames(self):
        evaluator=RecognitionEvaluation()
        truth={'id':1,'kind':'shot','time':9.9,'team':0,'actors':[{'team':0,'number':9}]}
        pred={'id':'cv-1','kind':'shot','time':10,'actors':[{'team':0,'number':9}],'facts':{}}
        evaluator.truth.append(truth);evaluator.pred.append(pred);evaluator.frames=200
        self.assertEqual(evaluator.snapshot()['pending_truth'],1)
        evaluator.finalize();report=evaluator.snapshot()
        self.assertEqual(report['event_scores']['shot']['tp'],1)
        self.assertEqual(report['pending_truth'],0);self.assertEqual(report['pending_predictions'],0)
        self.assertEqual(report['frames'],200)
        evaluator.finalize();self.assertEqual(evaluator.snapshot(),report)

    def test_unmatched_end_events_become_misses_and_extras(self):
        evaluator=RecognitionEvaluation()
        evaluator.truth.append({'id':1,'kind':'shot','time':10,'team':0,'actors':[{'team':0,'number':9}]})
        evaluator.pred.append({'id':'cv-1','kind':'shot','time':10,'actors':[{'team':1,'number':9}],'facts':{}})
        evaluator.finalize();score=evaluator.snapshot()['event_scores']['shot']
        self.assertEqual((score['tp'],score['fp'],score['fn']),(0,1,1))

    def test_possession_change_must_match_the_correct_team(self):
        e=RecognitionEvaluation();e.truth.append({'id':1,'kind':'possession_change','time':1,'team':0,'actors':[]})
        e.pred.append({'id':'cv-1','kind':'possession_change','time':1,'actors':[],'facts':{'to_team':1}})
        e.finalize();self.assertEqual(e.scores['possession_change'],{'tp':0,'fp':1,'fn':1})


class DemonstrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory();cls.path=Path(cls.folder.name)/'demo.sqlite3'
        cls.live=MatchSession(GeneratorSettings(42,'counterattack'),wall_clock=lambda:0,vision_enabled=True)
        writer=DemoWriter(cls.path,cls.live);writer.capture(cls.live)
        cls.png={0:sha256(cls.live.camera.png).hexdigest()}
        for tick in range(1,301):
            cls.live.pump(tick*.05);writer.capture(cls.live)
            if tick%20==0:cls.png[tick]=sha256(cls.live.camera.png).hexdigest()
        writer.finalize(cls.live,{'match_seconds':15},{});cls.reader=DemoReader(cls.path)

    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def test_every_sampled_replay_frame_equals_the_original_camera_png(self):
        for tick,fingerprint in self.png.items():
            result=self.reader.state(tick*.05)
            self.assertEqual(sha256(b64decode(result['frame_png'])).hexdigest(),fingerprint)
            self.assertEqual(result['clock'],tick*.05)

    def test_no_future_rounding_source_or_outcome(self):
        early=self.reader.state(3.5999,selected='moment-8')
        self.assertLessEqual(early['clock'],3.5999)
        self.assertIsNone(early['episode'])
        with closing(sqlite3.connect(self.path)) as db:
            when=db.execute("SELECT min(available) FROM materials WHERE id='moment-8'").fetchone()[0]
        before=self.reader.state(when-.05,selected='moment-8')
        after=self.reader.state(when,selected='moment-8')
        self.assertIsNone(before['episode']);self.assertIsNotNone(after['episode'])
        if not after['episode']['complete']:self.assertNotIn('saved',after['episode']['what'])
        self.assertTrue(all(e['time']<=after['clock'] for e in after['episode']['evidence']))

    def test_selected_chain_has_exact_raw_evidence_and_positions(self):
        data=self.reader.state(10,selected='moment-8',audience='analyst',language='en')
        episode=data['episode'];self.assertTrue(episode['verified'])
        self.assertEqual(episode['scene_event']['id'],episode['evidence_ids'][-1])
        self.assertEqual(len(episode['scene_event']['frame']),22)
        for source in episode['sources']:
            event=self.reader.event(source['id'],'en')['event']
            self.assertIn(event,self.live.pipeline.events)
        self.assertIsNone(data['summary'])

    def test_fan_analyst_and_focus_share_facts_and_source_references(self):
        packets=[self.reader.state(10,l,a,0,{'team':0,'number':10},'moment-8') for l in ('en','cs','de') for a in ('fan','analyst','player')]
        reference=packets[0]['episode']
        for data in packets:
            self.assertEqual(data['episode']['facts'],reference['facts'])
            self.assertEqual(data['episode']['evidence_ids'],reference['evidence_ids'])
            self.assertEqual(data['episode']['card']['fact_fingerprint'],reference['card']['fact_fingerprint'])
        self.assertNotEqual(packets[0]['episode']['what'],packets[1]['episode']['what'])
        self.assertEqual(packets[0]['episode']['card']['metrics'],[])
        self.assertTrue(packets[1]['episode']['card']['metrics'])

    def test_nine_lenses_use_one_available_revision_without_future_leak(self):
        with closing(sqlite3.connect(self.path)) as db:
            available=db.execute("SELECT min(available) FROM materials WHERE id='moment-8'").fetchone()[0]
        before=self.reader.lenses('moment-8',available-.05)
        self.assertEqual(before['status'],'waiting')
        self.assertEqual(before['views'],[])
        proof=self.reader.lenses('moment-8',available)
        self.assertEqual(proof['status'],'passed',proof['checks'])
        self.assertEqual(len(proof['views']),9)
        self.assertEqual({v['mode'] for v in proof['views']},{'fan','analyst','player'})
        self.assertEqual({v['language'] for v in proof['views']},{'en','cs','de'})
        self.assertEqual({v['facts_sha256'] for v in proof['views']},{proof['facts_sha256']})
        self.assertTrue(proof['source_event_ids'])
        with self.assertRaises(KeyError):self.reader.lenses('moment-unknown',available)

    def test_invalid_time_and_metrics_are_rejected(self):
        for at in (-1,15.1,float('nan'),True):
            with self.assertRaises(ValueError):self.reader.state(at)
        with self.assertRaises(ValueError):self.reader.state(1,metrics=['unknown'])
        with self.assertRaises(KeyError):self.reader.event(99999)

    def test_whole_pipeline_audits_do_not_accept_changed_replay(self):
        self.assertEqual(replay_audit(self.live,15,lambda *_:None)['status'],'passed')
        self.live.confirmed_frame['score'][0]+=1
        try:self.assertEqual(replay_audit(self.live,15,lambda *_:None)['status'],'failed')
        finally:self.live.confirmed_frame['score'][0]-=1

    def test_injected_ai_failures_keep_every_factual_fingerprint(self):
        report=ai_failure_audit(self.live)
        self.assertEqual(report['status'],'passed')
        self.assertEqual(len(report['cases']),5)
        self.assertTrue(all(c['metrics_and_facts_preserved'] for c in report['cases']))

    def test_delayed_ai_does_not_block_match_processing(self):
        live=MatchSession(GeneratorSettings(42,'counterattack'),wall_clock=lambda:0);live.pump(15)
        moment=next(m for m in live.insights.moments.values() if m.complete)
        packet=live.insights.moment_data(moment)
        async def execute():
            started=asyncio.Event();release=asyncio.Event()
            class Slow:
                async def compose(self,_):
                    started.set();await release.wait();raise TimeoutError()
            live.narrator=Slow()
            task=asyncio.create_task(live.process_narrative_job((live.run_id,moment.id,moment.revision),packet))
            await started.wait()
            live.pump(15.1)
            self.assertFalse(task.done())
            self.assertEqual(live.pipeline.tick,302)
            before=deepcopy(live.confirmed_frame)
            release.set();await task
            self.assertEqual(live.confirmed_frame,before)
        asyncio.run(execute())

    def test_http_replay_parameters_sources_and_archive_identity(self):
        from http.server import ThreadingHTTPServer
        import threading,os
        from urllib.request import urlopen
        from urllib.error import HTTPError
        from app import Handler
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with patch.dict(os.environ,{'EVENT_HORIZON_DEMO_ARCHIVE':str(self.path)}):
                with urlopen(base+'/demo/manifest') as response:manifest=json.load(response)
                with urlopen(base+'/demo/state?at=10&language=cs&audience=player&player=0:10') as response:state=json.load(response)
                self.assertEqual(state['clock'],10)
                self.assertEqual(state['run_key'],manifest['run_key'])
                for path,code in (('/demo/state?at=NaN',400),('/demo/state?at=5&at=6',400),
                                  ('/demo/state?language=xx',400),('/demo/state?player=2:99',400),
                                  ('/demo/state?run_key=wrong',409),('/demo/event?id=99999',404)):
                    with self.assertRaises(HTTPError) as failure:urlopen(base+path)
                    self.assertEqual(failure.exception.code,code,path)
                    failure.exception.close()
        finally:server.shutdown();server.server_close();worker.join(2)

    def test_overlay_boundaries_and_language_sources_are_verified(self):
        self.assertEqual(overlay_audit(self.live)['status'],'passed')
        self.assertEqual(language_audit(self.live)['status'],'passed')

    def test_summary_profiles_have_one_fact_set_and_real_focus_statistics(self):
        report,summaries=summaries_audit(self.live,False)
        self.assertEqual(report['status'],'passed');self.assertEqual(report['profiles'],621)
        a=summaries[summary_key('en','player',0,'0:10')]
        b=summaries[summary_key('cs','analyst',1,'1:1')]
        self.assertEqual(a['facts'],b['facts'])
        self.assertIn('Max Rowan',a['text'])
        self.assertEqual(a['player']['statistics']['passes'],1)
        self.assertEqual(a['generated_from'],'calculated_facts')

    def test_period_tackles_belong_to_the_winner_not_the_dispossessed_player(self):
        live=MatchSession(GeneratorSettings(42,'high_press'),wall_clock=lambda:0);live.pump(20)
        tackles=[e for e in live.pipeline.events if e['kind']=='tackle']
        self.assertTrue(tackles)
        for event in tackles:
            actor=event['actors'][-1]
            report=MatchReport.player_periods(live.pipeline.events,actor,20)
            expected=sum(e['actors'][-1]==actor for e in tackles)
            self.assertEqual(report['current']['tackles'],expected)

    def test_own_team_changes_summary_priority_without_changing_facts(self):
        reports=MatchReport()
        red=reports.build(self.live.pipeline,0,15,False,None,'en','fan',1)
        blue=reports.build(self.live.pipeline,0,15,False,None,'en','fan',0)
        self.assertEqual(red['fact_fingerprint'],blue['fact_fingerprint'])
        self.assertNotEqual(red['text'],blue['text'])
        self.assertIn('Red',red['text']);self.assertIn('Blue',blue['text'])


if __name__=='__main__':unittest.main()
