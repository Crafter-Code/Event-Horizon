                                                                                

                                                                              
                                                                               
   
from copy import deepcopy
import math

from demonstration_store import DemoReader, unpack
from periods import fingerprint
from roster import player_name


SCHEMA = 'eh-media-scene-1'
LAYOUTS = ('studio', 'broadcast', 'stream')


def audit_episode(episode, sources, clock):
                                                                             
    ids = episode['evidence_ids']
    events = [sources[n] for n in ids if n in sources]
    team = episode['team']
    shots = [e for e in events if e['kind'] == 'shot']
    passes = [e for e in events if e['kind'] == 'pass_completed']
    shot = shots[0] if len(shots) == 1 else None
    linked = True
    for event in passes:
        start = sources.get(event['details'].get('pass_start_id'))
        linked = linked and bool(start and start['kind'] == 'pass_started'
            and start['team'] == event['team'] == team and start['actors'] == event['actors']
            and start['id'] < event['id'] and start['time'] < event['time'])
    measured = None
    if shot:
        measured = sum(math.dist((p['x'], p['y']), shot['ball']) <= 5
                       for p in shot['frame'] if p['team'] != team)
    facts = episode['facts']
    chronology = bool(events) and ids == sorted(set(ids)) and len(events) == len(ids)
    chronology = chronology and all(e['match_id'] == events[0]['match_id'] and e['time'] <= clock for e in events)
    chronology = chronology and all(a['time'] <= b['time'] for a, b in zip(events, events[1:]))
    score = bool(events) and facts.get('score') == events[-1]['score']
    outcome = events[-1] if events else None
    if shot and outcome:
        expected = shot['score'][:]
        if outcome['kind'] == 'goal': expected[team] += 1
        score = score and outcome['score'] == expected and facts.get('outcome') == outcome['kind']
    checks = [
        {'key':'sources', 'label':'Received sources in order', 'passed':bool(chronology)},
        {'key':'passes', 'label':'Passes have a start and reception',
         'passed':bool(linked and len(passes) == facts.get('passes_in_attack'))},
        {'key':'shot', 'label':'Shot follows this possession',
         'passed':bool(shot and shot['team'] == team and all(e['team'] == team for e in passes)
                       and all(e['time'] <= shot['time'] for e in passes))},
        {'key':'pressure', 'label':'Pressure matches player positions',
         'passed':bool(shot and measured == shot['details'].get('pressure_count'))},
        {'key':'score', 'label':'Outcome agrees with the score', 'passed':bool(score)},
    ]
    return {'status':'passed' if all(c['passed'] for c in checks) else 'held',
            'checks':checks, 'opponents_within_5m':measured,
            'scope':'Checks of this recorded episode; not validation against professional football distributions.'}


def compose(state, episode, sources):
                                                                            
    integrity = audit_episode(episode, sources, state['clock']) if episode else None
    ready = bool(episode and episode['complete'] and integrity['status'] == 'passed')
    card = None
    steps = []
    if ready:
        events = [sources[n] for n in episode['evidence_ids']]
        shot = next(e for e in events if e['kind'] == 'shot')
        passes = [e for e in events if e['kind'] == 'pass_completed']
        for event in events:
            kind = event['kind']
            label = ('Recovery' if kind in ('tackle','interception','ball_recovered') else
                     {'pass_completed':'Pass received','shot':'Shot','goal':'Goal',
                      'save':'Save','shot_blocked':'Blocked','goal_kick':'Goal kick',
                      'second_half':'Half-time','full_time':'Full-time'}.get(kind,kind.replace('_',' ').title()))
            steps.append({'event_id':event['id'], 'time':event['time'], 'label':label,
                          'ball':event['ball'], 'kind':kind,
                          'origin':event['details'].get('origin'),
                          'actors':[player_name(p['team'],p['number']) for p in event['actors']],
                          'href':f"/demo/event?id={event['id']}&run_key={state['run_key']}"})
        elapsed = round(shot['time'] - events[0]['time'], 1)
        count = len(passes)
        pressure = integrity['opponents_within_5m']
        scorer = player_name(shot['actors'][0]['team'], shot['actors'][0]['number'])
        outcome = steps[-1]['label']
        title = f'{outcome} · {scorer}'
        caption = f'{count} completed passes. {elapsed:g}s to the shot. {pressure} {'opponent' if pressure == 1 else 'opponents'} within 5m at the shot.'
        facts = {'passes':count, 'elapsed_seconds':elapsed, 'opponents_within_5m':pressure,
                 'score_after_episode':episode['facts']['score'], 'outcome':episode['facts']['outcome'],
                 'shot_time':shot['time'], 'episode_id':episode['id'], 'source_event_ids':episode['evidence_ids']}
        card = {'title':title, 'caption':caption, 'facts':facts,
                'fact_fingerprint':fingerprint(facts), 'episode_time':episode['time'],
                'available_at':episode['card']['available_at'],
                'explanation':'The sequence shows how possession reached a shot. Proximity measures pressure; it does not establish why the outcome happened.',
                'provenance':'Source-derived factual copy', 'steps':steps}
    return {'schema_version':SCHEMA, 'match_id':state['match_id'], 'run_key':state['run_key'],
            'clock':state['clock'], 'frame_png':state['frame_png'], 'observation':deepcopy(state.get('observation')), 'period':state['period'],
            'score':state['score'], 'statistics':{k:deepcopy(state[k]) for k in ('passes','attempts','shots','possession','pressure')},
            'card':card, 'integrity':integrity,
            'status':'ready' if ready else 'held' if episode else 'waiting',
            'mode':'rehearsal', 'synthetic':True,
            'layouts':{layout:{'fact_fingerprint':card['fact_fingerprint'] if card else None,
                               'placement':place, 'aspect_ratio':aspect}
                       for layout,place,aspect in [('studio','alongside','16:9'),('broadcast','overlay','16:9'),('stream','below','9:16')]},
            'definitions':{'possession':'Share of in-play time; rounded percentages.',
                           'pressure':'Current opponents within 5m of the ball; episode pressure is measured at the shot.',
                           'passes':'Completed receptions / attempted passes.',
                           'shots':'Recorded attempts; a shot is not automatically a goal.'}}


def read_scene(path, at=0, selected=None):
    reader = DemoReader(path)
    if not math.isfinite(at) or not 0 <= at <= 5400: raise ValueError('Invalid media time')
    with reader.connect() as db:
        if selected:
            if db.execute('SELECT id FROM episodes WHERE id=?',(selected,)).fetchone() is None:
                raise KeyError('Unknown episode')
        else:
                                                                                  
            for key, body in db.execute('SELECT id,packet FROM episodes WHERE available<=? ORDER BY time DESC',(at,)):
                candidate = unpack(body)
                if 'passes_in_attack' in candidate['facts'] and candidate['complete']:
                    selected = key
                    break
    state = reader.state(at, selected=selected)
    episode = state['episode']
    sources = {}
    if episode and episode['complete'] and 'passes_in_attack' in episode['facts']:
        with reader.connect() as db:
            pending = list(episode['evidence_ids'])
            while pending:
                key = pending.pop()
                if key in sources: continue
                row = db.execute('SELECT payload FROM events WHERE id=?',(key,)).fetchone()
                if not row: continue
                event = unpack(row[0]); sources[key] = event
                if event['kind'] == 'pass_completed':
                    start = event['details'].get('pass_start_id')
                    if isinstance(start,int): pending.append(start)
    else:
        episode = None
    return compose(state, episode, sources)
