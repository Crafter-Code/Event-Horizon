                                                                               

import unittest

from app import MatchSession
from journey import SCHEMA_VERSION, build
from simulation import GeneratorSettings


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.live = MatchSession(GeneratorSettings(2), wall_clock=lambda: 0)

    def test_waiting_pending_and_completed_stages_never_use_future_events(self):
        waiting = build(self.live)
        self.assertEqual(waiting['schema_version'], SCHEMA_VERSION)
        self.assertIsNone(waiting['selected'])
        self.live.pump(48.9)
        pending = build(self.live)['selected']
        self.assertFalse(pending['complete'])
        self.assertFalse(pending['stages']['story'])
        self.assertFalse(pending['stages']['reviewed'])
        self.assertFalse(pending['stages']['on_air'])
        self.assertTrue(all(item['time'] <= self.live.confirmed_frame['clock'] for item in pending['sources']))
        self.live.pump(50)
        ready = build(self.live)['selected']
        self.assertEqual(ready['id'], pending['id'])
        self.assertGreater(ready['revision'], pending['revision'])
        self.assertTrue(ready['stages']['source'])
        self.assertTrue(ready['stages']['metrics'])
        self.assertTrue(ready['stages']['story'])
        self.assertFalse(ready['stages']['on_air'])
        self.assertIsNone(ready['broadcast']['text'])
        self.assertEqual(ready['agent']['status'], 'not_requested')
        self.assertIsNone(ready['agent']['interpretation'])

    def test_three_formats_share_facts_and_only_selected_copy_is_public(self):
        self.live.pump(50)
        moment = next(iter(self.live.insights.moments.values()))
        before = self.live.match.tick
        fan = build(self.live, team=0, player={'team': 0, 'number': 10})['selected']
        other = build(self.live, team=1, player={'team': 1, 'number': 10})['selected']
        self.assertEqual(fan['fact_fingerprint'], other['fact_fingerprint'])
        self.assertNotEqual(fan['stream']['personal'], other['stream']['personal'])
        self.assertEqual(self.live.match.tick, before)
        self.live.desk.act(self.live.insights, moment.id, moment.revision, 'review', 'Verified shot saved.')
        reviewed = build(self.live)['selected']
        self.assertTrue(reviewed['stages']['reviewed'])
        self.assertIsNone(reviewed['broadcast']['text'])
        self.live.desk.act(self.live.insights, moment.id, moment.revision, 'select')
        aired = build(self.live)['selected']
        self.assertEqual(aired['broadcast']['text'], 'Verified shot saved.')
        self.assertTrue(aired['stages']['on_air'])
        self.assertTrue(aired['broadcast']['receipt'])
        self.live.desk.act(self.live.insights, moment.id, moment.revision, 'hold')
        self.assertIsNone(build(self.live)['selected']['broadcast']['text'])

    def test_language_changes_copy_but_preserves_evidence_and_stage(self):
        self.live.pump(50)
        views = [build(self.live, language=language)['selected'] for language in ('en', 'cs', 'de')]
        self.assertEqual(len({view['fact_fingerprint'] for view in views}), 1)
        self.assertEqual(len({tuple(view['evidence_ids']) for view in views}), 1)
        self.assertEqual(len({view['story']['what'] for view in views}), 3)
        self.assertTrue(all(view['stages']['story'] for view in views))

    def test_trend_previews_sources_across_the_compared_interval(self):
        self.live.pump(130)
        trend = next(moment for moment in self.live.insights.moments.values() if moment.kind == 'trend')
        view = build(self.live, episode=trend.id)['selected']
        self.assertGreater(view['source_count'], view['sources_shown'])
        self.assertGreaterEqual(view['sources_shown'], 8)
        self.assertEqual(view['sources'][0]['id'], view['evidence_ids'][0])
        self.assertEqual(view['sources'][-1]['id'], view['evidence_ids'][-1])

    def test_verified_agent_text_is_separate_and_not_mislabelled_as_translation(self):
        self.live.pump(50)
        moment = next(iter(self.live.insights.moments.values()))
        moment.ai_status = 'verified'
        moment.source = 'foundry'
        moment.interpretation = {'what': 'Source-checked take.', 'why': 'Observed pass chain.',
                                 'change': 'The score stays level.', 'evidence_ids': moment.evidence_ids[:]}
        english = build(self.live, language='en')['selected']
        german = build(self.live, language='de')['selected']
        self.assertEqual(english['agent']['interpretation'], moment.interpretation)
        self.assertIsNone(german['agent']['interpretation'])
        self.assertNotEqual(english['story']['what'], moment.interpretation['what'])

    def test_unknown_episode_is_rejected_without_changing_match(self):
        before = self.live.match.tick
        with self.assertRaises(KeyError):
            build(self.live, episode='missing')
        self.assertEqual(self.live.match.tick, before)


if __name__ == '__main__':
    unittest.main()
