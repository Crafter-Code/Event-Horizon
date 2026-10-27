                                                                                    
from collections import Counter
from copy import deepcopy
from pathlib import Path
import json
import re
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

import app
from demonstration_store import DemoReader, unpack
from story_languages import COPY, LANGUAGES, render


ROOT=Path(__file__).resolve().parents[1]


class StoryLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader=DemoReader(ROOT/'data/full-match.sqlite3')
        cls.manifest=cls.reader.manifest()
        cls.goal=next(e for e in cls.manifest['episodes'] if e['kind']=='goal')
        with cls.reader.connect() as db:
            cls.packets=[unpack(r[0]) for r in db.execute('SELECT packet FROM episodes ORDER BY time')]
        cls.packet=next(p for p in cls.packets if p['id']==cls.goal['id'])

    def test_all_seven_languages_share_the_same_protected_facts(self):
        before=deepcopy(self.packet)
        for mode in ('fan','analyst','player'):
            results=[render(self.packet,l,mode,0,{'team':0,'number':10},5400) for l in LANGUAGES]
            self.assertEqual(len({r['episode']['protected_sha256'] for r in results}),1)
            self.assertEqual({r['language'] for r in results},set(LANGUAGES))
            for result in results:
                self.assertEqual(result['episode']['source_event_ids'],self.packet['evidence_ids'])
                self.assertEqual(result['episode']['fact_fingerprint'],self.packet['fact_fingerprint'])
                self.assertFalse(result['provenance']['model_generated'])
        self.assertEqual(self.packet,before)

    def test_every_recorded_episode_has_four_native_renditions_with_identical_numbers(self):
        for packet in self.packets:
            for audience in ('fan','analyst','player'):
                outputs=[render(packet,l,audience,0,{'team':0,'number':10},5400)['episode'] for l in COPY]
                tokens=lambda p:Counter(re.findall(r'[-+]?\d+(?:\.\d+)?',' '.join(p[k] for k in ('title','what','why','change','caption','personal'))))
                with self.subTest(episode=packet['id'],audience=audience):
                    self.assertEqual(len({p['protected_sha256'] for p in outputs}),1)
                    self.assertTrue(all(tokens(p)==tokens(outputs[0]) for p in outputs))
                    self.assertTrue(all(len(p['caption'])<=140 and p['caption'].count('\n')<=1 for p in outputs))
                    self.assertEqual(len({p['what'] for p in outputs}),4)

    def test_fan_is_shorter_and_absent_player_is_not_given_a_contribution(self):
        for language in COPY:
            fan=render(self.packet,language,'fan',clock=5400)['episode']
            analyst=render(self.packet,language,'analyst',clock=5400)['episode']
            self.assertLess(len(fan['what']+fan['change']),len(analyst['what']+analyst['change']))
            p={'team':0,'number':1}
            self.assertFalse(any(p in e['actors'] for e in self.packet['evidence']))
            text=render(self.packet,language,'player',player=p,clock=5400)['episode']['personal']
            self.assertIn(COPY[language]['no_player'],text)

    def test_unverified_and_future_sources_never_become_a_convincing_translation(self):
        bad=deepcopy(self.packet);bad['verified']=False
        self.assertEqual(render(bad,'fr',clock=5400)['status'],'held')
        self.assertIsNone(render(bad,'fr',clock=5400)['episode'])
        with self.assertRaises(ValueError):render(self.packet,'fr',clock=0)
        for language in ('xx','fr<script>'):
            with self.assertRaises(ValueError):render(self.packet,language,clock=5400)
        for clock in (-1,5401,float('nan')):
            with self.assertRaises(ValueError):render(self.packet,'fr',clock=clock)

    def test_original_ai_interpretation_is_not_relabelled_or_exposed_as_translated_ai(self):
        packet=deepcopy(self.packet);packet['interpretation']={'language':'en','what':'private model text'}
        result=render(packet,'fr',clock=5400)
        self.assertNotIn('private model text',json.dumps(result))
        self.assertFalse(result['provenance']['model_generated'])

    def test_archive_uses_only_the_available_revision_and_keeps_recap_at_full_time(self):
        stat=self.reader.path.stat()
        early=self.reader.story_language(self.goal['time']-.05,'fr',episode=self.goal['id'])
        if early['episode']:
            self.assertNotIn(COPY['fr']['outcomes']['goal'],early['episode']['what'])
        self.assertIsNone(early['recap'])
        pending=self.reader.story_language(self.goal['time'],'fr',episode=self.goal['id'])
        if pending['episode']:
            self.assertFalse(pending['episode']['complete'])
            self.assertIn(COPY['fr']['pending'],pending['episode']['what'])
        results=[self.reader.story_language(5400,l,'player',0,{'team':0,'number':10}) for l in LANGUAGES]
        self.assertEqual(len({r['recap']['fact_fingerprint'] for r in results}),1)
        self.assertTrue(all(r['recap']['source_event_ids']==results[0]['recap']['source_event_ids'] for r in results))
        for result in results[3:]:
            self.assertIn('Max Rowan',result['recap']['text'])
            self.assertEqual([p['score'] for p in result['recap']['goals']],[[1,0],[1,1],[2,1],[2,2],[3,2]])
        self.assertIsNone(self.reader.story_language(5399.95,'fr')['recap'])
        self.assertEqual(self.reader.path.stat().st_mtime_ns,stat.st_mtime_ns)


class StoryHttpTests(unittest.TestCase):
    def setUp(self):
        self.old=app.session
        app.session=app.MatchSession(wall_clock=lambda:0)
        app.session.pump(120)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join(2);app.session=self.old

    def get(self,query):
        try:
            with urlopen(self.base+'/story-language?'+query,timeout=5) as r:return r.status,json.load(r)
        except HTTPError as e:
            with e:return e.code,json.load(e)

    def test_live_reads_do_not_advance_or_mutate_match_and_are_bound_to_current_facts(self):
        before=app.session.confirmed_hash;clock=app.session.match.clock
        code,result=self.get('source=live&language=fr&audience=analyst&player=0:10')
        self.assertEqual(code,200);self.assertEqual(result['status'],'ready')
        q={'source':'live','language':'it','episode':result['episode']['id'],'run_key':result['run_key'],
           'fingerprint':result['episode']['fact_fingerprint']}
        self.assertEqual(self.get(urlencode(q))[0],200)
        self.assertEqual(self.get(urlencode({**q,'fingerprint':'wrong'}))[0],409)
        self.assertEqual(self.get(urlencode({**q,'run_key':'old'}))[0],409)
        self.assertEqual(app.session.confirmed_hash,before);self.assertEqual(app.session.match.clock,clock)

    def test_demo_and_bad_queries_fail_explicitly(self):
        self.assertEqual(self.get('source=demo&at=120&language=pt')[0],200)
        for q in ('language=xx','language=fr&language=it','source=bad','source=live&at=120',
                  'source=demo&at=nan','source=demo&at=5401','player=2:10','player=0:12','unexpected=1'):
            with self.subTest(query=q):self.assertEqual(self.get(q)[0],400)
        self.assertEqual(self.get('source=demo&episode=missing&language=fr')[0],404)
        self.assertEqual(self.get('source=demo&at=120&run_key=old&language=fr')[0],409)


if __name__=='__main__':unittest.main()
