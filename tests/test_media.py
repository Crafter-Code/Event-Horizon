                                                                            
from copy import deepcopy
from pathlib import Path
import json
import unittest

from demonstration_store import DemoReader
from media import read_scene, audit_episode, compose

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/'data/full-match.sqlite3'


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader=DemoReader(ARCHIVE)
        cls.manifest=cls.reader.manifest()
        cls.goal=next(e for e in cls.manifest['episodes'] if e['kind']=='goal')
        cls.state=cls.reader.state(cls.goal['available_at'],selected=cls.goal['id'])
        cls.episode=cls.state['episode']
        cls.sources={n:cls.reader.event(n)['event'] for n in cls.episode['evidence_ids']}
        for e in list(cls.sources.values()):
            if e['kind']=='pass_completed':
                key=e['details']['pass_start_id'];cls.sources[key]=cls.reader.event(key)['event']

    def test_three_scenes_share_facts_and_clock(self):
        scene=read_scene(ARCHIVE,self.goal['available_at'],self.goal['id'])
        self.assertEqual(scene['status'],'ready')
        self.assertEqual(scene['clock'],self.state['clock'])
        self.assertEqual(scene['frame_png'],self.state['frame_png'])
        self.assertEqual(scene['statistics']['possession'],self.state['possession'])
        self.assertEqual({x['fact_fingerprint'] for x in scene['layouts'].values()},{scene['card']['fact_fingerprint']})
        self.assertEqual(scene['layouts']['stream']['aspect_ratio'],'9:16')
        self.assertEqual(json.loads(json.dumps(scene)),scene)

    def test_all_complete_shot_episodes_pass_independent_source_checks(self):
        episodes=[e for e in self.manifest['episodes'] if e['kind']!='trend']
        self.assertGreater(len(episodes),10)
        for e in episodes:
            scene=read_scene(ARCHIVE,e['available_at'],e['id'])
            self.assertEqual(scene['status'],'ready',(e['id'],scene['integrity']))
            self.assertLessEqual(len(scene['card']['caption']),140)

    def test_seek_before_outcome_withholds_final_episode(self):
        before=read_scene(ARCHIVE,self.goal['time'],self.goal['id'])
        self.assertIsNone(before['card'])
        self.assertEqual(before['status'],'waiting')
        rewind=read_scene(ARCHIVE,0,self.goal['id'])
        self.assertIsNone(rewind['card'])
        self.assertEqual(rewind['score'],[0,0])

    def test_counter_corruption_holds_all_scenes(self):
        episode=deepcopy(self.episode);episode['facts']['passes_in_attack']+=1
        scene=compose(self.state,episode,self.sources)
        self.assertEqual(scene['status'],'held');self.assertIsNone(scene['card'])
        self.assertTrue(all(v['fact_fingerprint'] is None for v in scene['layouts'].values()))

    def test_orphan_pass_cannot_be_presented(self):
        sources=deepcopy(self.sources)
        event=next(e for e in sources.values() if e['kind']=='pass_completed')
        del sources[event['details']['pass_start_id']]
        result=audit_episode(self.episode,sources,self.state['clock'])
        self.assertFalse(next(c['passed'] for c in result['checks'] if c['key']=='passes'))

    def test_wrong_pressure_is_rejected_from_coordinates(self):
        sources=deepcopy(self.sources)
        shot=next(e for e in sources.values() if e['kind']=='shot');shot['details']['pressure_count']+=1
        result=audit_episode(self.episode,sources,self.state['clock'])
        self.assertFalse(next(c['passed'] for c in result['checks'] if c['key']=='pressure'))

    def test_wrong_score_and_future_evidence_are_held(self):
        episode=deepcopy(self.episode);episode['facts']['score']=[9,9]
        self.assertEqual(audit_episode(episode,self.sources,self.state['clock'])['status'],'held')
        self.assertEqual(audit_episode(self.episode,self.sources,self.goal['time'])['status'],'held')

    def test_unknown_or_nonfinite_request_is_rejected(self):
        for at in (-1,5401,float('nan'),float('inf')):
            with self.assertRaises(ValueError):read_scene(ARCHIVE,at)
        with self.assertRaises(KeyError):read_scene(ARCHIVE,0,'unknown-episode')

    def test_default_director_uses_only_known_completed_episodes(self):
        self.assertEqual(read_scene(ARCHIVE,0)['status'],'waiting')
        scene=read_scene(ARCHIVE,self.goal['available_at'])
        self.assertEqual(scene['card']['facts']['episode_id'],self.goal['id'])
        self.assertLessEqual(scene['card']['available_at'],scene['clock'])


if __name__=='__main__':unittest.main()
