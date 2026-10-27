                                                                               
from copy import deepcopy
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from match_arc import build_arc, MAX_CHECKPOINTS
import demonstration_store as store


def event(key, at, kind, team=0, score=None, **details):
    return {'id': key, 'time': at, 'kind': kind, 'team': team,
            'score': score if score is not None else [0, 0], 'details': details}


class MatchArcTests(unittest.TestCase):
    def test_scoreless_match_does_not_invent_a_highlight_or_winner(self):
        result = build_arc([event(1, 0, 'kickoff'), event(2, 5400, 'full_time')], 0, 5400, True)
        self.assertIn('stayed at 0:0', result['narrative'])
        self.assertEqual(result['checkpoints'], [])
        self.assertEqual(result['counts']['shots'], [0, 0])
        self.assertEqual(result['source_event_ids'], [1, 2])
        self.assertNotIn('won', result['narrative'])

    def test_first_shot_stays_pending_and_future_events_change_nothing(self):
        known = [event(1, 0, 'kickoff'), event(2, 7, 'shot', 1)]
        future = event(3, 8, 'goal', 1, [0, 1])
        result = build_arc(known + [future], 0, 7, False)
        self.assertEqual(result, build_arc(known, 0, 7, False))
        self.assertEqual(result['checkpoints'][0]['kind'], 'first_shot')
        self.assertEqual(result['checkpoints'][0]['score'], [0, 0])
        self.assertIn('still in progress', result['narrative'])
        self.assertNotIn('goal', result['narrative'].lower())
        self.assertNotIn(3, result['source_event_ids'])

    def test_goal_sequence_distinguishes_equalizer_restored_and_new_lead(self):
        teams = [0, 1, 0, 1, 1, 1, 0]
        events = [event(1, 0, 'kickoff')]
        score = [0, 0]
        for i, team in enumerate(teams, 2):
            score[team] += 1
            events.append(event(i, i * 60, 'goal', team, score[:]))
        result = build_arc(events, 0, 600, False)
        self.assertEqual([p['kind'] for p in result['checkpoints']],
                         ['opening_goal', 'equalizer', 'lead_restored', 'equalizer',
                          'takes_lead', 'extends_lead', 'reduces_deficit'])
        self.assertEqual(result['checkpoints'][-1]['score'], [3, 4])
        self.assertIn('3:4', result['narrative'])
        self.assertEqual(result['score_transitions']['equalizers'], [0, 2])
        self.assertIn('Red drew level twice', result['narrative'])

    def test_half_boundary_goal_is_counted_once_and_establishes_next_opening_score(self):
        events = [event(1, 0, 'kickoff'), event(2, 2700, 'goal', 0, [1, 0]),
                  event(3, 2700, 'second_half', 1, [1, 0]),
                  event(4, 2701, 'goal', 1, [1, 1])]
        first = build_arc(events, 0, 2700, True)
        second = build_arc(events, 2700, 2800, False)
        self.assertEqual([p['event_id'] for p in first['checkpoints']], [2])
        self.assertEqual([p['event_id'] for p in second['checkpoints']], [4])
        self.assertEqual(second['checkpoints'][0]['kind'], 'equalizer')
        self.assertIn('from 1:0 to 1:1', second['narrative'])
        self.assertEqual(second['coverage']['event_count'], 1)

    def test_restored_lead_cites_the_earlier_lead_even_across_half_boundary(self):
        events = [event(1, 0, 'kickoff'), event(2, 100, 'goal', 0, [1, 0]),
                  event(3, 200, 'goal', 1, [1, 1]), event(4, 2800, 'goal', 0, [2, 1])]
        result = build_arc(events, 2700, 2900, False)
        self.assertEqual(result['checkpoints'][0]['kind'], 'lead_restored')
        self.assertEqual(result['checkpoints'][0]['evidence_ids'], [2, 4])
        self.assertEqual(result['coverage']['event_count'], 1)

    def test_pressure_already_present_at_period_boundary_is_not_lost(self):
        events = [event(1, 0, 'kickoff'), event(2, 2699, 'pressure', 0, counts=[2, 0]),
                  event(3, 2701, 'pressure', 0, counts=[0, 0])]
        result = build_arc(events, 2700, 2800, False)
        self.assertEqual(result['counts']['pressure_peak'], [2, 0])
        self.assertEqual(result['counts']['pressure_changes'], 1)
        self.assertIn(2, result['source_event_ids'])

    def test_source_digest_covers_prior_pressure_payload_not_only_interval_rows(self):
        events = [event(1, 0, 'kickoff'), event(2, 2699, 'pressure', 0, counts=[2, 0]),
                  event(3, 2701, 'pressure', 0, counts=[0, 0])]
        first = build_arc(events, 2700, 2800, False)
        changed = deepcopy(events)
        changed[1]['details']['counts'] = [3, 0]
        second = build_arc(changed, 2700, 2800, False)
        self.assertNotEqual(first['narrative'], second['narrative'])
        self.assertNotEqual(first['coverage']['source_sha256'], second['coverage']['source_sha256'])
        self.assertEqual(first['coverage']['context_event_ids'], [2])

    def test_source_digest_covers_prior_lead_even_when_opening_score_is_identical(self):
        prefix_a = [event(1, 0, 'kickoff'), event(2, 100, 'goal', 0, [1, 0]),
                    event(3, 200, 'goal', 1, [1, 1])]
        prefix_b = [event(1, 0, 'kickoff'), event(2, 100, 'goal', 1, [0, 1]),
                    event(3, 200, 'goal', 0, [1, 1])]
        goal = event(4, 2800, 'goal', 0, [2, 1])
        first = build_arc(prefix_a + [goal], 2700, 2900, False)
        second = build_arc(prefix_b + [goal], 2700, 2900, False)
        self.assertEqual(first['checkpoints'][0]['kind'], 'lead_restored')
        self.assertEqual(second['checkpoints'][0]['kind'], 'takes_lead')
        self.assertNotEqual(first['coverage']['source_sha256'], second['coverage']['source_sha256'])

    def test_activity_counts_and_pressure_use_received_sources_only(self):
        events = [event(1, 0, 'kickoff'), event(2, 1, 'pass_completed'),
                  event(3, 2, 'tackle', 1), event(4, 2, 'possession_change', 1, from_team=0, to_team=1),
                  event(5, 3, 'pressure', 0, counts=[2, 0]), event(6, 4, 'shot', 1),
                  event(7, 5, 'pressure', 0, counts=[3, 0])]
        frozen = deepcopy(events)
        result = build_arc(events, 0, 4, False)
        self.assertEqual(result['counts'], {'completed_passes': [1, 0], 'shots': [0, 1],
            'tackles': [0, 1], 'possession_changes': 1, 'pressure_changes': 1, 'pressure_peak': [2, 0]})
        self.assertNotIn(7, result['source_event_ids'])
        self.assertEqual(events, frozen)

    def test_language_changes_words_but_never_ids_counts_scores_or_digest(self):
        events = [event(1, 0, 'kickoff'), event(2, 12, 'goal', 0, [1, 0])]
        results = [build_arc(events, 0, 15, False, code) for code in ('en', 'cs', 'de')]
        def factual(result):
            result = deepcopy(result)
            for key in ('title', 'narrative'):
                result.pop(key)
            for point in result['checkpoints']:
                point.pop('title'); point.pop('text')
            return result
        self.assertEqual(factual(results[0]), factual(results[1]))
        self.assertEqual(factual(results[0]), factual(results[2]))
        self.assertEqual(len({result['narrative'] for result in results}), 3)

    def test_long_match_has_bounded_checkpoints_and_citations(self):
        events, score = [event(1, 0, 'kickoff')], [0, 0]
        for key in range(2, 102):
            score[key % 2] += 1
            events.append(event(key, key * 20, 'goal', key % 2, score[:]))
        result = build_arc(events, 0, 5400, True)
        self.assertEqual(len(result['checkpoints']), MAX_CHECKPOINTS)
        self.assertEqual(result['checkpoint_count'], 100)
        self.assertTrue(result['checkpoints_truncated'])
        self.assertEqual(result['checkpoints'][0]['event_id'], 2)
        self.assertEqual(result['checkpoints'][-1]['event_id'], 101)
        self.assertLessEqual(len(result['source_event_ids']), 21)

    def test_invalid_bounds_duplicate_ids_and_impossible_goal_are_rejected(self):
        for args in ((-1, 1, False, 'en'), (0, float('nan'), False, 'en'),
                     (0, 1, False, 'xx'), (0, 1, 'yes', 'en'), (2, 1, False, 'en')):
            with self.assertRaises(ValueError):
                build_arc([], *args)
        with self.assertRaises(ValueError):
            build_arc([event(1, 0, 'kickoff'), event(1, 1, 'shot')], 0, 2, False)
        with self.assertRaises(ValueError):
            build_arc([event(1, 0, 'kickoff'), event(2, 1, 'goal', 0, [2, 0])], 0, 2, False)

    def test_report_addition_keeps_original_fact_fingerprint_contract(self):
        from app import MatchSession
        from simulation import GeneratorSettings
        session = MatchSession(GeneratorSettings(42, 'counterattack'), wall_clock=lambda: 0)
        session.pump(12)
        report = session.reports.build(session.pipeline, 0, 12, False, None, 'en')
        self.assertEqual(report['fact_fingerprint'], sha256(json.dumps(report['facts'], sort_keys=True).encode()).hexdigest())
        self.assertEqual(report['story_arc']['counts']['shots'], report['facts']['shots'])
        self.assertEqual(report['story_arc']['counts']['completed_passes'], report['facts']['passes'])
        self.assertEqual(report['generated_from'], 'calculated_facts')
        self.assertIsNone(report['interpretation'])


class ArchiveArcTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'archive.sqlite3'
        self.db = sqlite3.connect(self.path)
        self.db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY,time REAL,payload BLOB)')
        self.identity = {'run_key': 'run-one', 'match_id': 'match-one'}
        self.add(event(1, 0, 'kickoff'))
        with store._arc_cache_lock:
            store._arc_cache.clear()

    def tearDown(self):
        self.db.close(); self.folder.cleanup()

    def add(self, item):
        self.db.execute('INSERT INTO events VALUES(?,?,?)', (item['id'], item['time'], store.pack(item)))
        self.db.commit()

    def test_cache_reuses_all_languages_and_returns_independent_copies(self):
        with patch.object(store, 'build_arc', wraps=build_arc) as build:
            first = store.archive_story_arc(self.path, self.db, self.identity, 'en')
            first['counts']['shots'][0] = 999
            with closing(sqlite3.connect(self.path)) as another:
                second = store.archive_story_arc(self.path, another, self.identity, 'cs')
            self.assertEqual(build.call_count, 7)
            self.assertEqual(second['counts']['shots'], [0, 0])
            self.assertNotEqual(first['title'], second['title'])

    def test_cache_invalidates_on_source_file_change_or_archive_identity(self):
        with patch.object(store, 'build_arc', wraps=build_arc) as build:
            first = store.archive_story_arc(self.path, self.db, self.identity, 'en')
            self.add(event(2, 5, 'shot'))
            second = store.archive_story_arc(self.path, self.db, self.identity, 'en')
            self.assertNotEqual(first['coverage']['source_sha256'], second['coverage']['source_sha256'])
            self.assertEqual(second['counts']['shots'], [1, 0])
            store.archive_story_arc(self.path, self.db, {**self.identity, 'run_key': 'run-two'}, 'en')
            self.assertEqual(build.call_count, 21)

    def test_cache_is_bounded_across_archive_identities(self):
        for index in range(8):
            store.archive_story_arc(self.path, self.db, {**self.identity, 'run_key': str(index)}, 'en')
        self.assertEqual(len(store._arc_cache), store._ARC_CACHE_LIMIT)


if __name__ == '__main__':
    unittest.main()
