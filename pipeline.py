                                                                                  

                                                                             
                                                                               
                                                 
   

from collections import ChainMap, deque
from copy import copy, deepcopy
import hashlib
import json
import math
import time
from pass_quality import assess

from insights import MatchInsights
from context import GameContext
from simulation import STEP_SECONDS, TEAMS


class EventContractError(ValueError):
    pass


def point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise EventContractError('Expected two coordinates')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise EventContractError('Coordinates must be finite numbers')
    return tuple(value)


class MetricProjector:
                                                                                 

    def __init__(self):
        self.score = [0, 0]
        self.attempts = [0, 0]
        self.completed = [0, 0]
        self.shots = [0, 0]
        self.saves = [0, 0]
        self.possession_time = [0.0, 0.0]
        self.in_play_time = 0.0
        self.possession_team = 0
        self.passes_in_possession = 0
        self.open_passes = {}
        self.last_id = 0
        self.last_time = 0.0
        self.digests = {}

    def consume(self, event):
                                                                                 
        if not isinstance(event, dict):
            raise EventContractError('Expected an event object')
        event_id, timestamp, team = event.get('id'), event.get('time'), event.get('team')
        if type(event_id) is not int or event_id < 1:
            raise EventContractError('Invalid event id')
        if type(timestamp) not in (float, int) or not math.isfinite(timestamp) or timestamp < 0:
            raise EventContractError('Invalid event time')
        if type(team) is not int or team not in (0, 1):
            raise EventContractError('Invalid team')
        point(event.get('ball'))
        try:
            digest = hashlib.sha256(json.dumps(event, sort_keys=True, ensure_ascii=False,
                                               allow_nan=False).encode()).hexdigest()
        except (ValueError, TypeError) as error:
            raise EventContractError('Invalid event representation') from error
        if event_id in self.digests:
            if self.digests[event_id] != digest:
                raise EventContractError('Conflicting redelivery')
            return False
        if event_id != self.last_id + 1 or timestamp < self.last_time:
            raise EventContractError('Missing or out-of-order event')
        kind, details = event.get('kind'), event.get('details', {})
        kinds = {'kickoff', 'pass_started', 'pass_completed', 'pass_incomplete',
                 'interception', 'shot', 'goal', 'save', 'shot_blocked', 'goal_kick',
                 'corner', 'throw_in', 'restart_taken', 'tackle', 'ball_recovered',
                 'second_half', 'full_time', 'pressure', 'possession_change'}
        if not isinstance(kind, str) or kind not in kinds or not isinstance(details, dict):
            raise EventContractError('Invalid event type or details')
        actors = event.get('actors')
        if not isinstance(actors, list) or any(
                not isinstance(a, dict) or type(a.get('team')) is not int or a['team'] not in (0, 1)
                or type(a.get('number')) is not int or not 1 <= a['number'] <= 11 for a in actors):
            raise EventContractError('Invalid event participants')
        if kind == 'pressure':
            counts = details.get('counts')
            if (not isinstance(counts, list) or len(counts) != 2
                    or any(type(n) is not int or not 0 <= n <= 11 for n in counts)
                    or details.get('radius_m') != 5 or details.get('pressing_team') != team
                    or counts[1-team] != 0 or len(actors) != counts[team]
                    or any(a['team'] != team for a in actors)):
                raise EventContractError('Invalid pressure event')
        if kind == 'possession_change':
            if (details.get('from_team') not in (0, 1) or details.get('to_team') != team
                    or details['from_team'] == team):
                raise EventContractError('Invalid possession change')
        if kind == 'pass_started':
            origin, target = point(details.get('origin')), point(details.get('target'))
            if (type(details.get('direction')) is not int or details['direction'] not in (-1, 1)
                    or math.dist(origin, target) <= 0 or self.open_passes):
                raise EventContractError('Invalid pass geometry')
            if len(actors) != 2 or any(a['team'] != team for a in actors) or actors[0] == actors[1]:
                raise EventContractError('Invalid pass participants')
        if kind in ('pass_completed', 'pass_incomplete', 'interception'):
            start_id = details.get('pass_start_id')
            if type(start_id) is not int:
                raise EventContractError('Invalid pass reference')
            start = self.open_passes.get(start_id)
            if start is None:
                raise EventContractError('Pass outcome has no matching start')
            if kind == 'pass_completed':
                if start['team'] != team or details.get('direction') != start['details']['direction']:
                    raise EventContractError('Pass completion has the wrong team or direction')
                if point(details.get('origin')) != point(start['details']['origin']):
                    raise EventContractError('Pass origin changed')
                end = point(details.get('end'))
                if math.dist(end, point(event['ball'])) > .00001:
                    raise EventContractError('Pass endpoint does not match the ball')
                if actors != start['actors']:
                    raise EventContractError('Pass participants changed')
            elif kind == 'interception' and start['team'] == team:
                raise EventContractError('Interception must change team')
            elif kind == 'pass_incomplete' and start['team'] != team:
                raise EventContractError('Incomplete pass has the wrong team')
                                                                                    
        if kind == 'pass_started':
            self.attempts[team] += 1
            self.open_passes[event_id] = deepcopy(event)
        elif kind == 'pass_completed':
            self.completed[team] += 1
            self.passes_in_possession += 1
            del self.open_passes[start_id]
        elif kind in ('pass_incomplete', 'interception'):
            del self.open_passes[start_id]
        elif kind == 'shot':
            self.shots[team] += 1
        elif kind == 'goal':
            self.score[team] += 1
        elif kind == 'save':
            self.saves[team] += 1
        if kind in ('kickoff', 'restart_taken', 'pass_completed', 'interception', 'save', 'shot_blocked', 'tackle', 'ball_recovered'):
            if team != self.possession_team or kind in ('kickoff', 'restart_taken'):
                self.passes_in_possession = 0
            self.possession_team = team
        if kind in ('second_half', 'full_time', 'goal', 'goal_kick', 'corner', 'throw_in'):
            self.open_passes.clear()
        self.digests[event_id] = digest
        self.last_id, self.last_time = event_id, timestamp
        return True

    def accrue(self, active):
        if active:
            self.possession_time[self.possession_team] += STEP_SECONDS
            self.in_play_time += STEP_SECONDS

    def snapshot(self, players, ball, stopped):
        total = self.in_play_time
        first = round(self.possession_time[0] / total * 100) if total else 50
        pressure = [0, 0]
        if not stopped:
            pressure[1 - self.possession_team] = sum(
                p.team != self.possession_team and math.hypot(p.x - ball[0], p.y - ball[1]) <= 5
                for p in players)
        return {'score': self.score[:], 'attempts': self.attempts[:], 'passes': self.completed[:],
                'shots': self.shots[:], 'possession': [first, 100 - first], 'pressure': pressure}


class MatchPipeline:
    def __init__(self, match, timer=time.perf_counter):
        self.metrics = MetricProjector()
        self.insights = MatchInsights()
        self.events = []
        self.clock = 0.0
        self.tick = 0
        self.timer = timer
        self.receipts = deque(maxlen=100)
        self.displayed = set()
        self.revision = 0
        self.last_error = None
        self.moment_version = (0, 0)
        self.context = GameContext()
        self._receive(match)
        self.context.observe(match,self.metrics,False)

    @property
    def possession_time(self):
        return self.metrics.possession_time

    def advance(self, match, active):
        if match.tick != self.tick + 1:
            raise EventContractError('Pipeline requires consecutive model ticks')
                                                                           
        self.metrics.accrue(active)
        self.clock, self.tick = match.clock, match.tick
        self._receive(match)
        self.context.observe(match,self.metrics,active)
        if match.tick%1200==0:
            self.insights.context_change(self.context.window())

    def validate_next(self, match):
                                                                                    
        if match.tick != self.tick + 1:
            raise EventContractError('Pipeline requires consecutive model ticks')
        batch = match.events[self.metrics.last_id:]
        if not batch:
            return
        probe = copy(self.metrics)
        for key in ('score', 'attempts', 'completed', 'shots', 'saves'):
            setattr(probe, key, getattr(self.metrics, key)[:])
        probe.open_passes = self.metrics.open_passes.copy()
                                                                                 
        probe.digests = ChainMap({}, self.metrics.digests)
        for event in batch:
            if event['time'] > match.clock:
                raise EventContractError('Cannot receive a future event')
            probe.consume(event)

    def _receive(self, match):
        for event in match.events[self.metrics.last_id:]:
            if event['time'] > self.clock:
                raise EventContractError('Cannot receive a future event')
            started = self.timer()
            before = self.metrics.completed[:]
            if self.metrics.consume(event):
                self.events.append(deepcopy(event))
                self.revision += 1
                if event['kind'] == 'pass_completed':
                    self.receipts.append(self._explain_pass(event, before, started))
        self.insights.ingest(self)
        moment_version = (len(self.insights.moments), sum(m.revision for m in self.insights.moments.values()))
        if moment_version != self.moment_version:
            self.moment_version = moment_version
            self.revision += 1

    def _explain_pass(self, event, before, started):
        origin, end = point(event['details']['origin']), point(event['details']['end'])
        length = math.dist(origin, end)
        progress = (end[0] - origin[0]) * event['details']['direction']
        team = event['team']
        sender, receiver = event['actors'][:2]
        if progress >= 1:
            meaning = f'Forward progress towards the opposing goal: {progress:.1f} m.'
            label = 'Forward progress'
        elif progress <= -1:
            meaning = f'The ball travelled {abs(progress):.1f} m backwards along the pitch; the team kept possession.'
            label = 'Backward pass'
        else:
            meaning = 'The ball travelled mostly across the pitch; the team kept possession.'
            label = 'Lateral pass'
        explanation = (f"{TEAMS[team]}: #{sender['number']} → #{receiver['number']}, {length:.1f} m. {meaning} Completed passes in this possession: {self.metrics.passes_in_possession}.")
        elapsed = max(0, (self.timer() - started) * 1000)
        source=self.events[event['details']['pass_start_id']-1]
        quality=assess(origin,end,[(p['x'],p['y']) for p in source['frame'] if p['team']!=team],event['details']['direction'])
        return {'event_id': event['id'], 'start_event_id': event['details']['pass_start_id'],
                'time': event['time'], 'team': team, 'sender': sender['number'], 'receiver': receiver['number'],
                'origin': list(origin), 'end': list(end), 'direction': event['details']['direction'],
                'distance_m': round(length, 1), 'progress_m': round(progress, 1), 'quality':quality,'success':True,
                'passes_before': before[team], 'passes_after': self.metrics.completed[team],
                'possession_passes': self.metrics.passes_in_possession,
                'label': label, 'explanation': explanation, 'source': 'local',
                'processing_ms': round(elapsed, 3)}

    def acknowledge_display(self, event_id):
        if (type(event_id) is not int or not 1 <= event_id <= len(self.events)
                or self.events[event_id - 1]['kind'] != 'pass_completed'):
            raise ValueError('Explanation not found in the current match.')
        if event_id not in self.displayed:
            self.displayed.add(event_id)
            self.revision += 1

    def snapshot(self):
        receipts = []
        for source in list(self.receipts)[-8:]:
            item = deepcopy(source)
            item['displayed'] = item['event_id'] in self.displayed
            item['source_events'] = [deepcopy(self.events[item['start_event_id'] - 1]),
                                     deepcopy(self.events[item['event_id'] - 1])]
            item['related_moment_ids'] = [m.id for m in self.insights.moments.values()
                                         if item['event_id'] in m.evidence_ids]
            receipts.append(item)
        return {'revision': self.revision, 'received': len(self.events), 'processed': self.metrics.last_id,
                'receipts': receipts, 'status': 'ok' if self.last_error is None else 'degraded'}
