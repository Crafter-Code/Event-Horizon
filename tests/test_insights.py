import asyncio
from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

from app import MatchSession
from editorial import EditorialDesk, EditorialConflict
from foundry_narrative import FoundryNarrator, from_environment, validate_draft, compact_for_model
from broadcast_peer import review_payload, validate_review
from broadcast_peer_server import decide
from insights import MatchInsights
from simulation import Match, GeneratorSettings, STEP_SECONDS


def receive(match, insights, time, kind, team=0, score=None):
    match.clock, match.tick = time, round(time / STEP_SECONDS)
    match.possession_team = team
    if score is not None:
        match.score = score[:]
    match.event(kind, kind, kind=kind, actors=(team * 11 + 9,))
    insights.ingest(match)
    return match.events[-1]


def resolved_moment():
    match, insights = Match(), MatchInsights()
    insights.ingest(match)
    receive(match, insights, 10, 'shot')
    receive(match, insights, 11, 'goal', score=[1, 0])
    return match, insights, next(iter(insights.moments.values()))


class InsightTests(unittest.TestCase):
    def test_ordinary_passes_are_not_key_moments(self):
        live = MatchSession(wall_clock=lambda: 0)
        live.pump(30)
        self.assertGreater(sum(live.match.completed), 0)
        self.assertEqual(len(live.insights.moments), 0)
        self.assertIn('first key', live.insights.view()['summary'].lower())

    def test_shot_then_goal_updates_one_moment_and_explains_score(self):
        match, insights = Match(), MatchInsights()
        insights.ingest(match)
        receive(match, insights, 10, 'shot')
        moment = next(iter(insights.moments.values()))
        self.assertFalse(moment.complete)
        old_revision = moment.revision
        receive(match, insights, 11, 'goal', score=[1, 0])
        self.assertEqual(len(insights.moments), 1)
        self.assertTrue(moment.complete)
        self.assertGreater(moment.revision, old_revision)
        self.assertIn('take the lead', moment.title)
        self.assertIn('1:0', moment.what)
        self.assertIn('put the team ahead', moment.why)
        self.assertTrue(insights.verified(moment))
        self.assertEqual([insights.events[key]['kind'] for key in moment.evidence_ids][-2:], ['shot', 'goal'])

    def test_goal_equalizer_is_distinguished_from_lead(self):
        match, insights = Match(), MatchInsights()
        insights.ingest(match)
        receive(match, insights, 10, 'shot', team=1, score=[1, 0])
        receive(match, insights, 11, 'goal', team=1, score=[1, 1])
        moment = next(iter(insights.moments.values()))
        self.assertIn('equalize', moment.title)
        self.assertIn('levelled the score', moment.why)

    def test_live_narrative_has_what_why_change_and_real_sources(self):
        live = MatchSession(wall_clock=lambda: 0)
        live.pump(300)
        result = live.insights.view()
        self.assertGreater(len(result['moments']), 0)
        for moment in result['moments']:
            self.assertTrue(all(moment[field] for field in ('what', 'why', 'change')))
            self.assertTrue(moment['verified'])
            self.assertEqual(moment['source'], 'local')
            for evidence in moment['evidence']:
                self.assertLessEqual(evidence['time'], live.match.clock)
                self.assertEqual(evidence, live.match.events[evidence['id'] - 1])
        self.assertIn('Then', result['summary'])
        self.assertIn('A minute earlier', result['summary'])

    def test_windows_compare_received_shots_only(self):
        match, insights = Match(), MatchInsights()
        insights.ingest(match)
        for time, team in ((10, 0), (50, 0), (70, 1), (100, 0)):
            receive(match, insights, time, 'shot', team)
        match.clock = 120
        insights.ingest(match)
        window = insights.window()
        self.assertEqual(window['shots'], [1, 1])
        self.assertEqual(window['previous_shots'], [2, 0])

    def test_future_events_are_rejected(self):
        match, insights = Match(), MatchInsights()
        insights.ingest(match)
        match.clock = 10
        match.event('Shot', 'Shot', kind='shot')
        match.clock = 9
        with self.assertRaises(ValueError):
            insights.ingest(match)

    def test_fan_preferences_change_priority_not_facts(self):
        live = MatchSession(wall_clock=lambda: 0)
        live.pump(600)
        neutral = deepcopy(live.insights.moments)
        player = {'team': 0, 'number': 10}
        view = live.insights.view(team=0, player=player)
        self.assertIn('#10', view['focus'])
        self.assertTrue(any('Your player · #10' in item['personalization'] for item in view['moments']))
        for item in view['moments']:
            original = neutral[item['id']]
            self.assertEqual(item['what'], original.what)
            self.assertEqual(item['evidence_ids'], original.evidence_ids)
            if 'Your player · #10' in item['personalization']:
                self.assertIn(player, item['actors'])
        self.assertEqual(neutral, live.insights.moments)

    def test_reading_and_personalizing_do_not_change_the_match(self):
        first, second = MatchSession(wall_clock=lambda: 0), MatchSession(wall_clock=lambda: 0)
        for second_number in range(1, 301):
            first.pump(second_number)
            first.snapshot(team=1, player={'team': 1, 'number': 4}, view='editor')
        second.pump(300)
        self.assertEqual(first.match.events, second.match.events)
        self.assertEqual(first.insights.view(), second.insights.view())

    def test_incremental_response_omits_unchanged_materials(self):
        live = MatchSession(wall_clock=lambda: 0)
        live.pump(300)
        initial = live.snapshot(view='editor')
        same = live.snapshot(after=initial['event_count'], run_id=live.run_id, view='editor',
                             insight_revision=initial['insight_revision'], desk_revision=initial['desk_revision'])
        self.assertNotIn('insights', same)
        self.assertNotIn('editorial', same)
        self.assertEqual(same['events'], [])


class EditorialTests(unittest.TestCase):
    def test_material_cannot_be_selected_before_review(self):
        _, insights, moment = resolved_moment()
        with self.assertRaises(ValueError):
            EditorialDesk().act(insights, moment.id, moment.revision, 'select')

    def test_pending_shot_cannot_be_reviewed(self):
        match, insights = Match(), MatchInsights()
        insights.ingest(match)
        receive(match, insights, 10, 'shot')
        moment = next(iter(insights.moments.values()))
        with self.assertRaises(ValueError):
            EditorialDesk().act(insights, moment.id, moment.revision, 'review', moment.what)

    def test_review_select_preview_and_hold(self):
        _, insights, moment = resolved_moment()
        original = deepcopy(insights.events)
        desk = EditorialDesk()
        desk.act(insights, moment.id, moment.revision, 'review', 'Blue opened the scoring — 1:0.')
        desk.act(insights, moment.id, moment.revision, 'select', 'Blue opened the scoring — 1:0.')
        self.assertEqual(desk.snapshot(insights)['active']['editorial']['copy'], 'Blue opened the scoring — 1:0.')
        self.assertEqual(desk.snapshot(insights)['selected_count'], 1)
        desk.act(insights, moment.id, moment.revision, 'hold')
        self.assertIsNone(desk.snapshot(insights)['active'])
        self.assertEqual(insights.events, original)

    def test_new_revision_invalidates_review_and_selected_preview(self):
        _, insights, moment = resolved_moment()
        desk = EditorialDesk()
        desk.act(insights, moment.id, moment.revision, 'review', moment.what)
        desk.act(insights, moment.id, moment.revision, 'select')
        old = moment.revision
        moment.revision += 1
        self.assertEqual(desk.state(moment)['status'], 'draft')
        self.assertIsNone(desk.snapshot(insights)['active'])
        with self.assertRaises(EditorialConflict):
            desk.act(insights, moment.id, old, 'review', moment.what)

    def test_changed_copy_requires_new_review(self):
        _, insights, moment = resolved_moment()
        desk = EditorialDesk()
        desk.act(insights, moment.id, moment.revision, 'review', moment.what)
        with self.assertRaises(EditorialConflict):
            desk.act(insights, moment.id, moment.revision, 'select', 'Different text')

    def test_old_run_cannot_modify_new_match(self):
        live = MatchSession(wall_clock=lambda: 0)
        live.pump(300)
        moment = next(iter(live.insights.moments.values()))
        payload = {'run_id': live.run_id, 'moment_id': moment.id, 'revision': moment.revision, 'action': 'review', 'copy': moment.what}
        live.restart()
        with self.assertRaises(EditorialConflict):
            live.editorial_action(payload)
        self.assertEqual(len(live.desk.records), 0)

    def test_unknown_sources_cannot_be_reviewed(self):
        _, insights, moment = resolved_moment()
        moment.evidence_ids.append(99999)
        with self.assertRaises(ValueError):
            EditorialDesk().act(insights, moment.id, moment.revision, 'review', moment.what)


class FakeAgent:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def run(self, prompt):
        self.calls.append(prompt)
        return json.dumps(next(self.responses), ensure_ascii=False)


class FoundryTests(unittest.TestCase):
    def test_model_packet_keeps_evidence_without_video_frames(self):
        packet, _ = self.packet_and_draft()
        compact = compact_for_model(packet)
        self.assertEqual(compact['evidence_ids'], packet['evidence_ids'])
        self.assertEqual(compact['fact_fingerprint'], packet['fact_fingerprint'])
        self.assertTrue(all('frame' not in item for item in compact['evidence']))
        self.assertTrue(all(item['id'] in packet['evidence_ids'] for item in compact['evidence']))
        self.assertLess(len(json.dumps(compact)), len(json.dumps(packet)))

    def packet_and_draft(self):
        _, insights, moment = resolved_moment()
        packet = insights.moment_data(moment)
        draft = {field: packet[field] for field in ('what', 'why', 'change', 'evidence_ids')}
        return packet, draft

    def test_three_agents_and_repair_after_rejection(self):
        packet, draft = self.packet_and_draft()
        analyst = FakeAgent([{'evidence_ids': packet['evidence_ids']}])
        writer = FakeAgent([draft, draft])
        verifier = FakeAgent([{'approved': False, 'unsupported_claims': ['clarify wording']},
                              {'approved': True, 'unsupported_claims': []}])
        result = asyncio.run(FoundryNarrator(analyst, writer, verifier).compose(packet))
        self.assertEqual(result, draft)
        self.assertEqual((len(analyst.calls), len(writer.calls), len(verifier.calls)), (1, 2, 2))
        self.assertIn('Repair', writer.calls[1])

    def test_handoff_restricts_writer_to_analyst_evidence(self):
        packet, draft = self.packet_and_draft()
        self.assertGreater(len(packet['evidence_ids']), 1)
        selected = [packet['evidence_ids'][-1]]
        analyst = FakeAgent([{'evidence_ids': selected}])
        writer = FakeAgent([{**draft, 'evidence_ids': selected}])
        verifier = FakeAgent([{'approved': True, 'unsupported_claims': []}])
        narrator = FoundryNarrator(analyst, writer, verifier)
        asyncio.run(narrator.compose(packet))
        handoff = json.loads(writer.calls[0])
        self.assertEqual(handoff['source']['evidence_ids'], selected)
        self.assertEqual([event['id'] for event in handoff['source']['evidence']], selected)
        self.assertEqual(narrator.trace()[0]['status'], 'verified')
        self.assertEqual([stage['role'] for stage in narrator.trace()[0]['stages']],
                         ['analysis', 'writing', 'fact_checking'])

    def test_writer_cannot_bypass_analyst_selection(self):
        packet, draft = self.packet_and_draft()
        analyst = FakeAgent([{'evidence_ids': [packet['evidence_ids'][-1]]}])
        writer = FakeAgent([draft])
        verifier = FakeAgent([])
        narrator = FoundryNarrator(analyst, writer, verifier)
        with self.assertRaises(ValueError):
            asyncio.run(narrator.compose(packet))
        self.assertEqual(len(verifier.calls), 0)
        self.assertEqual(narrator.trace()[0]['status'], 'fallback')

    def test_broadcast_peer_checks_identity_and_fails_closed(self):
        packet, draft = self.packet_and_draft()
        request = review_payload(packet, draft)
        self.assertEqual(validate_review(decide(request), request)['approved'], True)
        bad = {**request, 'fact_fingerprint': 'wrong'}
        with self.assertRaises(ValueError):
            validate_review(decide(bad), bad)

    def test_a2a_outage_retains_factual_episode(self):
        live = MatchSession(wall_clock=lambda: 0)
        live.pump(300)
        moment = next(item for item in live.insights.moments.values() if item.complete)
        packet = live.insights.moment_data(moment)
        draft = {field: packet[field] for field in ('what', 'why', 'change', 'evidence_ids')}
        original = moment.what

        class ReadyNarrator:
            def __init__(self):
                self.history = [{'status':'verified', 'stages':[]}]

            async def compose(self, _):
                return draft

        class UnavailablePeer:
            async def review(self, *_):
                raise TimeoutError('A2A peer unavailable')

        live.narrator = ReadyNarrator()
        live.broadcast_peer = UnavailablePeer()
        key = (live.run_id, moment.id, moment.revision)
        self.assertTrue(asyncio.run(live.process_narrative_job(key, packet)))
        self.assertEqual((moment.what, moment.source, moment.ai_status),
                         (original, 'local', 'fallback'))
        self.assertEqual(live.narrator.history[0]['stages'][-1]['role'], 'broadcast_a2a')

    def test_unsupported_numbers_and_sources_are_rejected(self):
        packet, draft = self.packet_and_draft()
        for invalid in ({**draft, 'what': 'Score 99:99.'}, {**draft, 'evidence_ids': [99999]}):
            with self.assertRaises(ValueError):
                validate_draft(invalid, packet)

    def test_missing_configuration_uses_explicit_local_mode(self):
        with patch.dict(os.environ, {}, clear=True):
            narrator, status = from_environment()
        self.assertIsNone(narrator)
        self.assertIn('Local', status)

    def test_stale_ai_result_is_ignored_and_failure_preserves_facts(self):
        live = MatchSession(wall_clock=lambda: 0)
        live.pump(300)
        moment = next(iter(live.insights.moments.values()))
        key = (live.run_id, moment.id, moment.revision)
        original = moment.what
        self.assertTrue(live.apply_narrative(key, None))
        self.assertEqual(moment.what, original)
        self.assertEqual(moment.source, 'local')
        live.restart()
        self.assertFalse(live.apply_narrative(key, None))


if __name__ == '__main__':
    unittest.main()
