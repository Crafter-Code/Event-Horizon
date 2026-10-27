import copy
import hashlib
import json
import math
import struct
import unittest

from raster import render,decode_png,encode_png,BACKGROUND,chunk,WIDTH,HEIGHT
from vision import VideoRecognizer
from vision_evaluation import RecognitionEvaluation
from pass_quality import assess
from camera import SyntheticCamera
from simulation import Match
from pipeline import MatchPipeline
from match_report import MatchReport
from app import MatchSession


def lineup():
    players=[{'team':t,'number':n,'x':8+n*7,'y':8+t*50} for t in (0,1) for n in range(1,12)]
    for p in players:
        if (p['team'],p['number'])==(0,10):p.update(x=40,y=34)
        if (p['team'],p['number'])==(0,6):p.update(x=58,y=34)
    return players


def feed(model,players,points,offset=0,in_play=True):
    for i,point in enumerate(points,1):
        model.observe(render(players,point),round(offset+i*.1,2),in_play=in_play)


class PixelTests(unittest.TestCase):
    def test_camera_codec_has_only_pixels_and_round_trips(self):
        png=encode_png(BACKGROUND);self.assertEqual(decode_png(png),BACKGROUND)
        kinds=[];p=8
        while p<len(png):
            n=struct.unpack('!I',png[p:p+4])[0];kinds.append(png[p+4:p+8]);p+=n+12
        self.assertEqual(kinds,[b'IHDR',b'IDAT',b'IEND'])

    def test_invalid_or_annotated_camera_frames_are_rejected(self):
        png=encode_png(BACKGROUND)
        for bad in (png[:-8],png[:90]+b'bad'+png[93:],png[:33]+chunk(b'tEXt',b'owner=10')+png[33:],png+b'owner=10'):
            with self.subTest(size=len(bad)),self.assertRaises(ValueError):decode_png(bad)

    def test_identifies_names_and_metric_coordinates_from_pixels(self):
        m=VideoRecognizer();p=lineup();frame=m.observe(render(p,(45,34)),.1)
        self.assertEqual(len(frame['players']),22)
        for player in frame['players']:
            gt=next(x for x in p if x['team']==player['team'] and x['number']==player['number'])
            self.assertLess(math.dist((player['x'],player['y']),(gt['x'],gt['y'])),.15)
        self.assertEqual(next(x['name'] for x in frame['players'] if x['team']==0 and x['number']==10),'Max Rowan')

    def test_occlusion_and_missing_ball_are_not_filled_from_truth(self):
        p=lineup();p[-1].update(x=40,y=34)
        m=VideoRecognizer();frame=m.observe(render(p,(45,34)),.1)
        self.assertLess(len(frame['players']),22)
        blank=m.observe(encode_png(BACKGROUND),.2)
        self.assertEqual(blank['players'],[]);self.assertIsNone(blank['ball'])

    def test_tracking_uses_image_movement_and_known_time(self):
        m=VideoRecognizer();p=lineup();m.observe(render(p,(45,34)),.1)
        p[0]['x']+=.6
        result=m.observe(render(p,(46.6,34)),.2)
        moved=next(a for a in result['players'] if a['team']==0 and a['number']==1)
        self.assertAlmostEqual(moved['speed_mps'],6,delta=.8)
        self.assertAlmostEqual(moved['distance_m'],.6,delta=.15)
        self.assertAlmostEqual(result['ball']['speed_mps'],16,delta=1.5)

    def test_teleport_and_stoppage_do_not_create_distance_or_shot(self):
        m=VideoRecognizer();p=lineup();feed(m,p,[(40.65,34)]*3)
        p[0]['x']+=30
        frame=m.observe(render(p,(90,34)),.4,in_play=False)
        self.assertEqual(next(a['distance_m'] for a in frame['players'] if a['team']==0 and a['number']==1),0)
        self.assertFalse(any(e['kind']=='shot' for e in m.events))

    def test_duplicate_and_future_nonfinite_clock_rejected_before_mutation(self):
        m=VideoRecognizer();png=render(lineup(),(45,34));m.observe(png,.1)
        for t in (.1,0,float('nan')):
            with self.assertRaises(ValueError):m.observe(png,t)
        self.assertEqual(m.frame_id,1)

    def test_pass_recognition_quality_accuracy_and_speed_have_pixel_sources(self):
        m=VideoRecognizer();p=lineup();feed(m,p,[(40.65,34)]*3+[(40.65+1.6*i,34) for i in range(1,11)]+[(58.65,34)]*4)
        done=next(e for e in m.events if e['kind']=='pass_completed');facts=done['facts'];measure=facts['speed_measurement']
        self.assertTrue(facts['success']);self.assertGreater(facts['quality']['distance_m'],17)
        self.assertAlmostEqual(measure['distance_m']/measure['interval_s'],measure['speed_mps'],delta=.03)
        self.assertAlmostEqual(measure['speed_mps'],16,delta=2)
        self.assertEqual(m.snapshot()['teams'][0]['accuracy_pct'],100)
        self.assertEqual(m.snapshot()['player_statistics']['0:10']['passes'],1)
        self.assertTrue(all(e['source']=='pixels' and len(e['frame_ids'])==2 for e in m.events))

    def test_shot_is_not_mistaken_for_first_mixed_speed_pass(self):
        m=VideoRecognizer();p=lineup();next(x for x in p if (x['team'],x['number'])==(0,10)).update(x=90,y=34)
        feed(m,p,[(90.65,34)]*3+[(92.25,34),(94.75,34),(97.25,34),(99.75,34),(102.25,34),(104.75,34)])
        m.observe(render(p,(107.25,34)),1.,in_play=False)
        shots=[e for e in m.events if e['kind']=='shot'];self.assertEqual(len(shots),1)
        self.assertFalse(any(e['kind']=='pass_started' for e in m.events))
        measurement=shots[0]['facts']['measurement']
        self.assertAlmostEqual(measurement['distance_m']/measurement['interval_s'],shots[0]['facts']['speed_mps'],delta=.03)
        self.assertTrue(any(e['kind']=='goal' for e in m.events))

    def test_fast_ball_offset_rotation_during_dribbling_is_not_a_release(self):
        m=VideoRecognizer();p=lineup();feed(m,p,[(40.65,34)]*3)
        for i in range(1,15):m.observe(render(p,((40.65 if i%2 else 39.35),34)),round(.3+i*.05,2))
        self.assertFalse(any(e['kind'] in ('pass_started','shot') for e in m.events))
        self.assertEqual(m.snapshot()['teams'][0]['attempts'],0)

    def test_tackle_and_possession_change_are_extracted(self):
        p=lineup();m=VideoRecognizer();feed(m,p,[(40.65,34)]*3)
        next(x for x in p if (x['team'],x['number'])==(1,10)).update(x=40.7,y=34)
        feed(m,p,[(40.65,34)]*3,offset=.3)
        self.assertTrue(any(e['kind']=='tackle' for e in m.events))
        self.assertTrue(any(e['kind']=='possession_change' for e in m.events))

    def test_difficulty_increases_with_distance_forward_direction_and_pressure(self):
        low=assess((0,0),(0,5),[],1);far=assess((0,0),(0,35),[],1)
        forward=assess((0,0),(35,0),[],1);pressured=assess((0,0),(35,0),[(1,0),(2,0),(3,0)],1)
        self.assertLess(low['difficulty'],far['difficulty']);self.assertLess(far['difficulty'],forward['difficulty']);self.assertLess(forward['difficulty'],pressured['difficulty'])
        self.assertEqual(pressured['pressure_count'],3);self.assertIn('not a probability',pressured['method'])

    def test_ground_truth_checker_cannot_change_predictions(self):
        p=lineup();png=render(p,(40.65,34));a=VideoRecognizer();b=VideoRecognizer();e=RecognitionEvaluation()
        for i in range(1,5):
            left=a.observe(png,i*.1);right=b.observe(png,i*.1)
            false_truth=[{**x,'x':0,'y':0} for x in p]
            e.compare(right,false_truth,(0,0),[],b.events)
            self.assertEqual(left,right)
        self.assertEqual(a.snapshot(),b.snapshot())

    def test_accuracy_uses_misses_and_false_positives_not_only_successes(self):
        e=RecognitionEvaluation();obs={'players':[],'ball':None,'time':3.,'in_play':True}
        gt={'id':1,'kind':'shot','time':.2,'actors':[{'team':0,'number':10}]}
        pred={'id':'cv-1','kind':'pass_started','time':.2,'actors':[{'team':0,'number':10}]}
        e.compare(obs,lineup(),(40,34),[gt],[pred]);scores=e.snapshot()['event_scores']
        self.assertEqual(scores['shot']['fn'],1);self.assertEqual(scores['pass_started']['fp'],1)
        self.assertEqual(scores['shot']['recall'],0);self.assertIsNone(scores['goal']['recall'])

    def test_verification_examples_link_prediction_frames_without_changing_scores(self):
        evaluation=RecognitionEvaluation()
        observation={'players':[],'ball':None,'time':3.,'in_play':True}
        truth=[{'id':41,'kind':'shot','time':.2,'actors':[{'team':0,'number':10}]}]
        prediction=[{'id':'cv-3','kind':'shot','time':.25,'actors':[{'team':0,'number':10}],
                     'frame_ids':[4,5]}]
        evaluation.compare(observation,lineup(),(40,34),truth,prediction)
        result=evaluation.snapshot()
        self.assertEqual(result['event_scores']['shot']['tp'],1)
        self.assertEqual(result['examples'][-1]['truth_id'],41)
        self.assertEqual(result['examples'][-1]['prediction_id'],'cv-3')
        self.assertEqual(result['examples'][-1]['frame_ids'],[4,5])
        self.assertEqual(result['examples'][-1]['delta_s'],.05)


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.match=Match();cls.pipeline=MatchPipeline(cls.match);cls.reports=MatchReport();cls.half=None
        while not cls.match.finished:
            m=cls.match;stopped=bool(m.restart);period=m.period;m.advance();cls.pipeline.advance(m,not stopped and m.period==period and not m.finished)
            if m.clock==2700:cls.half=cls.reports.snapshot(cls.pipeline)['halves'][0]
        cls.final=cls.reports.snapshot(cls.pipeline)

    def test_halftime_report_stays_fixed_after_second_half(self):
        self.assertEqual(self.half,self.final['halves'][0]);self.assertTrue(self.half['facts']['complete'])
        self.assertEqual(self.half['facts']['end'],2700)

    def test_full_report_reconciles_with_independent_event_metrics(self):
        facts=self.final['full_time']['facts'];metrics=self.pipeline.metrics
        self.assertEqual(facts['goals'],metrics.score);self.assertEqual(facts['passes'],metrics.completed)
        self.assertEqual(facts['attempts'],metrics.attempts);self.assertEqual(facts['shots'],metrics.shots)

    def test_summaries_link_only_existing_episodes_and_available_sources(self):
        for report in self.final['halves']+[self.final['full_time']]:
            for episode in report['episodes']:
                self.assertIn(episode['id'],self.pipeline.insights.moments)
                self.assertTrue(all(self.pipeline.events[i-1]['time']<=report['facts']['end'] for i in episode['evidence_ids']))

    def test_pressure_and_rhythm_episodes_include_comparison_and_actions(self):
        changes=[m for m in self.pipeline.insights.moments.values() if m.facts.get('context_change')]
        self.assertTrue(any(m.facts['context_change']=='pressure' for m in changes))
        self.assertTrue(any(m.facts['context_change']=='rhythm' for m in changes))
        for m in changes:
            self.assertTrue(self.pipeline.insights.verified(m));self.assertIn('losses',m.facts['comparison']['current'])
            self.assertTrue(m.evidence_ids);self.assertIsNone(m.facts['ai_interpretation'])

    def test_player_accuracy_tackles_and_team_context_use_actual_actor(self):
        p={'team':0,'number':10};report=self.reports.snapshot(self.pipeline,p)['full_time']['player'];events=self.pipeline.events
        count=sum(e['kind']=='tackle' and e['actors'][-1]==p for e in events if e['actors'])
        self.assertEqual(report['statistics']['tackles'],count)
        self.assertEqual(report['statistics']['shots'],sum(e['kind']=='shot' and e['actors'][0]==p for e in events if e['actors']))
        self.assertTrue(report['period_comparison']['comparable'])

    def test_languages_preserve_facts_and_episode_ids(self):
        reports=[self.reports.snapshot(self.pipeline,language=l)['full_time'] for l in ('en','cs','de')]
        self.assertEqual(len({r['fact_fingerprint'] for r in reports}),1)
        self.assertEqual([[e['id'] for e in r['episodes']] for r in reports][0],[[e['id'] for e in r['episodes']] for r in reports][2])

    def test_report_does_not_predict_half_or_full_results_early(self):
        m=Match();p=MatchPipeline(m);r=MatchReport().snapshot(p)
        self.assertEqual(r['halves'],[]);self.assertIsNone(r['full_time'])

    def test_ai_interpretation_cannot_overwrite_observed_facts(self):
        live=MatchSession(wall_clock=lambda:0);live.pump(130)
        m=next(m for m in live.insights.moments.values() if m.complete)
        before=(m.what,m.why,m.change);draft=dict(what=m.what,why=m.why,change=m.change,evidence_ids=m.evidence_ids[:])
        self.assertTrue(live.apply_narrative((live.run_id,m.id,m.revision),draft))
        self.assertEqual((m.what,m.why,m.change),before);self.assertEqual(m.interpretation['why'],draft['why'])

    def test_video_branch_does_not_change_deterministic_match(self):
        a=Match();b=Match();camera=SyntheticCamera()
        for _ in range(300):a.advance();b.advance();camera.advance(b)
        self.assertEqual(a.event_digest.hexdigest(),b.event_digest.hexdigest())
        self.assertEqual(a.snapshot(),b.snapshot())

    def test_recent_goal_opens_the_attack_even_for_opponent_preferences(self):
        first_goal=next(e for e in self.pipeline.events if e['kind']=='goal')
        live=MatchSession(wall_clock=lambda:0);live.pump(first_goal['time'])
        opposite=1-first_goal['team']
        data=live.snapshot(team=opposite,player={'team':opposite,'number':2})
        chosen=data['experience']['selected']
        self.assertEqual(chosen['kind'],'goal');self.assertEqual(chosen['evidence_ids'][-1],first_goal['id'])
        self.assertTrue(any(e['kind']=='pass_completed' for e in chosen['evidence']))
        prior=next(m for m in live.insights.moments.values() if m.id!=chosen['id'])
        manual=live.snapshot(selected=prior.id)['experience']['selected']
        self.assertEqual(manual['id'],prior.id)


if __name__=='__main__':unittest.main()
