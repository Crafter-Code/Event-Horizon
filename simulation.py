                                                                         

                                                                             
                                                                            
                                                                          
   

from dataclasses import dataclass
import hashlib
import json
import math
import random
from scenarios import profile, ScenarioDirector


LENGTH, WIDTH = 105.0, 68.0
GOAL_HALF = 3.66
PRESS_RADIUS = 5.0
PLAYER_SPEED = 6.2
PASS_SPEED, SHOT_SPEED = 16.0, 25.0
TEAMS = ("Blue", "Red")
FORMATION = (
    (5, 34), (25, 8), (23, 25), (23, 43), (25, 60),
    (43, 15), (44, 34), (43, 53), (65, 9), (69, 34), (65, 59),
)
MODEL_VERSION = 'eh-sim-5'
STEP_SECONDS = .05


@dataclass(frozen=True)
class GeneratorSettings:
    seed: int = 42
    scenario: str = 'open_play'

    def __post_init__(self):
        if type(self.seed) is not int or not 0 <= self.seed <= 4294967295:
            raise ValueError('Seed must be an integer from 0 to 4294967295.')
        profile(self.scenario)

    def as_dict(self):
        result = {'seed': self.seed, 'model_version': MODEL_VERSION, 'step_seconds': STEP_SECONDS}
                                                                               
                                                                                 
        if self.scenario != 'open_play':
            definition = profile(self.scenario)
            result.update(scenario=self.scenario, scenario_version=definition['version'],
                          scenario_sha256=definition['sha256'])
        return result


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def move_toward(start, target, step):
    length = distance(start, target)
    if length <= step:
        return tuple(target)
    return (start[0] + (target[0] - start[0]) * step / length,
            start[1] + (target[1] - start[1]) * step / length)


def clamp(value, low, high):
    return max(low, min(high, value))


@dataclass
class Player:
    team: int
    number: int
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0

    @property
    def position(self):
        return self.x, self.y


class Match:
    def __init__(self, settings=None):
        self.settings = settings if settings is not None else GeneratorSettings()
        self.match_id = hashlib.sha256(json.dumps(self.settings.as_dict(),sort_keys=True).encode()).hexdigest()[:16]
        self.rng = random.Random(self.settings.seed)
        self.scenario = profile(self.settings.scenario)
        self.director = ScenarioDirector(self.scenario)
        self.tick = 0
        self.events = []
        self.event_digest = hashlib.sha256()
        self.clock = 0.0
        self.period = 1
        self.finished = False
        self.players = []
        for team in range(2):
            for number, (x, y) in enumerate(FORMATION, 1):
                x = min(x, 43.0)
                self.players.append(Player(team, number, x if team == 0 else LENGTH - x, y))
        self.owner = 9
        self.players[self.owner].x = LENGTH / 2 - .65
        self.players[self.owner].y = WIDTH / 2
        self.ball = [LENGTH / 2, WIDTH / 2]
        self.possession_team = 0
        self.possession_time = [0.0, 0.0]
        self.in_play_time = 0.0
        self.score = [0, 0]
        self.attempts = [0, 0]
        self.completed = [0, 0]
        self.shots = [0, 0]
        self.saves = [0, 0]
        self.flight = None
        self.free_velocity = [0.0, 0.0]
        self.restart = None
        self.think_in = .6
        self.control_time = 0.0
        self.last_touch_team = 0
        self.recovery = [0.0] * 22
        self.trail = None
        self._pressure_state = (0, 0)
        self.director.initialize(self)
        if self.settings.scenario == 'open_play':
            self.event('Kick-off', 'Blue kick off from the centre spot.', kind='kickoff')
        else:
            self.event('Scenario starts', self.scenario['description']['en'], kind='kickoff',
                       actors=(self.owner,), details={'scenario_start': True, 'start_phase': 'in_play'})

    def direction(self, team):
        return (1 if team == 0 else -1) * (1 if self.period == 1 else -1)

    def local_x(self, x, team):
        return x if self.direction(team) == 1 else LENGTH - x

    def world_x(self, x, team):
        return self.local_x(x, team)

    def opponents_near(self, team, position=None, radius=PRESS_RADIUS):
        position = self.ball if position is None else position
        return [i for i, p in enumerate(self.players)
                if p.team != team and distance(p.position, position) <= radius]

    def pressure(self):
        counts = [0, 0]
        if not self.restart and not self.finished:
            counts[1 - self.possession_team] = len(self.opponents_near(self.possession_team))
        return counts

    def event(self, title, text, kind='match_event', actors=(), details=None, event_team=None):
        self.last_event = {'id': len(self.events) + 1, 'tick': self.tick,
                           'time': round(self.clock, 2), 'kind': kind,
                           'title': title, 'text': text,
                           'ball': [round(value, 6) for value in self.ball],
                           'team': self.possession_team if event_team is None else event_team,
                           'score': self.score[:], 'passes': self.completed[:],
                           'attempts': self.attempts[:], 'shots': self.shots[:],
                           'actors': [{'team': self.players[i].team, 'number': self.players[i].number}
                                      for i in dict.fromkeys(actors)],
                           'details': details or {}, 'match_id': self.match_id, 'period': self.period,
                           'frame': [{'team': p.team, 'number': p.number, 'x': round(p.x,3), 'y': round(p.y,3)} for p in self.players]}
        self.events.append(self.last_event)
        encoded = json.dumps(self.last_event, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')
        self.event_digest.update(encoded + b'\n')

    def take_control(self, index):
        if self.owner is not None and self.owner != index:
            self.recovery[self.owner] = 1.8
        self.owner = index
        self.possession_team = self.players[index].team
        self.last_touch_team = self.possession_team
        self.flight = None
        self.free_velocity = [0.0, 0.0]
        self.control_time = 0.0
        self.think_in = self.rng.uniform(1.5, 3.0)

    def pass_options(self):
        player = self.players[self.owner]
        direction = self.direction(player.team)
                                                                         
        defensive_line = sorted(self.local_x(p.x, player.team)
                                for p in self.players if p.team != player.team)[-2]
        options = []
        for index, receiver in enumerate(self.players):
            if receiver.team != player.team or index == self.owner:
                continue
            length = distance(self.ball, receiver.position)
            if length < 5 or length > 36:
                continue
            if self.local_x(receiver.x, player.team) > max(LENGTH / 2, defensive_line, self.local_x(self.ball[0], player.team)):
                continue
            dx, dy = receiver.x - self.ball[0], receiver.y - self.ball[1]
            clearance = 20.0
            for opponent in self.players:
                if opponent.team == player.team:
                    continue
                fraction = ((opponent.x - self.ball[0]) * dx + (opponent.y - self.ball[1]) * dy) / length ** 2
                if fraction < .03 or fraction > 1.05:
                    continue
                fraction = clamp(fraction, 0, 1)
                point = self.ball[0] + fraction * dx, self.ball[1] + fraction * dy
                clearance = min(clearance, distance(point, opponent.position))
            forward = (receiver.x - player.x) * direction
            value = forward * self.director.policy['forward_weight'] + min(clearance, 8) * 1.8 - abs(length - 17) * .12
            value += self.rng.uniform(-2, 2)
            if receiver.number == 1:
                value -= 4
            options.append((value, index))
        return sorted(options, reverse=True)

    def start_pass(self, receiver_index):
        player, receiver = self.players[self.owner], self.players[receiver_index]
        origin = tuple(self.ball)
                                                                          
        target = receiver.position
        self.attempts[player.team] += 1
        self.flight = {"kind": "pass", "team": player.team, "sender": self.owner,
                       "receiver": receiver_index, "origin": origin, "target": target,
                       "age": 0.0, "length": distance(origin, target),
                       'start_event_id': len(self.events) + 1, 'direction': self.direction(player.team)}
        self.trail = {"from": origin, "to": target, "until": self.clock + 4}
        sender = self.owner
        self.owner = None
        self.event('Pass — ' + TEAMS[player.team],
                   f'#{player.number} sends the ball towards #{receiver.number}. The pass is not complete yet.',
                   kind='pass_started', actors=(sender, receiver_index),
                   details={'origin': list(origin), 'target': list(target),
                            'direction': self.direction(player.team)})

    def can_shoot(self):
        if self.owner is None:
            return False
        team = self.players[self.owner].team
        goal = self.world_x(LENGTH, team), WIDTH / 2
        return distance(self.ball, goal) <= 24 and abs(self.ball[1] - WIDTH / 2) <= 15

    def start_shot(self):
        if not self.can_shoot():
            return False
        player = self.players[self.owner]
        goal_x = self.world_x(LENGTH, player.team)
        length = distance(self.ball, (goal_x, WIDTH / 2))
        pressure = len(self.opponents_near(player.team))
                                                                              
                                                                               
        aim = self.rng.uniform(-2.8, 2.8)
        error = self.rng.gauss(0, .65 + length * .055 + pressure * .45)
        target = (goal_x + self.direction(player.team) * .5, WIDTH / 2 + aim + error)
        self.shots[player.team] += 1
        self.flight = {"kind": "shot", "team": player.team, "sender": self.owner,
                       "origin": tuple(self.ball), "target": target, "age": 0.0}
        self.trail = {"from": tuple(self.ball), "to": target, "until": self.clock + 4}
        self.event("Shot — " + TEAMS[player.team],
                   f'Player #{player.number} shoots from {length:.0f} m. Opponents within 5 m: {pressure}.',
                   kind='shot', actors=(self.owner,), details={'distance_m': round(length,1), 'pressure_count': pressure})
        self.owner = None
        return True

    def player_targets(self):
        targets = []
        team = self.possession_team
        chasing = set()
        if self.owner is not None or (self.owner is None and self.flight is None):
            for side in range(2):
                if self.owner is not None and side == team:
                    continue
                candidates = [i for i, p in enumerate(self.players) if p.team == side and p.number != 1 and self.recovery[i] <= 0]
                chasing.update(sorted(candidates, key=lambda i: distance(self.players[i].position, self.ball))[:self.director.policy['chasers'] if self.owner is not None else 2])
        elif self.flight:
                                                                   
            side = 1 - self.flight["team"]
            candidates = [i for i, p in enumerate(self.players) if p.team == side and p.number != 1]
            chasing.update(sorted(candidates, key=lambda i: distance(self.players[i].position, self.ball))[:1])
        for index, p in enumerate(self.players):
            local_ball = self.local_x(self.ball[0], p.team)
            home_x, home_y = FORMATION[p.number - 1]
            if p.number == 1:
                x = 3.0 + clamp((local_ball - 40) * .04, 0, 3)
                y = WIDTH / 2 + (self.ball[1] - WIDTH / 2) * .22
                if (self.flight and self.flight["kind"] == "shot" and
                        self.flight["team"] != p.team and self.flight["age"] >= .18):
                    origin, target = self.flight["origin"], self.flight["target"]
                    keeper_x = self.world_x(x, p.team)
                    fraction = clamp((keeper_x - origin[0]) / (target[0] - origin[0]), 0, 1)
                    y = clamp(origin[1] + fraction * (target[1] - origin[1]), WIDTH / 2 - 5.5, WIDTH / 2 + 5.5)
            else:
                shift = (local_ball - LENGTH / 2) * .5
                x = clamp(home_x + shift + (5 if p.team == team else self.director.policy['defending_shift_m']), 7, 98)
                y = clamp(home_y + (self.ball[1] - WIDTH / 2) * .18, 4, WIDTH - 4)
            target = (self.world_x(x, p.team), y)
            if index in chasing:
                target = tuple(self.ball)
                if self.owner is not None:
                                                                             
                                                                   
                    goal_side = (self.world_x(0, p.team), WIDTH / 2)
                    target = move_toward(self.ball, goal_side, self.director.policy['closing_gap_m'])
            if self.flight and self.flight.get("receiver") == index:
                target = self.flight["target"]
            if index == self.owner:
                                                                               
                ahead = (p.x + self.direction(p.team) * 7, p.y)
                nearby = self.opponents_near(p.team, p.position, 9)
                if nearby:
                    nearest = min(nearby, key=lambda j: distance(p.position, self.players[j].position))
                    opponent = self.players[nearest]
                    gap = max(.2, distance(p.position, opponent.position))
                    ahead = (p.x + self.direction(p.team) * 3 + (p.x - opponent.x) / gap * 7,
                             p.y + (p.y - opponent.y) / gap * 7)
                target = (clamp(ahead[0], 2, LENGTH - 2), clamp(ahead[1], 4, WIDTH - 4))
            targets.append(target)
        return self.director.targets(self, targets)

    def move_players(self, targets, dt):
        for index, (player, target) in enumerate(zip(self.players, targets)):
            speed = 4.4 if index == self.owner else PLAYER_SPEED
            if player.number == 1:
                speed = 5.0
            elif self.owner is not None and player.team != self.possession_team and distance(player.position, self.ball) < 5:
                speed = self.director.policy['closing_mps']
            x, y = move_toward(player.position, target, speed * dt)
            player.vx, player.vy = (x - player.x) / dt, (y - player.y) / dt
            player.x, player.y = clamp(x, .5, LENGTH - .5), clamp(y, .5, WIDTH - .5)

    def advance_flight(self, dt):
        flight = self.flight
        flight["age"] += dt
        speed = SHOT_SPEED if flight["kind"] == "shot" else PASS_SPEED
        old = tuple(self.ball)
        new = move_toward(old, flight["target"], speed * dt)
                                                                                
        dx, dy = new[0] - old[0], new[1] - old[1]
        segment = dx * dx + dy * dy
        contacts = []
        for index, p in enumerate(self.players):
            if index == flight["sender"]:
                continue
            if p.team == flight["team"] and index != flight.get("receiver"):
                continue
            fraction = clamp(((p.x - old[0]) * dx + (p.y - old[1]) * dy) / segment, 0, 1) if segment else 0
            point = old[0] + fraction * dx, old[1] + fraction * dy
            radius = 1.25 if p.number == 1 and flight["kind"] == "shot" else .8
            if distance(point, p.position) <= radius:
                contacts.append((fraction, index, point))
        if contacts:
            _, index, point = min(contacts)
            self.ball = list(point)
            player = self.players[index]
            if player.team == flight["team"]:
                self.completed[player.team] += 1
                sender = self.players[flight["sender"]]
                forward = (point[0] - flight["origin"][0]) * self.direction(player.team)
                actual_length = distance(flight['origin'], point)
                text = f'#{sender.number} → #{player.number}, {actual_length:.0f} m. '
                text += f'Forward progress: {forward:.0f} m.' if forward > 1 else 'The team kept the ball with a lateral or backward pass.'
                title, kind = "Completed pass — " + TEAMS[player.team], 'pass_completed'
            elif flight["kind"] == "shot":
                if player.number == 1:
                    self.saves[player.team] += 1
                    title, kind = "Save — " + TEAMS[player.team], 'save'
                    text = 'The goalkeeper met the ball on its shot trajectory and took possession.'
                else:
                    title, kind = 'Shot blocked', 'shot_blocked'
                    text = f'{TEAMS[player.team]}, #{player.number}, blocked the trajectory and won the ball.'
            else:
                title, kind = "Interception — " + TEAMS[player.team], 'interception'
                text = f'#{player.number} intercepted the pass trajectory. Possession switched to their team.'
            self.take_control(index)
            details = {}
            if flight['kind'] == 'pass':
                details = {'pass_start_id': flight['start_event_id'],
                           'origin': list(flight['origin']), 'end': list(point),
                           'direction': flight['direction']}
            self.event(title, text, kind=kind, actors=(flight['sender'], index), details=details)
            return
        self.ball = list(new)
        if self.check_boundary(old):
            return
        if distance(new, flight["target"]) < .01:
            self.flight = None
            if flight["kind"] == "pass":
                self.event("Incomplete pass — " + TEAMS[flight["team"]], 'The intended receiver did not control the ball. The teams contest the loose ball.', kind='pass_incomplete',
                           details={'pass_start_id': flight['start_event_id']})
            self.free_velocity = [0.0, 0.0]

    def check_boundary(self, previous):
        x, y = self.ball
        if 0 <= x <= LENGTH and 0 <= y <= WIDTH:
            return False
        if x < 0 or x > LENGTH:
            end = 0 if x < 0 else LENGTH
            fraction = (end - previous[0]) / (x - previous[0]) if x != previous[0] else 1
            crossing_y = previous[1] + fraction * (y - previous[1])
            attacking = next(team for team in range(2) if self.world_x(LENGTH, team) == end)
            if self.flight and self.flight["kind"] == "shot" and abs(crossing_y - WIDTH / 2) <= GOAL_HALF:
                self.score[attacking] += 1
                self.event("Goal — " + TEAMS[attacking], 'The shot crossed the goal line between the posts. The opponent will restart from the centre.', kind='goal', actors=(self.flight['sender'],))
                self.start_restart("kickoff", 1 - attacking, (LENGTH / 2, WIDTH / 2))
            elif self.last_touch_team == attacking:
                defending = 1 - attacking
                self.event("Goal kick — " + TEAMS[defending], 'The ball crossed the end line. The goalkeeper will restart play.', kind='goal_kick')
                self.start_restart("goal_kick", defending, (self.world_x(5.5, defending), WIDTH / 2))
            else:
                self.event("Corner — " + TEAMS[attacking], 'The ball crossed the end line after touching the defending team.', kind='corner')
                self.start_restart("corner", attacking, (clamp(end, .5, LENGTH - .5), .5 if y < WIDTH / 2 else WIDTH - .5))
        else:
            team = 1 - self.last_touch_team
            self.event("Throw-in — " + TEAMS[team], 'The ball crossed the touchline. The opponent will take a throw-in.', kind='throw_in')
            self.start_restart("throw_in", team, (clamp(x, 1, LENGTH - 1), .5 if y < 0 else WIDTH - .5))
        return True

    def start_restart(self, kind, team, point):
        self.owner = None
        self.flight = None
        self.free_velocity = [0.0, 0.0]
        if kind == "kickoff":
            taker = team * 11 + 9
        elif kind == "goal_kick":
            taker = team * 11
        else:
            taker = min((i for i, p in enumerate(self.players) if p.team == team and p.number != 1),
                        key=lambda i: distance(self.players[i].position, point))
        targets = self.player_targets()
        if kind == "kickoff":
            for i, p in enumerate(self.players):
                hx, hy = FORMATION[p.number - 1]
                targets[i] = (self.world_x(min(hx, 43), p.team), hy)
        targets[taker] = point
        travel = max(distance(p.position, target) / (5 if p.number == 1 else PLAYER_SPEED)
                     for p, target in zip(self.players, targets))
        self.restart = {"kind": kind, "team": team, "point": point, "taker": taker,
                        "targets": targets, "remaining": max(3, travel + 1, distance(self.ball, point) / 15 + .5)}

    def metadata(self):
        return {'match_id': self.match_id, 'settings': self.settings.as_dict(),
                'scenario': {k: self.scenario[k] for k in ('id', 'version', 'title', 'description', 'expectations')},
                'match_parameters': {'duration_s': 5400, 'half_s': 2700, 'players_per_team': 11,
                                     'player_max_mps': PLAYER_SPEED, 'pass_mps': PASS_SPEED,
                                     'shot_mps': SHOT_SPEED, 'pressure_radius_m': PRESS_RADIUS,
                                     'initial_phase': 'kickoff' if self.settings.scenario == 'open_play' else 'in_play'},
                'pitch': {'length_m': LENGTH, 'width_m': WIDTH},
                'teams': [{'id': team, 'name': TEAMS[team],
                           'lineup': [{'id': f'{team}:{n}', 'number': n,
                                       'role': 'goalkeeper' if n == 1 else 'outfield'} for n in range(1,12)]}
                          for team in (0,1)]}

    def advance(self, dt=STEP_SECONDS):
        previous_team, previous_tick = self.possession_team, self.tick
        self._advance(dt)
        if self.tick == previous_tick:
            return
        if self.possession_team != previous_team:
            actors = (self.owner,) if self.owner is not None else ()
            self.event('Possession change', 'The ball changed teams.', kind='possession_change', actors=actors,
                       details={'from_team': previous_team, 'to_team': self.possession_team})
        pressure = tuple(self.pressure())
        if pressure != self._pressure_state:
            pressing = 1 - self.possession_team
            opponents = tuple(self.opponents_near(self.possession_team)) if not self.restart and not self.finished else ()
            self.event('Pressure change', 'The number of opponents within 5 m changed.',
                       kind='pressure', actors=opponents,
                       details={'counts': list(pressure), 'radius_m': PRESS_RADIUS, 'pressing_team': pressing},
                       event_team=pressing)
            self._pressure_state = pressure

    def _advance(self, dt=STEP_SECONDS):
        if dt != STEP_SECONDS:
            raise ValueError(f'The model requires a fixed {STEP_SECONDS} second step')
        if self.finished:
            return
        self.recovery = [max(0, value - dt) for value in self.recovery]
        old_clock = self.clock
        self.tick += 1
        self.clock = min(5400.0, self.tick * STEP_SECONDS)
        if old_clock < 2700 <= self.clock and self.period == 1:
            self.period = 2
            self.event("Second half", 'The teams changed ends. Red will kick off from the centre.', kind='second_half')
            self.start_restart("kickoff", 1, (LENGTH / 2, WIDTH / 2))
        if self.clock >= 5400:
            self.finished = True
            self.event("Match finished", 'The final score and statistics of the synthetic match are displayed.', kind='full_time')
            return
        if self.restart:
            restart = self.restart
            self.move_players(restart["targets"], dt)
            self.ball = list(move_toward(self.ball, restart["point"], 15 * dt))
            restart["remaining"] -= dt
            if restart["remaining"] <= 0 and distance(self.players[restart["taker"]].position, self.ball) <= 1:
                self.take_control(restart["taker"])
                self.restart = None
                self.event("Restart — " + TEAMS[self.possession_team], 'The team restarted play after the stoppage.', kind='restart_taken', actors=(self.owner,))
            return
        self.in_play_time += dt
        self.possession_time[self.possession_team] += dt
        self.move_players(self.player_targets(), dt)
        if self.flight:
            self.advance_flight(dt)
        elif self.owner is None:
            nearest = min(range(22), key=lambda i: distance(self.players[i].position, self.ball))
            if distance(self.players[nearest].position, self.ball) <= 1:
                self.take_control(nearest)
                self.event("Ball recovery — " + TEAMS[self.possession_team], f'#{self.players[nearest].number} reached the loose ball first.', kind='ball_recovered', actors=(nearest,))
        else:
            player = self.players[self.owner]
            nearest = min((p for p in self.players if p.team != player.team),
                          key=lambda p: distance(p.position, player.position))
            gap = distance(player.position, nearest.position)
            if gap < 5:
                                                                            
                foot = (player.x + (player.x - nearest.x) / max(gap, .1) * .65,
                        player.y + (player.y - nearest.y) / max(gap, .1) * .65)
            else:
                foot = player.x + self.direction(player.team) * .65, player.y
            self.ball = list(move_toward(self.ball, foot, 12 * dt))
            self.control_time += dt
            nearby = self.opponents_near(player.team, self.ball, 1.25)
            nearby = [i for i in nearby if self.recovery[i] <= 0]
            if nearby and self.control_time > .4 and self.rng.random() < 1 - math.exp(-self.director.policy['tackle_rate'] * dt):
                index = min(nearby, key=lambda i: distance(self.players[i].position, self.ball))
                previous_owner = self.owner
                self.take_control(index)
                self.event("Tackle — " + TEAMS[self.possession_team], f'#{self.players[index].number} closed down the opponent and won the ball.', kind='tackle', actors=(previous_owner, index))
                return
            if self.director.act(self):
                return
            self.think_in -= dt / self.director.policy['decision_scale']
            pressure = len(self.opponents_near(player.team))
            if self.think_in <= 0 or (pressure >= 2 and self.control_time > 1.2):
                if self.can_shoot() and self.rng.random() < .22:
                    self.start_shot()
                else:
                    options = self.pass_options()
                    if options and (pressure or self.rng.random() < .8 or player.number == 1):
                        self.start_pass(options[0][1])
                    else:
                        self.think_in = self.rng.uniform(.8, 1.5)

    def snapshot(self):
        first = round(100 * self.possession_time[0] / self.in_play_time) if self.in_play_time else 50
        return {
            "clock": round(self.clock, 2), "period": self.period, "finished": self.finished,
            "players": [{"team": p.team, "number": p.number, "x": round(p.x, 3), "y": round(p.y, 3)} for p in self.players],
            "ball": [round(value, 3) for value in self.ball], "owner": self.owner,
            "team": self.possession_team, "score": self.score[:],
            "passes": self.completed[:], "attempts": self.attempts[:], "shots": self.shots[:],
            "possession": [first, 100 - first], "pressure": self.pressure(),
            "event": self.last_event.copy(),
            "trail": self.trail if self.trail and self.trail["until"] > self.clock else None,
            "phase": ("Match finished" if self.finished else "Play stopped" if self.restart else
                      "Shot" if self.flight and self.flight["kind"] == "shot" else
                      "Pass" if self.flight else "Ball held by «" + TEAMS[self.possession_team] + "»"),
        }
