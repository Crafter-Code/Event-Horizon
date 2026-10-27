                                                                                     

from collections import deque
from copy import deepcopy
from dataclasses import asdict
import json
from types import SimpleNamespace
import unittest

from insights import MatchInsights, Moment
from intelligence_provenance import build_provenance, TRACE_WINDOW
from simulation import GeneratorSettings, MODEL_VERSION


class TraceNarrator:
    def __init__(self):
        self.history = deque(maxlen=TRACE_WINDOW)

    def trace(self):
        return deepcopy(list(self.history))


def session_fixture(configured=False):
    insights = MatchInsights()
    return SimpleNamespace(run_key='current-run', insights=insights,
        narrator=TraceNarrator() if configured else None,
        match=SimpleNamespace(match_id='synthetic-match', settings=GeneratorSettings(42)))


def add_episode(session, key='moment-1', state='not_requested'):
    event_id = len(session.insights.events) + 1
    session.insights.events[event_id] = {'id': event_id, 'kind': 'goal', 'time': event_id,
                                        'score': [1, 0], 'text': 'A recorded synthetic goal.'}
    moment = Moment(key, 2, event_id, 0, 'goal', 'Synthetic goal', 'A goal occurred.',
                    'The score changed.', 'Blue leads.', [event_id], [], True, {'score': [1, 0]},
                    ai_status=state)
    session.insights.moments[key] = moment
    return moment


def apply_fixture(session, moment):
    source = session.insights.fact_fingerprint(moment)
    ids = moment.evidence_ids[:]
    trace = {'run_key': session.run_key, 'episode_id': moment.id, 'fact_fingerprint': source,
             'status': 'verified', 'stages': [
                 {'role': 'analysis', 'status': 'complete', 'evidence_ids': ids},
                 {'role': 'writing', 'status': 'complete', 'attempt': 1, 'evidence_ids': ids},
                 {'role': 'fact_checking', 'status': 'approved', 'attempt': 1, 'issue_count': 0}]}
    session.narrator.history.append(trace)
    moment.interpretation = {'what': 'Model output must stay private here.', 'why': 'An explanation.',
                             'change': 'A change.', 'evidence_ids': ids}
    moment.source, moment.ai_status = 'foundry', 'verified'
    moment.revision += 1
    return trace


class IntelligenceProvenanceTests(unittest.TestCase):
    def test_local_factual_origin_is_explicit(self):
        live = session_fixture()
        add_episode(live)
        result = build_provenance(live)
        self.assertEqual(result['data'], {'origin': 'synthetic', 'model_version': MODEL_VERSION,
            'match_id': 'synthetic-match', 'seed': 42, 'scenario': 'open_play'})
        self.assertEqual(result['narrative']['status'], 'local_factual')
        self.assertEqual(result['narrative']['provider'], 'local')
        self.assertIsNone(result['narrative']['proof'])

    def test_configured_client_with_no_calls_is_not_verified(self):
        live = session_fixture(True)
        add_episode(live, state='pending')
        narrative = build_provenance(live)['narrative']
        self.assertEqual(narrative['status'], 'configured')
        self.assertEqual(narrative['counts'], {'verified': 0, 'pending': 1, 'fallback': 0})
        self.assertIsNone(narrative['latest'])

    def test_applied_result_matches_current_facts_and_pre_application_revision(self):
        live = session_fixture(True)
        moment = add_episode(live)
        trace = apply_fixture(live, moment)
        narrative = build_provenance(live)['narrative']
        self.assertEqual(narrative['status'], 'verified')
        self.assertEqual(narrative['counts']['verified'], 1)
        self.assertEqual(narrative['proof']['source_fact_fingerprint'], trace['fact_fingerprint'])
        self.assertEqual(narrative['proof']['fact_fingerprint'], live.insights.fact_fingerprint(moment))
        self.assertNotEqual(narrative['proof']['source_fact_fingerprint'], narrative['proof']['fact_fingerprint'])

    def test_stale_run_episode_and_fingerprint_never_prove_current_ai(self):
        for field, value in (('run_key', 'old-run'), ('episode_id', 'missing'),
                             ('fact_fingerprint', 'mismatched-facts')):
            with self.subTest(field=field):
                live = session_fixture(True)
                trace = apply_fixture(live, add_episode(live))
                trace[field] = value
                narrative = build_provenance(live)['narrative']
                self.assertEqual(narrative['status'], 'configured')
                self.assertEqual(narrative['counts']['verified'], 0)
                self.assertIsNone(narrative['latest'])
                self.assertIsNone(narrative['proof'])

    def test_changed_current_facts_cannot_reuse_an_approved_trace(self):
        live = session_fixture(True)
        moment = add_episode(live)
        apply_fixture(live, moment)
        moment.facts['score'] = [2, 0]
        self.assertIsNone(build_provenance(live)['narrative']['proof'])

    def test_approved_trace_without_applied_interpretation_cannot_pass(self):
        for broken in ('source', 'ai_status', 'interpretation', 'incomplete', 'citations', 'approval'):
            with self.subTest(broken=broken):
                live = session_fixture(True)
                moment = add_episode(live)
                trace = apply_fixture(live, moment)
                if broken == 'source': moment.source = 'local'
                elif broken == 'ai_status': moment.ai_status = 'fallback'
                elif broken == 'interpretation': moment.interpretation = None
                elif broken == 'incomplete': moment.complete = False
                elif broken == 'citations': moment.interpretation['evidence_ids'] = [999]
                elif broken == 'approval': trace['stages'][-1]['status'] = 'rejected'
                narrative = build_provenance(live)['narrative']
                self.assertEqual(narrative['counts']['verified'], 0)
                self.assertIsNone(narrative['proof'])

    def test_fallback_is_not_verified_even_with_an_approved_stage(self):
        live = session_fixture(True)
        moment = add_episode(live, state='fallback')
        trace = apply_fixture(live, moment)
        trace['status'] = 'fallback'
        self.assertIsNone(build_provenance(live)['narrative']['proof'])
        self.assertEqual(build_provenance(live)['narrative']['status'], 'fallback')

    def test_latest_failure_does_not_erase_earlier_applied_success(self):
        live = session_fixture(True)
        good = add_episode(live, 'earlier')
        apply_fixture(live, good)
        failed = add_episode(live, 'later', 'fallback')
        live.narrator.history.append({'run_key': live.run_key, 'episode_id': failed.id,
            'fact_fingerprint': live.insights.fact_fingerprint(failed), 'status': 'fallback', 'stages': []})
        narrative = build_provenance(live)['narrative']
        self.assertEqual(narrative['status'], 'fallback')
        self.assertEqual(narrative['counts'], {'verified': 1, 'pending': 0, 'fallback': 1})
        self.assertEqual(narrative['proof']['episode_id'], 'earlier')
        self.assertEqual(narrative['latest']['episode_id'], 'later')

    def test_trace_window_is_not_an_all_time_success_counter(self):
        live = session_fixture(True)
        apply_fixture(live, add_episode(live))
        for i in range(TRACE_WINDOW):
            live.narrator.history.append({'run_key': 'old-run', 'episode_id': str(i)})
        narrative = build_provenance(live)['narrative']
        self.assertEqual(narrative['counts']['verified'], 0)
        self.assertEqual(narrative['verified_count_scope'], 'current_run_retained_traces')
        self.assertEqual(narrative['trace_window'], TRACE_WINDOW)

    def test_read_only_and_no_raw_text_secret_or_endpoint_disclosure(self):
        live = session_fixture(True)
        moment = add_episode(live)
        trace = apply_fixture(live, moment)
        trace.update(prompt='PRIVATE_PROMPT', endpoint='PRIVATE_ENDPOINT', failure='PRIVATE_ERROR')
        before = (asdict(moment), deepcopy(live.insights.events), live.narrator.trace())
        result = build_provenance(live)
        self.assertEqual(before, (asdict(moment), live.insights.events, live.narrator.trace()))
        serialized = json.dumps(result)
        for value in ('PRIVATE_PROMPT', 'PRIVATE_ENDPOINT', 'PRIVATE_ERROR', 'Model output must stay private here.'):
            self.assertNotIn(value, serialized)
        self.assertLess(len(serialized), 1600)

    def test_actual_application_revision_transition_is_recognized(self):
        from app import MatchSession
        live = MatchSession(GeneratorSettings(2), wall_clock=lambda: 0)
        live.pump(50)
        live.narrator = TraceNarrator()
        moment = next(item for item in live.insights.moments.values() if item.complete)
        packet = live.insights.moment_data(moment)
        draft = {key: packet[key] for key in ('what', 'why', 'change', 'evidence_ids')}
        live.narrator.history.append({'run_key': live.run_key, 'episode_id': moment.id,
            'fact_fingerprint': packet['fact_fingerprint'], 'status': 'verified', 'stages': [
                {'role': 'analysis', 'status': 'complete', 'evidence_ids': draft['evidence_ids']},
                {'role': 'writing', 'status': 'complete', 'attempt': 1, 'evidence_ids': draft['evidence_ids']},
                {'role': 'fact_checking', 'status': 'approved', 'attempt': 1, 'issue_count': 0}]})
        self.assertTrue(live.apply_narrative((live.run_id, moment.id, moment.revision), draft))
        with live.lock:
            result = build_provenance(live)
        self.assertEqual(result['narrative']['status'], 'verified')
        self.assertEqual(result['narrative']['proof']['episode_id'], moment.id)


if __name__ == '__main__':
    unittest.main()
