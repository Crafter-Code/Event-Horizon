                                                                               

                                                                          
                                                                               
   
from collections import deque
from copy import deepcopy
import math
from simulation import STEP_SECONDS


class GameContext:
    def __init__(self):
        self.clock = 0
        self.frames = deque(maxlen=2405)
        self.pressure_time = [0.,0.]
        self.zones = [[0.]*9 for _ in range(2)]
        self.possession = [0.,0.]
        self.events = []
        self.last_id = 0
        self.series = []
        self.periods = []
        self.attacks = []
        self.attack_team = None
        self.attack_counted = False
        self.positions = None
        self.distance = {key: 0. for key in (f'{t}:{n}' for t in (0,1) for n in range(1,12))}
        self.movement = {key: deque(maxlen=61) for key in self.distance}
        self.current_positions = {}
        self.movement_second = -1
        self.players = {f'{t}:{n}': dict(attempts=0,passes=0,received=0,shots=0,saves=0,regains=0,tackles=0)
                        for t in (0,1) for n in range(1,12)}
        self.player_events = {key: deque(maxlen=30) for key in self.players}
        self.player_pressure = {}
        self._sample(0)

    def _sample(self, clock):
        self.frames.append({'time': clock, 'pressure': self.pressure_time[:],
                            'zones': deepcopy(self.zones), 'possession': self.possession[:]})

    def observe(self, match, metrics, active):
        self.clock = match.clock
                                                                         
        self.possession = metrics.possession_time[:]
        pressure = metrics.snapshot(match.players, match.ball, bool(match.restart) or match.finished)['pressure']
        if active:
            zone = min(2,max(0,int(match.ball[0]/35))) + 3*min(2,max(0,int(match.ball[1]/(68/3))))
            for team in (0,1):
                if pressure[team]:
                    self.pressure_time[team] += STEP_SECONDS
                    self.zones[team][zone] += STEP_SECONDS
        positions = {f'{p.team}:{p.number}': p for p in match.players}
        for key, player in positions.items():
            old = self.positions.get(key) if self.positions else None
            if active and old is not None:
                self.distance[key] += math.dist(old, player.position)
            self.current_positions[key] = {'x': round(player.x,3), 'y': round(player.y,3),
                                           'speed_mps': round(math.hypot(player.vx,player.vy),2)}
            if int(match.clock) != self.movement_second:
                self.movement[key].append({'time': round(match.clock,2), 'x': round(player.x,3),
                                           'y': round(player.y,3), 'in_play': bool(active)})
        self.positions = {key: p.position for key,p in positions.items()}
        self.movement_second = int(match.clock)
        for event in match.events[self.last_id:]:
            self.events.append(event)
            self.last_id = event['id']
            kind, team = event['kind'], event['team']
            if kind in ('kickoff','restart_taken','interception','tackle','ball_recovered','save','shot_blocked','possession_change'):
                if self.attack_team != team or kind in ('kickoff','restart_taken'):
                    self.attack_counted = False
                self.attack_team = team
            if kind in ('goal','goal_kick','corner','throw_in','second_half','full_time'):
                self.attack_team = None
                self.attack_counted = False
            if kind in ('pass_started','pass_completed','interception','tackle','ball_recovered','shot'):
                if self.attack_team != team:
                    self.attack_team, self.attack_counted = team, False
                direction = 1 if (team == 0) == (event.get('period',1) == 1) else -1
                local_x = event['ball'][0] if direction == 1 else 105-event['ball'][0]
                if local_x >= 70 and not self.attack_counted:
                    self.attacks.append({'id': f"attack-{event['id']}", 'event_id': event['id'],
                                         'time': event['time'], 'team': team})
                    self.attack_counted = True
            actors = event['actors']
            for actor in actors:
                key = f"{actor['team']}:{actor['number']}"
                if event['kind'] == 'pressure':
                    self.player_pressure[key] = event['id']
                else:
                    self.player_events[key].append(event['id'])
            if actors:
                first = self.players[f"{actors[0]['team']}:{actors[0]['number']}"]
                last = self.players[f"{actors[-1]['team']}:{actors[-1]['number']}"]
                kind = event['kind']
                if kind == 'pass_started': first['attempts'] += 1
                elif kind == 'pass_completed': first['passes'] += 1; last['received'] += 1
                elif kind == 'shot': first['shots'] += 1
                elif kind == 'save': last['saves'] += 1
                elif kind in ('interception','tackle','ball_recovered'):
                    last['regains'] += 1
                    last['tackles'] += kind == 'tackle'
        self._sample(match.clock)
        if int(match.clock)//60 > len(self.series):
            completed = self.window()
            self.periods.append(deepcopy({key: completed[key] for key in ('current','previous','comparable')}))
            current = completed['current']
            self.series.append({'time': round(match.clock,2), 'passes':current['passes'],
                                'shots':current['shots'], 'pressure':current['pressure_seconds']})

    def window(self):
        end = self.clock
        def interval(start,end):
            frames = list(self.frames)
            a = min(frames,key=lambda frame:abs(frame['time']-start))
            b = min(frames,key=lambda frame:abs(frame['time']-end))
            possession = [max(0,b['possession'][t]-a['possession'][t]) for t in (0,1)]
            total = sum(possession)
            passes, shots, forward = [0,0], [0,0], [0.,0.]
            attacks, tackles, close_shots, losses = [0,0], [0,0], [0,0], [0,0]
            ids=[]
            for event in reversed(self.events):
                if event['time'] <= start: break
                if event['time'] > end: continue
                if event['kind'] == 'pass_started': passes[event['team']] += 1; ids.append(event['id'])
                elif event['kind'] == 'shot':
                    shots[event['team']] += 1
                    close_shots[event['team']] += event['details'].get('distance_m', 999) <= 18
                    ids.append(event['id'])
                elif event['kind'] == 'tackle': tackles[event['team']] += 1; ids.append(event['id'])
                elif event['kind'] == 'pass_completed':
                    details=event['details']
                    forward[event['team']] += max(0,(details['end'][0]-details['origin'][0])*details['direction'])
                    ids.append(event['id'])
                elif event['kind'] == 'pressure': ids.append(event['id'])
                elif event['kind'] == 'possession_change':
                    losses[event['details']['from_team']]+=1;ids.append(event['id'])
            for attack in reversed(self.attacks):
                if attack['time'] <= start: break
                if attack['time'] <= end:
                    attacks[attack['team']] += 1
                    ids.append(attack['event_id'])
            return {'losses':losses,'attacks': attacks, 'tackles': tackles, 'close_shots': close_shots, 'start':round(start,2),'end':round(end,2), 'passes':passes,'shots':shots,
                    'possession':[round(possession[0]/total*100) if total else 50,
                                  100-round(possession[0]/total*100) if total else 50],
                    'forward_m':[round(v,1) for v in forward],
                    'pressure_seconds':[round(max(0,b['pressure'][t]-a['pressure'][t]),1) for t in (0,1)],
                    'zones':[[round(max(0,b['zones'][t][i]-a['zones'][t][i]),1) for i in range(9)] for t in (0,1)],
                    'evidence_ids':sorted(set(ids))}
        current=interval(max(0,end-60),end)
        previous=interval(max(0,end-120),max(0,end-60))
        return {'current':current,'previous':previous,'comparable':end>=120,'series':deepcopy(self.series[-90:])}

    def focus_summary(self, player):
        if player is None: return None
        key=f"{player['team']}:{player['number']}"
        return {'player':player.copy(),'statistics':self.players[key].copy(),
                'movement':{'distance_m':round(self.distance[key],1),**self.current_positions[key],
                            'path':list(self.movement[key])}}

    def focus(self, player):
        if player is None: return None
        key=f"{player['team']}:{player['number']}"
        ids = list(self.player_events[key])
        if key in self.player_pressure:
            ids.append(self.player_pressure[key])
        return {'player':player.copy(),'statistics':self.players[key].copy(),
                'movement': {'distance_m': round(self.distance[key],1), **self.current_positions[key],
                             'path': list(self.movement[key])},
                'events':[deepcopy(self.events[i-1]) for i in sorted(ids,reverse=True)[:30]]}
