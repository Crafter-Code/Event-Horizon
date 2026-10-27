                                                                         

                                                                           
                                                                            
   

from collections import deque
from copy import deepcopy
from dataclasses import dataclass, asdict
import hashlib
import json

from simulation import TEAMS


def match_time(seconds):
    return f'{int(seconds // 60):02}:{int(seconds % 60):02}'


@dataclass
class Moment:
    id: str
    revision: int
    time: float
    team: int | None
    kind: str
    title: str
    what: str
    why: str
    change: str
    evidence_ids: list
    actors: list
    complete: bool
    facts: dict
    source: str = 'local'
    ai_status: str = 'not_requested'
    interpretation: dict | None = None


class MatchInsights:
    def __init__(self):
        self.events = {}
        self.moments = {}
        self.frames = deque(maxlen=125)
        self.chain = []
        self.attack_team = None
        self.active_shot = None
        self.last_sample = -1
        self.last_trend_check = 0
        self.last_trend = -120
        self.last_event_id = 0
        self.revision = 0
        self.clock = 0
        self.shot_events = []

    def ingest(self, match):
        self.clock = match.clock
        second = int(match.clock)
        if second != self.last_sample:
            self.frames.append((match.clock, *match.possession_time))
            self.last_sample = second
            self.revision += 1
        for event in match.events[self.last_event_id:]:
            if event['id'] != self.last_event_id + 1 or event['time'] > match.clock:
                raise ValueError('Non-contiguous or future event')
            self.events[event['id']] = deepcopy(event)
            self.last_event_id = event['id']
            self._event(event)
        if second // 60 > self.last_trend_check:
            self.last_trend_check = second // 60
            self._trend()

    def window(self, end=None):
        end = self.clock if end is None else end
        start = max(0, end - 60)
        previous = max(0, start - 60)
        shots, before = [0, 0], [0, 0]
        evidence = []
        for key in reversed(self.shot_events):
            event = self.events[key]
            if event['time'] <= previous:
                break
            if event['kind'] == 'shot' and event['time'] <= end:
                bucket = shots if event['time'] > start else before
                bucket[event['team']] += 1
                evidence.append(event['id'])
        frames = [frame for frame in self.frames if frame[0] <= end]
        possession = [50, 50]
        if frames:
            a = min(frames, key=lambda frame: abs(frame[0] - start))
            b = frames[-1]
            duration = (b[1] - a[1]) + (b[2] - a[2])
            if duration > 0:
                possession[0] = round((b[1] - a[1]) / duration * 100)
                possession[1] = 100 - possession[0]
        return {'start': round(start, 2), 'end': round(end, 2), 'shots': shots,
                'previous_shots': before, 'possession': possession,
                'evidence_ids': sorted(evidence)}

    @staticmethod
    def change_text(window):
        duration = min(60, int(window['end']))
        prefix = 'In the last minute' if window['end'] >= 60 else f'Since kick-off ({duration} s)'
        shots = window['shots']
        text = f"{prefix}: shots {shots[0]}:{shots[1]}, possession {window['possession'][0]}%:{window['possession'][1]}%."
        if window['end'] >= 120:
            before = window['previous_shots']
            text += f' A minute earlier, shots were {before[0]}:{before[1]}.'
            advantage, old = shots[0] - shots[1], before[0] - before[1]
            if advantage * old < 0:
                text += f' {TEAMS[0 if advantage > 0 else 1]} increased their shot activity.'
            elif advantage != 0:
                text += f' {TEAMS[0 if advantage > 0 else 1]} took more shots in this period.'
        return text

    def _event(self, event):
        kind, team = event['kind'], event['team']
        if kind in ('interception', 'tackle', 'ball_recovered', 'restart_taken', 'kickoff'):
            self.chain = [event['id']]
            self.attack_team = team
        elif kind == 'pass_completed':
            if self.attack_team != team:
                self.chain = []
                self.attack_team = team
            self.chain.append(event['id'])
        elif kind == 'shot':
            self.shot_events.append(event['id'])
                                                                            
                                                                               
            ids = self.chain[:]
            ids.append(event['id'])
            self.active_shot = f"moment-{event['id']}"
            self._shot_moment(event, ids)
        elif kind in ('goal', 'save', 'shot_blocked', 'goal_kick'):
            if self.active_shot:
                moment = self.moments[self.active_shot]
                if event['time'] - moment.time <= 4:
                    self._resolve(moment, event)
                self.active_shot = None
            if kind in ('save', 'shot_blocked'):
                self.chain = [event['id']]
                self.attack_team = team
        elif kind in ('second_half', 'full_time'):
            if self.active_shot:
                self._resolve(self.moments[self.active_shot], event)
                self.active_shot = None
            self.chain = []
            self.attack_team = None

    def _shot_moment(self, event, ids):
        team = event['team']
        ids = [key for key in ids if self.events[key]['team'] == team or key == event['id']]
        passes = sum(self.events[key]['kind'] == 'pass_completed' for key in ids)
        regain = next((self.events[key] for key in ids if self.events[key]['kind'] in ('tackle', 'interception')), None)
        counter = bool(regain and event['time'] - regain['time'] <= 15 and
                       abs(event['ball'][0] - regain['ball'][0]) >= 20)
        why = (f"After regaining the ball, {TEAMS[team]} reached a shot in {event['time'] - regain['time']:.0f} s."
               if counter else f'The attack reached a shot after {passes} completed passes.')
        window = self.window(event['time'])
        moment = Moment(f"moment-{event['id']}", 1, event['time'], team,
                        'counterattack' if counter else 'chance',
                        'Fast attack leading to a shot' if counter else 'Shot — ' + TEAMS[team],
                        TEAMS[team] + ': ' + event['text'][:1].lower() + event['text'][1:], why, self.change_text(window), ids,
                        self._actors(ids), False,
                        {'score': event['score'][:], 'passes_in_attack': passes,
                         'counterattack': counter, 'window': window})
        self.moments[moment.id] = moment
        self.revision += 1

    def _resolve(self, moment, event):
        moment.evidence_ids.append(event['id'])
        moment.revision += 1
        moment.complete = True
        moment.actors = self._actors(moment.evidence_ids)
        moment.facts['score'] = event['score'][:]
        moment.facts['outcome'] = event['kind']
        if event['kind'] == 'goal':
            moment.kind = 'goal'
            team = moment.team
            own, other = event['score'][team], event['score'][1 - team]
            if own == other:
                moment.title = TEAMS[team] + ' equalize'
            elif own - 1 == other:
                moment.title = TEAMS[team] + ' take the lead'
            else:
                moment.title = 'Goal — ' + TEAMS[team]
            moment.what = f"{TEAMS[team]} scored. The score is {event['score'][0]}:{event['score'][1]}."
            moment.why += (' The goal levelled the score.' if own == other else
                           ' The goal put the team ahead.' if own - 1 == other else
                           ' The team reduced the deficit.' if own < other else
                           ' The team increased its lead.')
        else:
            result = {'save': 'The goalkeeper saved the shot and took possession.',
                      'shot_blocked': 'A defender blocked the shot and won the ball.',
                      'goal_kick': 'The shot ended with the ball crossing the end line.',
                      'second_half': 'The end of the first half interrupted the episode.',
                      'full_time': 'The end of the match interrupted the episode.'}[event['kind']]
            moment.what += ' ' + result
            moment.why += f" The score remained {event['score'][0]}:{event['score'][1]}."
            moment.why += (' The opponent was awarded the restart.' if event['kind'] == 'goal_kick' else
                           ' The attack ended with the opponent gaining possession.' if event['kind'] in ('save', 'shot_blocked') else '')
        moment.source = 'local'
        moment.ai_status = 'not_requested'
        self.revision += 1

    def _actors(self, ids):
        result = []
        for key in ids:
            for actor in self.events[key].get('actors', []):
                if actor not in result:
                    result.append(actor.copy())
        return result

    def _trend(self):
        if self.clock < 120 or self.clock - self.last_trend < 120:
            return
        window = self.window()
        now, before = window['shots'], window['previous_shots']
        difference = now[0] - now[1]
        old = before[0] - before[1]
        if abs(difference) < 2 or difference == old:
            return
        ids = window['evidence_ids']
        if not ids:
            return
        team = 0 if difference > 0 else 1
        moment_id = f'trend-{int(self.clock)}'
        self.moments[moment_id] = Moment(
            moment_id, 1, self.clock, team, 'trend', 'Change in activity in front of goal',
            f'{TEAMS[team]} took more shots in the last minute.',
            'The change is confirmed by comparing two adjacent minutes; its cause is not established.',
            self.change_text(window), ids, self._actors(ids), True, {'window': window})
        self.last_trend = self.clock
        self.revision += 1

    def verified(self, moment):
        return all(check['passed'] for check in self.check_report(moment))

    def context_change(self, comparison):
                                                                                  
        if not comparison['comparable']:return
        a,b=comparison['current'],comparison['previous']
        pressure=[round(a['pressure_seconds'][t]-b['pressure_seconds'][t],1) for t in (0,1)]
        rhythm=[abs(a['passes'][t]-b['passes'][t])>=3 or abs(a['attacks'][t]-b['attacks'][t])>=1 or a['losses'][t]!=b['losses'][t] for t in (0,1)]
        for subtype,eligible in (('pressure',max(map(abs,pressure))>=4),('rhythm',any(rhythm))):
            if not eligible:continue
            key=f'{subtype}-{int(self.clock)}'
            candidates=[e for e in self.events.values() if b['start']<e['time']<=a['end'] and e['kind'] in
                        (('pressure','tackle','interception','pass_completed') if subtype=='pressure' else ('pass_started','possession_change','shot'))]
                                                                                  
            ids=sorted({e['id'] for e in candidates[:8]+candidates[-16:]})
            if not ids:continue
            what=('Pressure time changed: '+', '.join(f'{TEAMS[t]} {b["pressure_seconds"][t]} → {a["pressure_seconds"][t]} s' for t in (0,1))) if subtype=='pressure' else (
                'Actions per minute: '+ '; '.join(f'{TEAMS[t]} — passes {b["passes"][t]} → {a["passes"][t]}, attacks {b["attacks"][t]} → {a["attacks"][t]}, losses {b["losses"][t]} → {a["losses"][t]}' for t in (0,1)))
            self.moments[key]=Moment(key,1,self.clock,None,'trend',
                'Pressure change' if subtype=='pressure' else 'Rhythm change',what,
                'The observation is supported by actions and a comparison of adjacent minutes. Its cause is not established.',
                self.change_text(self.window()),ids,self._actors(ids),True,
                {'window':self.window(),'context_change':subtype,'comparison':deepcopy(comparison),
                 'observed':True,'ai_interpretation':None})
            self.revision+=1

    def check_report(self, moment):
        evidence = [self.events[key] for key in moment.evidence_ids if key in self.events]
        sources = bool(evidence) and len(evidence) == len(moment.evidence_ids)
        ordered = (len(moment.evidence_ids) == len(set(moment.evidence_ids)) and
                   moment.evidence_ids == sorted(moment.evidence_ids) and
                   all(a['time'] <= b['time'] for a, b in zip(evidence, evidence[1:])))
        timely = sources and all(event['time'] <= min(self.clock, moment.time + 4) for event in evidence)
        passes = sum(event['kind'] == 'pass_completed' for event in evidence)
        counts = 'passes_in_attack' not in moment.facts or moment.facts['passes_in_attack'] == passes
        score = 'score' not in moment.facts or (sources and moment.facts['score'] == evidence[-1]['score'])
        window = moment.facts['window']
        current, previous = [0, 0], [0, 0]
        for key in self.shot_events:
            event = self.events[key]
            if max(0, window['start'] - 60) < event['time'] <= window['end']:
                bucket = current if event['time'] > window['start'] else previous
                bucket[event['team']] += 1
        windows = current == window['shots'] and previous == window['previous_shots']
        return [
            {'key': 'sources', 'label': 'Source events', 'passed': sources, 'detail': f'Found: {len(evidence)} of {len(moment.evidence_ids)}.'},
            {'key': 'order', 'label': 'Order and uniqueness', 'passed': ordered, 'detail': 'Chronological sequence without duplicates.' if ordered else 'Events are out of order or duplicated.'},
            {'key': 'time', 'label': 'Episode time', 'passed': timely, 'detail': 'Only received events were used.' if timely else 'Events outside the allowed time range were found.'},
            {'key': 'counts', 'label': 'Passes and score', 'passed': counts and score, 'detail': f'Completed passes in evidence sequence: {passes}.' if counts and score else 'The pass count or score differs from the sources.'},
            {'key': 'windows', 'label': 'Window comparison', 'passed': windows, 'detail': 'Shot counts recalculated from source events.' if windows else 'The shot count differs from the source events.'},
        ]

    def fact_fingerprint(self, moment):
        packet = {'id': moment.id, 'revision': moment.revision, 'facts': moment.facts,
                  'evidence': [self.events.get(key) for key in moment.evidence_ids]}
        return hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False,
                                         separators=(',', ':')).encode()).hexdigest()

    def attack_path(self, moment):
        evidence = [self.events[key] for key in moment.evidence_ids if key in self.events]
        if not evidence or moment.kind == 'trend':
            return []
        passes = [event for event in evidence if event['kind'] == 'pass_completed']
        shot = next((event for event in evidence if event['kind'] == 'shot'), None)
        if shot is None:
            return []
        start = evidence[0]
        path = [{'label': 'Attack starts', 'time': start['time'], 'event_ids': [start['id']]}]
        if passes:
            path.append({'label': f'Completed passes: {len(passes)}', 'time': passes[-1]['time'],
                         'event_ids': [event['id'] for event in passes]})
        path.append({'label': 'Shot', 'time': shot['time'], 'event_ids': [shot['id']]})
        if moment.complete:
            outcome = evidence[-1]
            labels = {'goal': 'Goal', 'save': 'Save', 'shot_blocked': 'Blocked shot', 'goal_kick': 'Wide',
                      'second_half': 'Half-time', 'full_time': 'Full-time'}
            path.append({'label': labels.get(outcome['kind'], 'Outcome'), 'time': outcome['time'], 'event_ids': [outcome['id']]})
        return path

    def player_contribution(self, moment, player):
        counts = {'passes_made': 0, 'passes_received': 0, 'shots': 0, 'saves': 0, 'regains': 0}
        ids = []
        for key in moment.evidence_ids:
            event = self.events[key]
            actors = event.get('actors', [])
            if player not in actors:
                continue
            ids.append(key)
            if event['kind'] == 'pass_completed':
                counts['passes_made'] += bool(actors and actors[0] == player)
                counts['passes_received'] += bool(len(actors) > 1 and actors[1] == player)
            counts['shots'] += event['kind'] == 'shot' and bool(actors) and actors[0] == player
            counts['saves'] += event['kind'] == 'save' and bool(actors) and actors[-1] == player
            counts['regains'] += event['kind'] in ('tackle', 'interception', 'ball_recovered') and bool(actors) and actors[-1] == player
        return {'counts': counts, 'evidence_ids': ids}

    def moment_data(self, moment):
        data = asdict(moment)
        data['verified'] = self.verified(moment)
        data['checks'] = self.check_report(moment)
        data['fact_fingerprint'] = self.fact_fingerprint(moment)
        data['attack_path'] = self.attack_path(moment)
        data['evidence'] = [deepcopy(self.events[key]) for key in moment.evidence_ids]
        return data

    def view(self, team=None, player=None):
        moments = list(self.moments.values())
        recent = moments[-16:]
        def priority(moment):
            focused = player is not None and player in moment.actors
            return (int(focused) * 2 + int(team is not None and moment.team == team), moment.time)
        selected = sorted(recent, key=priority, reverse=True)[:6]
                                                                              
                                                                          
        required = recent[-1:]
        goals = [moment for moment in recent if moment.kind == 'goal']
        if goals and goals[-1] not in required:
            required.append(goals[-1])
        for moment in required:
            if moment not in selected:
                removable = next((item for item in reversed(selected) if item not in required), None)
                if len(selected) >= 6 and removable is not None:
                    selected.remove(removable)
                selected.append(moment)
        chosen = sorted(selected, key=priority, reverse=True)
        cards = []
        for moment in chosen:
            data = self.moment_data(moment)
            labels = []
            if team is not None and moment.team == team:
                labels.append('Your team')
            if player is not None and player in moment.actors:
                labels.append(f"Your player · #{player['number']}")
            data['personalization'] = labels
            data['personal_story'] = ''
            data['contribution'] = None
            if player is not None:
                contribution = self.player_contribution(moment, player)
                data['contribution'] = contribution
                if contribution['evidence_ids']:
                    values = contribution['counts']
                    data['personal_story'] = (f"Player #{player['number']} contributed to this episode: completed passes — {values['passes_made']}, passes received — {values['passes_received']}, shots — {values['shots']}, saves — {values['saves']}, recoveries — {values['regains']}.")
            elif team is not None:
                data['personal_story'] = ('This attack belongs to your team.' if moment.team == team else
                                          'This episode shows an attack by your team’s opponent.')
            cards.append(data)
        latest = sorted(moments, key=lambda moment: moment.time)[-3:]
        parts = [f"{'At' if i == 0 else 'Then at'} {match_time(moment.time)} — {moment.what}"
                 for i, moment in enumerate(latest)]
        if not parts:
            summary = 'The match is developing. The first key episodes will appear after shots or a noticeable change in activity in front of goal.'
        else:
            summary = ' '.join(parts)
            summary += ' ' + latest[-1].why
        window = self.window()
        summary += ' ' + self.change_text(window)
        focus = 'Whole match'
        if player is not None:
            focus = f"{TEAMS[player['team']]} · player #{player['number']}"
        elif team is not None:
            focus = 'Team: ' + TEAMS[team]
        return {'revision': self.revision, 'focus': focus, 'summary': summary,
                'window': window, 'moments': cards, 'total_moments': len(moments)}
