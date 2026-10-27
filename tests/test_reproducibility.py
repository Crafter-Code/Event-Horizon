                                                                             

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from app import MatchSession
from simulation import GeneratorSettings, Match, STEP_SECONDS


class ReproducibilityTests(unittest.TestCase):
    def test_identical_full_matches_have_identical_events_and_statistics(self):
        first = Match(GeneratorSettings(42))
        second = Match(GeneratorSettings(42))
        for tick in range(int(5400 / STEP_SECONDS)):
            first.advance()
                                                                           
            if tick % 37 == 0:
                second.snapshot()
            second.advance()
            if tick % 600 == 0:
                self.assertEqual(first.snapshot(), second.snapshot())
        self.assertTrue(first.finished and second.finished)
        self.assertEqual(first.events, second.events)
        self.assertEqual(first.snapshot(), second.snapshot())
        self.assertEqual(first.event_digest.hexdigest(), second.event_digest.hexdigest())
        kinds = {event['kind'] for event in first.events}
        self.assertTrue({'pass_started', 'pass_completed', 'shot', 'goal', 'second_half', 'full_time'} <= kinds)
        self.assertEqual([e['id'] for e in first.events], list(range(1, len(first.events) + 1)))
        self.assertTrue(all(a['tick'] <= b['tick'] for a, b in zip(first.events, first.events[1:])))
        digest = hashlib.sha256()
        for event in first.events:
            digest.update(json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode() + b'\n')
        self.assertEqual(digest.hexdigest(), first.event_digest.hexdigest())
        print(f'\nIdentical 90-minute runs: {len(first.events)} events, score={first.score}, SHA-256={digest.hexdigest()}')

    def test_same_seed_in_fresh_processes_and_different_hash_seeds(self):
        script = '''
import json, random
from simulation import Match, GeneratorSettings
random.seed(9999)
m = Match(GeneratorSettings(42))
for _ in range(2400): m.advance()
print(json.dumps([m.snapshot(), m.event_digest.hexdigest()], sort_keys=True))
'''
        root = Path(__file__).resolve().parents[1]
        first = subprocess.check_output([sys.executable, '-B', '-c', script], cwd=root,
                                        env={**os.environ, 'PYTHONHASHSEED': '1'})
        second = subprocess.check_output([sys.executable, '-B', '-c', script], cwd=root,
                                         env={**os.environ, 'PYTHONHASHSEED': '852'})
        self.assertEqual(first, second)

    def test_different_seeds_change_the_match(self):
        first, second = Match(GeneratorSettings(42)), Match(GeneratorSettings(43))
        for _ in range(1200):
            first.advance()
            second.advance()
        self.assertNotEqual(first.events, second.events)
        self.assertNotEqual(first.event_digest.hexdigest(), second.event_digest.hexdigest())

    def test_seed_validation(self):
        for seed in (-1, 4294967296, 1.5, True, None, '42'):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                GeneratorSettings(seed)
        self.assertEqual(GeneratorSettings(0).seed, 0)
        self.assertEqual(GeneratorSettings(4294967295).seed, 4294967295)

    def test_variable_steps_cannot_change_a_replay(self):
        match = Match()
        for dt in (.1, .01, 0, -1):
            with self.assertRaises(ValueError):
                match.advance(dt)
        self.assertEqual(match.tick, 0)
        self.assertEqual(match.clock, 0)

    def test_scheduler_jitter_and_poll_frequency_do_not_change_events(self):
        regular, uneven = MatchSession(wall_clock=lambda: 0), MatchSession(wall_clock=lambda: 0)
        for tick in range(1, 1201):
            regular.pump(tick * STEP_SECONDS)
            if tick % 3 == 0:
                regular.snapshot()
        for now in (.013, .122, .21, .58, 1.02, 1.33, 5.03, 12.7, 19.2, 37.98, 60):
            uneven.pump(now)
        self.assertEqual(regular.match.snapshot(), uneven.match.snapshot())
        self.assertEqual(regular.match.events, uneven.match.events)
        self.assertEqual(regular.match.tick, 1200)
        self.assertEqual(regular.match.clock, 60)

    def test_events_arrive_gradually_and_have_no_future_data(self):
        live = MatchSession(wall_clock=lambda: 0)
        initial = live.snapshot()
        self.assertEqual(initial['clock'], 0)
        self.assertEqual(initial['event_count'], 1)
        self.assertEqual(initial['attempts'], [0, 0])
        live.pump(.49)
        early = live.snapshot(after=1, run_id=live.run_id)
        self.assertEqual(early['events'], [])
        self.assertEqual(early['clock'], .45)
        self.assertEqual(early['attempts'], [0, 0])
        live.pump(3)
        later = live.snapshot(after=1, run_id=live.run_id)
        self.assertGreater(len(later['events']), 0)
        self.assertGreater(sum(later['attempts']), 0)
        self.assertTrue(all(e['time'] <= later['clock'] for e in later['events']))
        self.assertEqual(later['events'][0]['id'], 2)
        no_duplicates = live.snapshot(after=later['event_count'], run_id=live.run_id)
        self.assertEqual(no_duplicates['events'], [])
        self.assertEqual(no_duplicates['clock'], later['clock'])

    def test_statistics_update_at_the_event_not_after_the_match(self):
        live = MatchSession(wall_clock=lambda: 0)
        live.pump(2)
        snapshot = live.snapshot()
        events = snapshot['events']
        self.assertIn('pass_started', [event['kind'] for event in events])
        self.assertEqual(snapshot['attempts'], events[-1]['attempts'])
        self.assertEqual(snapshot['passes'], events[-1]['passes'])
        self.assertLess(snapshot['clock'], 5400)
        self.assertFalse(snapshot['finished'])

    def test_replay_resets_settings_rng_clock_and_statistics(self):
        now = [0]
        live = MatchSession(GeneratorSettings(17), wall_clock=lambda: now[0])
        live.pump(90)
        first = live.match.snapshot()
        events = copy.deepcopy(live.match.events)
        digest = live.match.event_digest.hexdigest()
        previous_run, previous_count = live.run_id, len(events)
        now[0] = 150
        live.restart()
        reset = live.snapshot(after=previous_count, run_id=previous_run)
        self.assertTrue(reset['reset'])
        self.assertEqual(reset['clock'], 0)
        self.assertEqual(reset['settings']['seed'], 17)
        self.assertEqual(reset['event_count'], 1)
        self.assertEqual(reset['attempts'], [0, 0])
        self.assertEqual(reset['shots'], [0, 0])
        live.pump(240)
        self.assertEqual(first, live.match.snapshot())
        self.assertEqual(events, live.match.events)
        self.assertEqual(digest, live.match.event_digest.hexdigest())

    def test_changing_settings_and_invalid_restart(self):
        live = MatchSession(wall_clock=lambda: 0)
        live.pump(20)
        before = live.match.snapshot()
        old_run = live.run_id
        with self.assertRaises(ValueError):
            live.restart(seed=-1)
        self.assertEqual(live.run_id, old_run)
        self.assertEqual(live.match.snapshot(), before)
        live.restart(seed=0)
        self.assertEqual(live.match.settings.seed, 0)
        self.assertEqual(live.match.clock, 0)

    def test_match_end_does_not_emit_duplicate_events(self):
        live = MatchSession(wall_clock=lambda: 0)
        live.pump(5400)
        events = len(live.match.events)
        digest = live.match.event_digest.hexdigest()
        live.pump(7200)
        self.assertEqual(len(live.match.events), events)
        self.assertEqual(live.match.event_digest.hexdigest(), digest)
        self.assertEqual(sum(e['kind'] == 'full_time' for e in live.match.events), 1)


if __name__ == '__main__':
    unittest.main()
