                                                                               
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import MatchSession
from editorial import EditorialDesk
from journal import EventJournal
from locales import event_display, translated_packet
from pipeline import EventContractError, MetricProjector
from simulation import GeneratorSettings


class ExperienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = MatchSession(GeneratorSettings(2), wall_clock=lambda:0)
        cls.live.pump(300)

    def test_all_required_event_kinds_arrive_numbered_with_metadata_and_frames(self):
        events = self.live.pipeline.events
        self.assertTrue({'pass_completed','shot','possession_change','pressure'} <= {e['kind'] for e in events})
        self.assertEqual([e['id'] for e in events], list(range(1,len(events)+1)))
        meta = self.live.match.metadata()
        self.assertEqual([len(t['lineup']) for t in meta['teams']], [11,11])
        self.assertEqual(len({p['id'] for t in meta['teams'] for p in t['lineup']}), 22)
        for event in events:
            self.assertEqual(event['match_id'],meta['match_id'])
            self.assertEqual(len(event['frame']),22)
            self.assertLessEqual(event['time'],self.live.confirmed_frame['clock'])
            self.assertEqual(event['time'],round(event['tick']*.05,2))

    def test_tackle_is_received_on_its_exact_model_tick(self):
                                                                         
                                                         
        live=MatchSession(GeneratorSettings(42),wall_clock=lambda:0)
        m=live.match
        for i,p in enumerate(m.players):
            p.x,p.y=10+(i%11)*7,8 if i<11 else 60
        m.owner=6;m.possession_team=0
        m.players[6].x,m.players[6].y=30,34
        m.players[15].x,m.players[15].y=30.5,34
        m.ball=[30.65,34];m.control_time=1;m.think_in=10
                                                                                         
        from generator_checks import GeneratorChecks
        live.generator_checks=GeneratorChecks(m)
        with patch.object(m.rng,'random',return_value=0):live.pump(.05)
        event=next(e for e in live.pipeline.events if e['kind']=='tackle')
        self.assertEqual(event['time'],.05)
        self.assertEqual(event['actors'],[{'team':0,'number':7},{'team':1,'number':5}])
        self.assertEqual(live.pipeline.metrics.possession_team,1)
        change=next(e for e in live.pipeline.events if e['kind']=='possession_change')
        self.assertEqual(change['time'],event['time'])

    def test_pressure_events_describe_pressing_side_and_actual_opponents(self):
        for e in self.live.pipeline.events:
            if e['kind'] != 'pressure': continue
            team=e['team']; counts=e['details']['counts']
            self.assertEqual(e['details']['pressing_team'],team)
            self.assertEqual(counts[team],len(e['actors']))
            self.assertEqual(counts[1-team],0)
            for actor in e['actors']:
                frame=next(p for p in e['frame'] if p['team']==actor['team'] and p['number']==actor['number'])
                self.assertLessEqual(math.dist((frame['x'],frame['y']),e['ball']),5.001)

    def test_auxiliary_events_do_not_invent_passes_shots_or_scores(self):
        source=self.live.match
        self.assertEqual(self.live.pipeline.metrics.completed,source.completed)
        self.assertEqual(self.live.pipeline.metrics.shots,source.shots)
        self.assertEqual(self.live.pipeline.metrics.score,source.score)

    def test_window_metrics_reconstruct_from_only_their_source_interval(self):
        windows=self.live.pipeline.context.window()
        self.assertTrue(windows['comparable'])
        for window in (windows['current'],windows['previous']):
            events=[e for e in self.live.pipeline.events if window['start']<e['time']<=window['end']]
            for t in (0,1):
                self.assertEqual(window['passes'][t],sum(e['kind']=='pass_started' and e['team']==t for e in events))
                self.assertEqual(window['shots'][t],sum(e['kind']=='shot' and e['team']==t for e in events))
                forward=sum(max(0,(e['details']['end'][0]-e['details']['origin'][0])*e['details']['direction']) for e in events if e['kind']=='pass_completed' and e['team']==t)
                self.assertEqual(window['forward_m'][t],round(forward,1))
                self.assertAlmostEqual(sum(window['zones'][t]),window['pressure_seconds'][t],delta=.5)
                self.assertLessEqual(window['pressure_seconds'][t],window['end']-window['start']+.1)
            self.assertEqual(sum(window['possession']),100)
            self.assertTrue(set(window['evidence_ids']) <= {e['id'] for e in events})

    def test_early_context_never_claims_a_complete_minute_comparison(self):
        live=MatchSession(wall_clock=lambda:0);live.pump(30)
        experience=live.snapshot()['experience']
        self.assertFalse(experience['context']['comparable'])
        self.assertIn('two complete',experience['context_text'])
        self.assertEqual(experience['context']['previous']['passes'],[0,0])

    def test_player_stats_count_roles_rather_than_every_source_mention(self):
        focus=self.live.pipeline.context.focus({'team':0,'number':10})
        events=self.live.pipeline.events
        actor={'team':0,'number':10}
        self.assertEqual(focus['statistics']['passes'],sum(e['kind']=='pass_completed' and e['actors'][0]==actor for e in events))
        self.assertEqual(focus['statistics']['received'],sum(e['kind']=='pass_completed' and e['actors'][-1]==actor for e in events))
        self.assertEqual(focus['statistics']['shots'],sum(e['kind']=='shot' and e['actors'][0]==actor for e in events))
        self.assertTrue(all(actor in e['actors'] for e in focus['events']))

    def test_counterattack_explains_regain_to_shot_and_keeps_geometry(self):
        moment=next(m for m in self.live.insights.moments.values() if m.facts.get('counterattack'))
        response=self.live.snapshot(audience='analyst',language='en',selected=moment.id)['experience']
        selected=response['selected'];evidence=selected['evidence']
        regain=next(e for e in evidence if e['kind'] in ('tackle','interception'))
        shot=next(e for e in evidence if e['kind']=='shot')
        self.assertIn(f"{shot['time']-regain['time']:.1f}",selected['why'])
        self.assertEqual([e['id'] for e in evidence],moment.evidence_ids)
        self.assertEqual(sum(e['kind']=='pass_completed' for e in evidence),selected['chain_metrics']['passes'])
        self.assertTrue(all(len(e['frame'])==22 for e in evidence))
        for e in evidence:
            if e['kind']=='pass_completed':self.assertTrue({'origin','end','direction'} <= e['details'].keys())

    def test_three_modes_languages_share_facts_without_advancing_match(self):
        before=self.live.match.event_digest.hexdigest()
        packets=[]
        for mode in ('fan','analyst','player'):
            for lang in ('en','cs','de'):
                data=self.live.snapshot(audience=mode,language=lang,player={'team':0,'number':10})
                exp=data['experience'];packets.append(exp['selected'])
                self.assertEqual((exp['audience'],exp['language']),(mode,lang))
                self.assertEqual(exp['stages']['received'],exp['stages']['processed'])
                self.assertTrue(exp['focus'])
                if lang in ('en','cs','de'):
                    for field in ('title','what','why','change','simple'):
                        self.assertFalse(re.search(r'[\u0400-\u04ff]',exp['selected'][field]),field)
                    self.assertFalse(re.search(r'[\u0400-\u04ff]',data['pipeline']['receipts'][-1]['explanation']))
        self.assertEqual(self.live.match.event_digest.hexdigest(),before)
        self.assertEqual(len({p['fact_fingerprint'] for p in packets}),1)
        self.assertTrue(all(p['facts']==packets[0]['facts'] for p in packets))

    def test_all_actual_episode_captions_and_evidence_are_localized(self):
        for moment in self.live.insights.moments.values():
            for language in ('en','cs'):
                packet=translated_packet(self.live.insights.moment_data(moment),language)
                material=self.live.content.render(packet,language=language)
                text=material['formats']['broadcast']['text']
                self.assertLessEqual(len(text),140);self.assertLessEqual(text.count('\n'),1)
                for event in packet['evidence']:
                    self.assertFalse(re.search(r'[\u0400-\u04ff]',event['title']+event['text']))
                    self.assertEqual(event['source_text'],self.live.pipeline.events[event['id']-1]['text'])

    def test_editor_review_is_bound_to_language(self):
        desk=EditorialDesk();moment=next(iter(self.live.insights.moments.values()))
        copy=desk.state(moment,self.live.insights,'en')['copy']
        reviewed=desk.act(self.live.insights,moment.id,moment.revision,'review',copy,'en')
        self.assertTrue(reviewed['receipt'])
        self.assertEqual(desk.state(moment,self.live.insights,'cs')['status'],'draft')
        with self.assertRaises(ValueError):desk.act(self.live.insights,moment.id,moment.revision,'select',None,'cs')
        desk.act(self.live.insights,moment.id,moment.revision,'select',copy,'en')
        self.assertIsNotNone(desk.snapshot(self.live.insights,'en')['active'])
        self.assertIsNone(desk.snapshot(self.live.insights,'de')['active'])

    def test_same_revision_omits_experience_but_new_tick_updates_context(self):
        live=MatchSession(wall_clock=lambda:0);live.pump(10)
        first=live.snapshot()
        same=live.snapshot(run_id=live.run_id,experience_revision=first['experience_revision'])
        self.assertNotIn('experience',same)
        live.pump(10.05)
        updated=live.snapshot(run_id=live.run_id,experience_revision=first['experience_revision'])
        self.assertIn('experience',updated)
        self.assertEqual(updated['experience']['context']['current']['end'],10.05)

    def test_saved_event_survives_reopen_and_new_replay_run(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'events.sqlite3';journal=EventJournal(path)
            live=MatchSession(GeneratorSettings(2),wall_clock=lambda:0,journal=journal)
            live.pump(10);key=live.run_key;source=deepcopy(live.pipeline.events[-1]);meta=live.match.metadata()
            live.restart();self.assertNotEqual(key,live.run_key);journal.close()
            reopened=EventJournal(path)
            record=reopened.find(key,source['id'])
            self.assertEqual(record['event'],source);self.assertEqual(record['metadata'],meta)
            self.assertEqual(len(reopened.runs()),2)
            self.assertIsNone(reopened.find(key,999999))
            reopened.append(key,[source])
            bad=deepcopy(source);bad['text']='conflict'
            with self.assertRaises(ValueError):reopened.append(key,[bad])
            self.assertEqual(reopened.find(key,source['id'])['event'],source)
            reopened.close()

    def test_archive_failure_preserves_frame_context_and_story(self):
        with tempfile.TemporaryDirectory() as folder:
            journal=EventJournal(Path(folder)/'events.sqlite3')
            live=MatchSession(GeneratorSettings(2),wall_clock=lambda:0,journal=journal)
            live.pump(10);before=live.snapshot()
            with patch.object(journal,'append',side_effect=sqlite3.OperationalError('disk unavailable')):live.pump(11)
            after=live.snapshot()
            for key in ('clock','events','event_count','score','event_hash','experience','insights'):
                self.assertEqual(before[key],after[key],key)
            self.assertEqual(after['pipeline']['status'],'degraded');journal.close()

    def test_failed_replay_start_preserves_previous_match(self):
        with tempfile.TemporaryDirectory() as folder:
            journal=EventJournal(Path(folder)/'events.sqlite3')
            live=MatchSession(wall_clock=lambda:0,journal=journal);live.pump(10)
            before=live.snapshot();key=live.run_key
            with patch.object(journal,'start',side_effect=sqlite3.OperationalError('disk unavailable')):
                with self.assertRaises(sqlite3.Error):live.restart(2)
            self.assertEqual(live.snapshot(),before)
            self.assertEqual(live.run_key,key);journal.close()

    def test_bad_new_pressure_contract_is_rejected_without_partial_batch(self):
        live=MatchSession(wall_clock=lambda:0);before=live.snapshot()
        advance=live.match.advance
        def bad_advance():
            advance();live.match.event('Bad pressure','Bad pressure',kind='pressure',details={'counts':[5,0],'radius_m':5,'pressing_team':0})
        with patch.object(live.match,'advance',side_effect=bad_advance):live.pump(.05)
        self.assertEqual(live.snapshot()['events'],before['events'])
        self.assertEqual(live.snapshot()['experience'],before['experience'])
        self.assertEqual(live.pipeline.metrics.last_id,before['event_count'])


if __name__ == '__main__':unittest.main()
