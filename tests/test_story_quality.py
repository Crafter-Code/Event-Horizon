                                                                                 

from copy import deepcopy
import unittest

from app import MatchSession
from editorial import EditorialDesk
from insights import MatchInsights
from simulation import Match, GeneratorSettings, STEP_SECONDS


def long_attack():
    match, insights = Match(), MatchInsights()
    insights.ingest(match)
    for index in range(24):
        match.tick = round((2 + index * 5) / STEP_SECONDS)
        match.clock = match.tick * STEP_SECONDS
        match.completed[0] += 1
        match.event('Pass', 'Pass', kind='pass_completed', actors=(6, 9))
        insights.ingest(match)
    match.clock, match.tick = 125, 2500
    match.event('Shot', 'Shot', kind='shot', actors=(9,))
    insights.ingest(match)
    match.clock, match.tick = 126, 2520
    match.possession_team = 1
    match.event('Save', 'Save', kind='save', actors=(9, 11))
    insights.ingest(match)
    return insights, next(iter(insights.moments.values()))


class StoryQualityTests(unittest.TestCase):
    def test_long_attack_is_not_truncated_by_display_windows(self):
        insights, moment = long_attack()
        self.assertEqual(moment.facts['passes_in_attack'], 24)
        self.assertEqual(len([key for key in moment.evidence_ids if insights.events[key]['kind'] == 'pass_completed']), 24)
        self.assertEqual(insights.attack_path(moment)[1]['label'], 'Completed passes: 24')
        self.assertTrue(insights.verified(moment))

    def test_seed_two_first_attack_has_all_thirteen_passes(self):
        live = MatchSession(GeneratorSettings(2), wall_clock=lambda: 0)
        live.pump(50)
        moment = next(iter(live.insights.moments.values()))
        self.assertEqual(live.match.completed[0], 13)
        self.assertEqual(moment.facts['passes_in_attack'], 13)
        self.assertIn('13', moment.why)
        self.assertTrue(all(check['passed'] for check in live.insights.check_report(moment)))

    def test_personal_story_distinguishes_passing_receiving_and_shooting(self):
        insights, moment = long_attack()
        sender = insights.player_contribution(moment, {'team': 0, 'number': 7})['counts']
        striker = insights.player_contribution(moment, {'team': 0, 'number': 10})['counts']
        keeper = insights.player_contribution(moment, {'team': 1, 'number': 1})['counts']
        self.assertEqual((sender['passes_made'], sender['passes_received'], sender['shots']), (24, 0, 0))
        self.assertEqual((striker['passes_made'], striker['passes_received'], striker['shots']), (0, 24, 1))
        self.assertEqual((keeper['shots'], keeper['saves']), (0, 1))

    def test_independent_checks_reject_corrupted_counts_and_windows(self):
        for field in ('passes', 'score', 'window'):
            insights, moment = long_attack()
            if field == 'passes':
                moment.facts['passes_in_attack'] -= 1
            elif field == 'score':
                moment.facts['score'][0] += 1
            else:
                moment.facts['window']['shots'][0] += 1
            self.assertFalse(insights.verified(moment), field)
            with self.assertRaises(ValueError):
                EditorialDesk().act(insights, moment.id, moment.revision, 'review', moment.what)

    def test_receipt_binds_copy_and_source_and_audit_tracks_actions(self):
        insights, moment = long_attack()
        desk = EditorialDesk()
        first = desk.act(insights, moment.id, moment.revision, 'review', 'A shot after a long attack.')
        second = desk.act(insights, moment.id, moment.revision, 'review', 'The long attack ended with a save.')
        self.assertNotEqual(first['receipt'], second['receipt'])
        desk.act(insights, moment.id, moment.revision, 'select', second['copy'])
        self.assertIsNotNone(desk.snapshot(insights)['active'])
        self.assertEqual([item['action'] for item in desk.history], ['review', 'review', 'select'])
                                                                           
        insights.events[moment.evidence_ids[0]]['text'] += ' changed'
        self.assertTrue(insights.verified(moment))
        self.assertEqual(desk.state(moment, insights)['status'], 'draft')
        self.assertIsNone(desk.snapshot(insights)['active'])
        with self.assertRaises(ValueError):
            desk.act(insights, moment.id, moment.revision, 'select')

    def test_checks_and_personalisation_do_not_mutate_sources(self):
        insights, moment = long_attack()
        original = deepcopy(insights.events)
        fingerprint = insights.fact_fingerprint(moment)
        insights.view(team=0, player={'team': 0, 'number': 7})
        EditorialDesk().snapshot(insights)
        self.assertEqual(insights.events, original)
        self.assertEqual(fingerprint, insights.fact_fingerprint(moment))

    def test_editor_request_must_match_the_facts_actually_displayed(self):
        live = MatchSession(GeneratorSettings(2), wall_clock=lambda: 0)
        live.pump(50)
        moment = next(iter(live.insights.moments.values()))
        payload = {'run_id': live.run_id, 'moment_id': moment.id, 'revision': moment.revision,
                   'fact_fingerprint': live.insights.fact_fingerprint(moment),
                   'action': 'review', 'copy': moment.what}
        live.editorial_action(payload)
        live.insights.events[moment.evidence_ids[0]]['text'] += ' updated'
        with self.assertRaises(ValueError):
            live.editorial_action(payload)


if __name__ == '__main__':
    unittest.main()
