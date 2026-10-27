                                                                          

import math
import unittest

from simulation import LENGTH, WIDTH, PLAYER_SPEED, STEP_SECONDS, GeneratorSettings, Match, distance


def clear_scene():
    match = Match()
    match.rng.seed(17)
                                                                     
    for i, player in enumerate(match.players):
        player.x, player.y = 10 + (i % 11) * 7, 8 if i < 11 else 60
    match.owner = 6
    match.possession_team = 0
    match.players[6].x, match.players[6].y = 30, 34
    match.ball = [30.65, 34]
    return match


def finish_flight(match):
    for _ in range(200):
        if match.flight is None:
            break
        match.advance_flight(.05)
    else:
        raise AssertionError('Flight did not finish')


class MatchTests(unittest.TestCase):
    def test_full_lineups_and_kickoff(self):
        match = Match()
        self.assertEqual([sum(p.team == team for p in match.players) for team in (0, 1)], [11, 11])
        self.assertEqual(match.ball, [LENGTH / 2, WIDTH / 2])
        self.assertLess(distance(match.players[match.owner].position, match.ball), 1)
        self.assertTrue(all(p.x >= LENGTH / 2 for p in match.players if p.team == 1))
        self.assertTrue(all(distance(p.position, match.ball) >= 9.15 for p in match.players if p.team == 1))

    def test_pass_counts_only_after_reception(self):
        match = clear_scene()
        match.players[9].x, match.players[9].y = 47, 34
        match.start_pass(9)
        self.assertEqual(match.attempts, [1, 0])
        self.assertEqual(match.completed, [0, 0])
        match.advance_flight(.05)
        self.assertGreater(match.ball[0], 30.65)
        self.assertLess(match.ball[0], 47)
        self.assertEqual(match.completed, [0, 0])
        finish_flight(match)
        self.assertEqual(match.completed, [1, 0])
        self.assertEqual(match.owner, 9)

    def test_defender_intercepts_actual_pass_path(self):
        match = clear_scene()
        match.players[9].x, match.players[9].y = 47, 34
        match.players[15].x, match.players[15].y = 39, 34
        match.start_pass(9)
        finish_flight(match)
        self.assertEqual(match.owner, 15)
        self.assertEqual(match.possession_team, 1)
        self.assertEqual(match.completed, [0, 0])
        self.assertEqual(match.attempts, [1, 0])

    def test_distant_defender_does_not_intercept(self):
        match = clear_scene()
        match.players[9].x, match.players[9].y = 47, 34
        match.players[15].x, match.players[15].y = 39, 37
        match.start_pass(9)
        finish_flight(match)
        self.assertEqual(match.owner, 9)

    def test_no_reception_is_not_a_completed_pass(self):
        match = clear_scene()
        match.players[9].x, match.players[9].y = 47, 34
        match.start_pass(9)
        match.players[9].y = 45
        finish_flight(match)
        self.assertEqual(match.completed, [0, 0])
        self.assertIsNone(match.owner)

    def test_pressure_measures_nearby_opponents(self):
        match = clear_scene()
        match.players[15].x, match.players[15].y = 33, 34
        match.players[16].x, match.players[16].y = 30.65, 38.9
        self.assertEqual(match.pressure(), [0, 2])
        match.players[16].y = 39.1
        self.assertEqual(match.pressure(), [0, 1])
        match.take_control(15)
        self.assertEqual(match.pressure(), [1, 0])

    def test_no_shot_from_own_half(self):
        match = clear_scene()
        self.assertFalse(match.start_shot())
        self.assertEqual(match.shots, [0, 0])
        self.assertIsNone(match.flight)

    def test_shot_only_scores_when_ball_crosses_goal(self):
        match = clear_scene()
        match.players[6].x = 90
        match.ball = [90.65, 34]
        self.assertTrue(match.start_shot())
        match.flight['target'] = (105.5, 34)
        self.assertEqual(match.shots, [1, 0])
        self.assertEqual(match.score, [0, 0])
        finish_flight(match)
        self.assertEqual(match.score, [1, 0])
        self.assertEqual(match.restart['kind'], 'kickoff')
        self.assertEqual(match.restart['team'], 1)

    def test_wide_shot_does_not_score(self):
        match = clear_scene()
        match.ball = [90, 34]
        match.start_shot()
        match.flight['target'] = (105.5, 40)
        finish_flight(match)
        self.assertEqual(match.score, [0, 0])
        self.assertEqual(match.restart['kind'], 'goal_kick')

    def test_keeper_save_prevents_goal(self):
        match = clear_scene()
        match.ball = [90, 34]
        match.players[11].x, match.players[11].y = 102, 34
        match.start_shot()
        match.flight['target'] = (105.5, 34)
        finish_flight(match)
        self.assertEqual(match.owner, 11)
        self.assertEqual(match.saves, [0, 1])
        self.assertEqual(match.score, [0, 0])

    def test_defender_blocks_shot(self):
        match = clear_scene()
        match.ball = [90, 34]
        match.players[15].x, match.players[15].y = 96, 34
        match.start_shot()
        match.flight['target'] = (105.5, 34)
        finish_flight(match)
        self.assertEqual(match.owner, 15)
        self.assertEqual(match.shots, [1, 0])
        self.assertEqual(match.score, [0, 0])

    def test_goal_against_left_side(self):
        match = clear_scene()
        match.owner, match.possession_team, match.last_touch_team = 17, 1, 1
        match.ball = [15, 34]
        match.players[17].x, match.players[17].y = 15.65, 34
        match.start_shot()
        match.flight['target'] = (-.5, 34)
        finish_flight(match)
        self.assertEqual(match.score, [0, 1])
        self.assertEqual(match.restart['team'], 0)

    def test_corner_and_throw_in_follow_last_touch(self):
        match = clear_scene()
        match.last_touch_team = 1
        match.ball = [105.2, 20]
        match.check_boundary((104, 20))
        self.assertEqual(match.restart['kind'], 'corner')
        self.assertEqual(match.restart['team'], 0)
        match = clear_scene()
        match.ball = [40, -.1]
        match.check_boundary((40, .1))
        self.assertEqual(match.restart['kind'], 'throw_in')
        self.assertEqual(match.restart['team'], 1)

    def test_stoppage_does_not_add_possession_time(self):
        match = clear_scene()
        match.start_restart('goal_kick', 1, (99.5, 34))
        match.advance(.05)
        self.assertEqual(match.possession_time, [0, 0])
        self.assertEqual(match.pressure(), [0, 0])

    def test_halftime_changes_direction_without_teleporting(self):
        match = Match()
        match.tick = int(2700 / STEP_SECONDS) - 1
        match.clock = match.tick * STEP_SECONDS
        before = [p.position for p in match.players]
        ball = match.ball[:]
        match.advance(.05)
        self.assertEqual(match.period, 2)
        self.assertEqual(match.direction(0), -1)
        self.assertEqual(match.restart['team'], 1)
        for old, player in zip(before, match.players):
            self.assertLessEqual(distance(old, player.position), PLAYER_SPEED * .05 + 1e-8)
        self.assertLessEqual(distance(ball, match.ball), 25 * .05 + 1e-8)

    def test_complete_matches_remain_physically_and_numerically_consistent(self):
        for seed in range(3):
            match = Match(GeneratorSettings(seed))
            for _ in range(int(5400 / STEP_SECONDS) + 1):
                previous = [p.position for p in match.players]
                ball = match.ball[:]
                match.advance()
                for old, player in zip(previous, match.players):
                    self.assertLessEqual(distance(old, player.position), PLAYER_SPEED * STEP_SECONDS + 1e-7)
                    self.assertTrue(0 <= player.x <= LENGTH and 0 <= player.y <= WIDTH)
                self.assertLessEqual(distance(ball, match.ball), 25 * STEP_SECONDS + 1e-7)
                self.assertAlmostEqual(sum(match.possession_time), match.in_play_time, places=5)
                for team in (0, 1):
                    self.assertLessEqual(match.completed[team], match.attempts[team])
                    self.assertLessEqual(match.score[team], match.shots[team])
                if match.owner is not None:
                    self.assertEqual(match.possession_team, match.players[match.owner].team)
                    self.assertLessEqual(distance(match.players[match.owner].position, match.ball), 1.8)
            self.assertTrue(match.finished)
            self.assertEqual(match.clock, 5400)
            self.assertGreater(sum(match.completed), 0)
            self.assertGreater(sum(match.shots), 0)
            self.assertEqual(sum(match.snapshot()['possession']), 100)
            print(f'\nMatch {seed}: score={match.score}, passes={match.completed}/{match.attempts}, shots={match.shots}')


if __name__ == '__main__':
    unittest.main()
