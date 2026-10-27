                                                                               
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_STORED

from app import MatchSession
from dataset import export_dataset, verify_dataset, duration_ticks
from generator_checks import GeneratorChecks, GeneratorConsistencyError
from scenarios import catalogue, load_catalog, profile, validate_profile, ScenarioExpectations
from simulation import Match, GeneratorSettings


def play(name, seed=42, seconds=30):
    m=Match(GeneratorSettings(seed,name));checks=GeneratorChecks(m)
    while m.clock<seconds:m.advance();checks.validate(m)
    return m,checks


class ScenarioTests(unittest.TestCase):
    def test_original_match_sequence_is_preserved(self):
        match,_=play('open_play')
        facts=[{k:v for k,v in e.items() if k not in ('title','text')} for e in match.events]
        digest=hashlib.sha256(json.dumps(facts,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                                                                                     
        self.assertEqual(digest,'066e9556adf36f11f7cbc4b8a080e4db992df13648f11e97451dd2e3ac43550d')

    def test_high_press_is_physical_and_creates_a_real_turnover(self):
        m,checks=play('high_press')
        self.assertEqual(checks.snapshot(m.clock)['scenario']['status'],'passed')
        pressure=next(e for e in m.events if e['kind']=='pressure')
        self.assertGreaterEqual(pressure['details']['counts'][1],2)
        tackle=next(e for e in m.events if e['kind']=='tackle')
        player=next(p for p in tackle['frame'] if p['team']==tackle['actors'][-1]['team'] and p['number']==tackle['actors'][-1]['number'])
        self.assertLessEqual(__import__('math').dist((player['x'],player['y']),tackle['ball']),1.251)
        self.assertEqual(tackle['score'],[0,0])

    def test_counterattack_uses_actual_received_passes_before_shot(self):
        for seed in (0,1,7,42,4294967295):
            with self.subTest(seed=seed):
                m,c=play('counterattack',seed,15)
                result=c.snapshot(m.clock)['scenario']
                self.assertEqual(result['status'],'passed')
                events=[m.events[t['evidence']['event_id']-1] for t in result['expectations']]
                self.assertEqual([e['kind'] for e in events],['pass_completed','pass_completed','shot'])
                self.assertTrue(all(a['time']<b['time'] for a,b in zip(events,events[1:])))
                self.assertTrue(all(e['details'].get('direction',1)==1 for e in events))

    def test_same_settings_same_metadata_events_and_hash(self):
        for name in ('high_press','counterattack'):
            a,_=play(name);b,_=play(name)
            self.assertEqual(a.metadata(),b.metadata());self.assertEqual(a.events,b.events)
            self.assertEqual(a.event_digest.hexdigest(),b.event_digest.hexdigest())
            self.assertIn('scenario_sha256',a.settings.as_dict())
        a,_=play('high_press',0);b,_=play('high_press',1)
        self.assertNotEqual(a.event_digest.hexdigest(),b.event_digest.hexdigest())

    def test_expectation_cannot_confirm_future_or_fabricate_events(self):
        m=Match(GeneratorSettings(42,'counterattack'));ex=ScenarioExpectations(m.scenario)
        ex.consume(m.events);self.assertEqual(ex.snapshot(0)['status'],'pending')
        failed=ex.snapshot(15)
        self.assertEqual(failed['status'],'failed');self.assertEqual(len(m.events),1)
        self.assertTrue(all(t['evidence'] is None for t in failed['expectations']))

    def test_live_scenario_passport_separates_generated_evidence_from_pixel_verdict(self):
        live=MatchSession(GeneratorSettings(42,'counterattack'),wall_clock=lambda:0,vision_enabled=True)
        live.pump(15)
        passport=live.snapshot()['generator']['scenario']
        self.assertEqual(passport['status'],'passed')
        self.assertEqual([item['recognition']['status'] for item in passport['expectations']],['matched']*3)
        for item in passport['expectations']:
            self.assertEqual(item['recognition']['truth_id'],item['evidence']['event_id'])
            self.assertTrue(item['recognition']['frame_ids'])
            self.assertGreater(item['recognition']['prediction_time'],0)
        self.assertEqual(len(live.camera.evaluation.verdicts),3)
        local=MatchSession(GeneratorSettings(42,'counterattack'),wall_clock=lambda:0,vision_enabled=False)
        local.pump(15)
        self.assertEqual(local.match.events,live.match.events)
        self.assertNotIn('recognition',local.snapshot()['generator']['scenario']['expectations'][0])

    def test_catalogue_can_extend_without_editing_simulator_or_analyzer(self):
        data=profile('counterattack');data.pop('sha256');data['id']='wide_counter';data['version']=2
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'wide.json').write_text(json.dumps(data))
            loaded=load_catalog(tmp)
        self.assertIn('wide_counter',loaded);self.assertEqual(loaded['wide_counter']['version'],2)
        self.assertNotEqual(loaded['wide_counter']['sha256'],profile('counterattack')['sha256'])

    def test_invalid_profile_is_rejected(self):
        original=profile('counterattack');original.pop('sha256')
        for broken in ('outside','duplicate','opponent','unknown','clock','owner'):
            d=deepcopy(original)
            if broken=='outside':d['initial']['players'][0]['x']=106
            elif broken=='duplicate':d['initial']['players'][1]['id']='0:1'
            elif broken=='opponent':d['sequence'][0]['receiver']='1:10'
            elif broken=='unknown':d['policy']['execute']='code'
            elif broken=='clock':d['expectations'][0]['by_s']=float('nan')
            else:d['initial']['owner']='0:1'
            with self.subTest(broken=broken),self.assertRaises(ValueError):validate_profile(d)

    def test_settings_validation_and_atomic_restart(self):
        live=MatchSession(GeneratorSettings(42,'counterattack'),wall_clock=lambda:0)
        live.pump(10);before=live.snapshot()
        for name in ('unknown','../counterattack',None,[],True):
            with self.subTest(name=name),self.assertRaises(ValueError):live.restart(scenario=name if name is not None else '')
            self.assertEqual(live.snapshot()['event_hash'],before['event_hash'])
        live.restart();live.pump(10)
        self.assertEqual(live.snapshot()['event_hash'],before['event_hash'])
        live.restart(seed=1);self.assertEqual(live.match.settings.scenario,'counterattack')
        live.restart(scenario='high_press');self.assertEqual(live.match.settings.seed,1)


class GeneratorCheckTests(unittest.TestCase):
    def test_legal_goal_checks_crossing_point_not_later_outside_position(self):
        m=Match()
        for p in m.players:p.x,p.y=10,8 if p.team==0 else 60
        m.owner=9;m.players[9].x,m.players[9].y=104.15,37.5
        m.ball=[104.8,37.5]
        self.assertTrue(m.start_shot())
                                                                           
        m.flight['target']=(105.5,37.9)
        checks=GeneratorChecks(m);m.advance();checks.validate(m)
        self.assertEqual(m.score,[1,0]);self.assertGreater(m.ball[1],37.66)
        self.assertEqual(checks.snapshot(m.clock)['status'],'passed')

    def test_rejects_score_possession_boundaries_speed_and_clock_corruption(self):
        for corruption in ('score','owner','position','teleport','ball','clock','pressure','event_score'):
            m=Match();checks=GeneratorChecks(m);m.advance()
            if corruption=='score':m.score=[1,0]
            elif corruption=='owner':m.possession_team=1
            elif corruption=='position':m.players[0].x=-1
            elif corruption=='teleport':m.players[0].x+=2
            elif corruption=='ball':m.ball=[106,34]
            elif corruption=='clock':m.clock+=.01
            elif corruption=='pressure':m.event('bad','bad',kind='pressure',event_team=1,details={'counts':[0,9],'radius_m':5})
            else:m.event('bad','bad',kind='ball_recovered',actors=(m.owner,));m.events[-1]['score']=[1,0]
            with self.subTest(corruption=corruption),self.assertRaises(GeneratorConsistencyError):checks.validate(m)
            self.assertEqual(checks.snapshot(0)['status'],'failed')

    def test_live_error_stops_publication_and_replay_restores_checks(self):
        live=MatchSession(wall_clock=lambda:0);live.pump(2);before=live.snapshot();advance=live.match.advance
        def corrupt():advance();live.match.score[0]+=1
        with patch.object(live.match,'advance',side_effect=corrupt):live.pump(3)
        after=live.snapshot()
        self.assertEqual(after['clock'],before['clock']);self.assertEqual(after['score'],before['score'])
        self.assertEqual(after['generator']['status'],'failed')
        live.restart();live.pump(3);self.assertEqual(live.snapshot()['generator']['status'],'passed')


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clips={}
        for name in ('high_press','counterattack'):
            out=io.BytesIO();manifest=export_dataset(out,GeneratorSettings(42,name),15)
            cls.clips[name]=(out.getvalue(),manifest)

    def test_full_video_labels_metadata_evidence_and_predictions_are_exported(self):
        covered=set()
        for name,(data,manifest) in self.clips.items():
            with self.subTest(name=name),ZipFile(io.BytesIO(data)) as z:
                self.assertEqual(manifest['frame_count'],301)
                self.assertEqual(manifest['expectations']['status'],'passed')
                frames=[json.loads(line) for line in z.read('annotations.jsonl').splitlines()]
                self.assertEqual(len(frames),301);self.assertEqual(frames[0]['time_s'],0)
                self.assertEqual(frames[-1]['time_s'],15)
                self.assertTrue(all(len(f['players'])==22 for f in frames))
                events=[json.loads(line) for line in z.read('events.jsonl').splitlines()]
                covered.update(e['kind'] for e in events)
                self.assertEqual([e['id'] for e in events],list(range(1,len(events)+1)))
                for e in manifest['expectations']['expectations']:
                    self.assertEqual(events[e['evidence']['event_id']-1]['kind'],e['kind'])
                predictions=[json.loads(line) for line in z.read('predictions.jsonl').splitlines()]
                self.assertTrue(predictions);self.assertTrue(all(str(e['id']).startswith('cv-') for e in predictions))
                self.assertFalse(manifest['labels_used_as_model_input'])
                self.assertEqual(json.loads(z.read('validation.json'))['violations'],0)
                meta=json.loads(z.read('metadata.json'))
                self.assertEqual(meta['pitch'],{'length_m':105,'width_m':68})
                self.assertEqual(sum(len(t['lineup']) for t in meta['teams']),22)
                self.assertEqual(len(manifest['files']),312)
                result=json.loads(z.read('scenario_results.json'))
                self.assertTrue(all(t['recognition']['status']=='matched' for t in result['expectations']))
        self.assertTrue({'pass_started','shot','tackle','possession_change','pressure'}<=covered)

    def test_byte_identical_export_and_detects_tampering(self):
        out=io.BytesIO();export_dataset(out,GeneratorSettings(42,'counterattack'),15)
        self.assertEqual(out.getvalue(),self.clips['counterattack'][0])
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp,'clip.zip');p.write_bytes(out.getvalue());self.assertTrue(verify_dataset(p)['verified'])
            with ZipFile(io.BytesIO(out.getvalue())) as original,ZipFile(p,'w',compression=ZIP_STORED) as broken:
                for name in original.namelist():broken.writestr(name,b'corrupt' if name=='frames/000001.png' else original.read(name))
            with self.assertRaisesRegex(ValueError,'Checksum mismatch'):verify_dataset(p)

    def test_duration_rejects_nan_infinity_and_fractional_ticks(self):
        for seconds in (0,-1,5401,float('nan'),float('inf'),True,'15',.03):
            with self.subTest(seconds=seconds),self.assertRaises(ValueError):duration_ticks(seconds)
