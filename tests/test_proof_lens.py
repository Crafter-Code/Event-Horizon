                                                                                

import unittest

from app import MatchSession
from proof_lens import claim_map
from simulation import GeneratorSettings


class ProofLensTests(unittest.TestCase):
    def test_pending_and_resolved_shot_share_a_source_checked_claim_path(self):
        live = MatchSession(GeneratorSettings(2), wall_clock=lambda: 0)
        live.pump(48.9)
        pending = live.snapshot()['experience']['selected']
        self.assertFalse(pending['complete'])
        pending_outcome = next(item for item in pending['proof_lens'] if item['key'] == 'outcome')
        self.assertEqual(pending_outcome['detail'], 'Outcome pending')
        self.assertEqual(pending_outcome['event_ids'],
                         [next(event['id'] for event in pending['evidence'] if event['kind'] == 'shot')])
        live.pump(50)
        completed = live.snapshot()['experience']['selected']
        keys = [item['key'] for item in completed['proof_lens']]
        self.assertEqual(keys, ['opening', 'build', 'shot', 'outcome', 'context'])
        build = completed['proof_lens'][1]
        self.assertEqual(build['value'], completed['facts']['passes_in_attack'])
        self.assertEqual(build['event_ids'], [event['id'] for event in completed['evidence']
                                               if event['kind'] == 'pass_completed'])
        self.assertEqual(completed['proof_lens'][-2]['event_ids'], [completed['evidence'][-1]['id']])
        self.assertEqual(completed['proof_lens'][-1]['event_ids'], [completed['evidence'][-1]['id']])
        self.assertTrue(all(set(item['event_ids']) <= set(completed['evidence_ids'])
                            for item in completed['proof_lens']))

    def test_counterattack_recovery_and_player_role_are_not_invented(self):
        live = MatchSession(GeneratorSettings(2), wall_clock=lambda: 0)
        live.pump(300)
        moment = next(item for item in live.insights.moments.values() if item.facts.get('counterattack'))
        selected = live.snapshot(audience='player', player={'team': 0, 'number': 10},
                                 selected=moment.id)['experience']['selected']
        claims = selected['proof_lens']
        self.assertEqual(claims[0]['key'], 'recovery')
        self.assertEqual(claims[0]['event_ids'][0], next(event['id'] for event in selected['evidence']
            if event['kind'] in ('tackle', 'interception')))
        self.assertIn('after the recovery', next(item for item in claims if item['key']=='shot')['detail'])
        contribution = live.insights.player_contribution(moment, {'team': 0, 'number': 10})
        personal = next(item for item in claims if item['key'] == 'player')
        self.assertEqual(personal['event_ids'], contribution['evidence_ids'])

    def test_language_and_audience_change_copy_not_proof_ids(self):
        live = MatchSession(GeneratorSettings(2), wall_clock=lambda: 0)
        live.pump(50)
        views = [live.snapshot(audience=mode, language=language)['experience']['selected']
                 for language in ('en','de','cs') for mode in ('fan','analyst','player')]
        sources = [tuple((card['key'],tuple(card['event_ids'])) for card in view['proof_lens'])
                   for view in views]
        self.assertEqual(len(set(sources)), 1)
        self.assertEqual(len({view['fact_fingerprint'] for view in views}), 1)
        self.assertEqual(len({view['proof_lens'][0]['label'] for view in views}), 3)

    def test_mismatched_pass_count_is_rejected(self):
        live = MatchSession(GeneratorSettings(2), wall_clock=lambda: 0)
        live.pump(50)
        packet = live.insights.moment_data(next(iter(live.insights.moments.values())))
        packet['facts']['passes_in_attack'] += 1
        with self.assertRaises(ValueError):
            claim_map(packet)


if __name__ == '__main__':
    unittest.main()
