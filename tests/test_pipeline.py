                                                                                  

from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch

from app import MatchSession
from editorial import EditorialConflict
from pipeline import EventContractError, MetricProjector
from simulation import GeneratorSettings


def first_pass():
    live = MatchSession(wall_clock=lambda: 0)
    live.pump(10)
    receipt = live.pipeline.receipts[0]
    return live, receipt


class PipelineTests(unittest.TestCase):
    def test_failed_event_keeps_last_coherent_frame_and_replay_recovers(self):
        live, _ = first_pass()
        before = live.snapshot()
        advance = live.match.advance
        def broken_advance():
            advance()
            live.match.event('Bad input', 'Bad input', kind='unrecognised')
        with patch.object(live.match, 'advance', side_effect=broken_advance):
            live.pump(11)
        after = live.snapshot()
        self.assertEqual(after['pipeline']['status'], 'degraded')
        for field in ('clock', 'event_count', 'event_hash', 'events', 'score', 'passes', 'possession', 'players', 'ball'):
            self.assertEqual(before[field], after[field], field)
        live.pump(20)
        self.assertEqual(live.snapshot()['clock'], before['clock'])
        live.restart()
        live.pump(10)
        self.assertEqual(live.snapshot()['pipeline']['status'], 'ok')

    def test_live_ui_metrics_do_not_read_mutated_generator_counters(self):
        live, _ = first_pass()
        expected = live.snapshot()
        live.match.score = [999, 999]
        live.match.completed = [999, 999]
        live.match.attempts = [999, 999]
        live.match.shots = [999, 999]
        live.pump(10.05)
        actual = live.snapshot()
        for field in ('score', 'passes', 'attempts', 'shots'):
            self.assertEqual(actual[field], expected[field], field)

    def test_contract_rejects_unrecognised_types_and_changed_sender(self):
        live, receipt = first_pass()
        for problem in ('type', 'sender'):
            projector = MetricProjector()
            for event in live.match.events[:receipt['event_id']-1]:
                projector.consume(event)
            bad = deepcopy(live.match.events[receipt['event_id']-1])
            if problem == 'type': bad['kind'] = 'unrecognised'
            else: bad['actors'][0]['number'] = 1
            with self.assertRaises(EventContractError): projector.consume(bad)
            self.assertEqual(projector.completed, [0, 0])

    def test_pass_reaches_metrics_explanation_and_ui_response_automatically(self):
        live, receipt = first_pass()
        response = live.snapshot()
        self.assertTrue(response['pipeline']['receipts'])
        self.assertEqual(receipt['passes_after'], receipt['passes_before'] + 1)
        self.assertIn(f"#{receipt['sender']} → #{receipt['receiver']}", receipt['explanation'])
        self.assertAlmostEqual(receipt['distance_m'], round(math.dist(receipt['origin'], receipt['end']), 1))
        self.assertEqual(receipt['progress_m'], round((receipt['end'][0]-receipt['origin'][0])*receipt['direction'], 1))
        self.assertGreaterEqual(receipt['processing_ms'], 0)
        self.assertEqual(response['pipeline']['received'], response['pipeline']['processed'])

    def test_metrics_are_calculated_from_events_not_copied_from_producer(self):
        live, receipt = first_pass()
        projector = MetricProjector()
        for event in live.match.events:
            changed = deepcopy(event)
            changed['score'] = [999, 999]
            changed['passes'] = [999, 999]
            changed['attempts'] = [999, 999]
            changed['shots'] = [999, 999]
            projector.consume(changed)
        self.assertEqual(projector.completed, live.match.completed)
        self.assertEqual(projector.attempts, live.match.attempts)
        self.assertEqual(projector.score, live.match.score)
        self.assertEqual(projector.shots, live.match.shots)

    def test_redelivery_does_not_double_count(self):
        live, receipt = first_pass()
        projector = MetricProjector()
        for event in live.match.events:
            self.assertTrue(projector.consume(event))
            self.assertFalse(projector.consume(deepcopy(event)))
        self.assertEqual(projector.completed, live.match.completed)

    def test_conflicting_duplicate_and_gap_are_rejected_without_mutation(self):
        live, receipt = first_pass()
        events = live.match.events
        projector = MetricProjector()
        projector.consume(events[0])
        bad = deepcopy(events[0]); bad['text'] += ' changed'
        with self.assertRaises(EventContractError): projector.consume(bad)
        with self.assertRaises(EventContractError): projector.consume(events[2])
        self.assertEqual(projector.last_id, 1)
        self.assertEqual(projector.completed, [0, 0])

    def test_outcome_requires_original_pass_and_consistent_geometry(self):
        live, receipt = first_pass()
        outcome = live.match.events[receipt['event_id'] - 1]
        for change in ('reference', 'endpoint', 'actors'):
            projector = MetricProjector()
            for event in live.match.events[:outcome['id']-1]: projector.consume(event)
            bad = deepcopy(outcome)
            if change == 'reference': bad['details']['pass_start_id'] = 99999
            elif change == 'endpoint': bad['details']['end'][0] += 5
            else: bad['actors'] = ['invalid']
            before = projector.completed[:]
            with self.assertRaises(EventContractError): projector.consume(bad)
            self.assertEqual(projector.completed, before)

    def test_source_chain_is_the_actual_start_and_completion(self):
        live, receipt = first_pass()
        data = live.snapshot()['pipeline']['receipts'][0]
        self.assertEqual([e['kind'] for e in data['source_events']], ['pass_started', 'pass_completed'])
        for source in data['source_events']:
            self.assertEqual(source, live.match.events[source['id'] - 1])
        self.assertEqual(data['start_event_id'], data['source_events'][0]['id'])

    def test_reading_api_does_not_claim_that_a_card_was_displayed(self):
        live, receipt = first_pass()
        first = live.snapshot()['pipeline']
        live.snapshot(); live.snapshot()
        self.assertTrue(all(not p['displayed'] for p in first['receipts']))
        self.assertEqual(live.pipeline.displayed, set())

    def test_display_confirmation_is_idempotent_and_checked_against_run(self):
        live, receipt = first_pass()
        payload = {'run_id': live.run_id, 'event_id': receipt['event_id']}
        before = live.pipeline.revision
        live.acknowledge_display(payload)
        after = live.pipeline.revision
        self.assertGreater(after, before)
        live.acknowledge_display(payload)
        self.assertEqual(after, live.pipeline.revision)
        self.assertTrue(live.snapshot()['pipeline']['receipts'][0]['displayed'])
        live.restart()
        with self.assertRaises(EditorialConflict): live.acknowledge_display(payload)
        with self.assertRaises(ValueError): live.acknowledge_display({'run_id':live.run_id,'event_id':99999})

    def test_timings_and_display_status_do_not_change_reproducible_events(self):
        first, second = MatchSession(wall_clock=lambda:0), MatchSession(wall_clock=lambda:0)
        first.pump(120); second.pump(120)
        for item in list(first.pipeline.receipts): first.pipeline.acknowledge_display(item['event_id'])
        self.assertEqual(first.match.event_digest.hexdigest(), second.match.event_digest.hexdigest())
        self.assertEqual(first.match.events, second.match.events)
        first_passes = [dict(p,processing_ms=0) for p in first.pipeline.receipts]
        second_passes = [dict(p,processing_ms=0) for p in second.pipeline.receipts]
        self.assertEqual(first_passes, second_passes)

    def test_unchanged_pipeline_payload_is_omitted(self):
        live, receipt = first_pass()
        initial = live.snapshot()
        same = live.snapshot(after=initial['event_count'],run_id=live.run_id,
                             pipeline_revision=initial['pipeline_revision'])
        self.assertNotIn('pipeline', same)
        self.assertEqual(same['events'], [])

    def test_projected_counters_match_reference_through_full_match(self):
        live = MatchSession(GeneratorSettings(42),wall_clock=lambda:0)
        for second in range(1,5401):
            live.pump(second)
            self.assertIsNone(live.pipeline.last_error)
            if second % 30 == 0:
                projected=live.pipeline.metrics.snapshot(live.match.players,live.match.ball,
                                                        bool(live.match.restart) or live.match.finished)
                reference=live.match.snapshot()
                for key in projected: self.assertEqual(projected[key],reference[key],(second,key))
        self.assertEqual(live.pipeline.metrics.saves, live.match.saves)
        self.assertTrue(live.match.finished)


if __name__ == '__main__':
    unittest.main()
