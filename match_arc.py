                                                                                   

from global_localization import locale_map, translate_tree, translate_text
import hashlib
import json
import math

from locales import team_name


MAX_CHECKPOINTS = 12
COPY = locale_map({
    'en': {
        'title': 'The story of this period', 'empty': 'No recorded actions are available in this period yet.',
        'range': 'From {start} to {end}, the score moved from {before} to {after}.',
        'level': 'From {start} to {end}, the score stayed at {after}.',
        'opening_goal': '{team} opened the scoring', 'equalizer': '{team} equalized',
        'lead_restored': '{team} regained the lead', 'takes_lead': '{team} took the lead',
        'extends_lead': '{team} extended the lead', 'reduces_deficit': '{team} reduced the deficit',
        'first_shot': 'First recorded shot · {team}', 'first_tackle': 'First recorded tackle · {team}',
        'first_pass': 'First completed pass · {team}',
        'point': '{title} at {time}. Score: {score}.',
        'equalizers': '{team} drew level {count}.',
        'activity': 'Recorded activity: {blue} — {bp} completed passes, {bs} shots, {bt} tackles; {red} — {rp} completed passes, {rs} shots, {rt} tackles.',
        'possession': 'The event stream records {n} changes of possession in this period.',
        'pressure': 'Observed pressure peaks (players within 5 m of the ball): {blue} {b}, {red} {r}.',
        'pending': 'This period is still in progress.',
    },
    'cs': {
        'title': 'Příběh tohoto úseku', 'empty': 'V tomto úseku zatím nejsou dostupné zaznamenané akce.',
        'range': 'Od {start} do {end} se skóre změnilo z {before} na {after}.',
        'level': 'Od {start} do {end} zůstalo skóre {after}.',
        'opening_goal': '{team}: první gól zápasu', 'equalizer': '{team}: vyrovnání',
        'lead_restored': '{team}: návrat do vedení', 'takes_lead': '{team}: přechod do vedení',
        'extends_lead': '{team}: zvýšení náskoku', 'reduces_deficit': '{team}: snížení ztráty',
        'first_shot': 'První zaznamenaná střela · {team}', 'first_tackle': 'První zaznamenané odebrání míče · {team}',
        'first_pass': 'První přesná přihrávka · {team}',
        'point': '{title} v čase {time}. Skóre: {score}.',
        'equalizers': '{team}: {count} vyrovnání v tomto úseku.',
        'activity': 'Zaznamenané akce: {blue} — přesné přihrávky {bp}, střely {bs}, odebrání míče {bt}; {red} — přesné přihrávky {rp}, střely {rs}, odebrání míče {rt}.',
        'possession': 'Proud událostí v tomto úseku zaznamenal {n} změn držení míče.',
        'pressure': 'Nejvyšší zaznamenaný tlak (hráči do 5 m od míče): {blue} {b}, {red} {r}.',
        'pending': 'Tento úsek stále probíhá.',
    },
    'de': {
        'title': 'Die Geschichte dieses Abschnitts', 'empty': 'Für diesen Abschnitt liegen noch keine aufgezeichneten Aktionen vor.',
        'range': 'Von {start} bis {end} änderte sich der Spielstand von {before} auf {after}.',
        'level': 'Von {start} bis {end} blieb der Spielstand bei {after}.',
        'opening_goal': '{team} erzielte das erste Tor', 'equalizer': '{team} glich aus',
        'lead_restored': '{team} ging erneut in Führung', 'takes_lead': '{team} ging in Führung',
        'extends_lead': '{team} baute die Führung aus', 'reduces_deficit': '{team} verkürzte den Rückstand',
        'first_shot': 'Erster aufgezeichneter Schuss · {team}', 'first_tackle': 'Erste aufgezeichnete Balleroberung · {team}',
        'first_pass': 'Erster erfolgreicher Pass · {team}',
        'point': '{title} bei {time}. Spielstand: {score}.',
        'equalizers': '{team} glich {count}-mal aus.',
        'activity': 'Aufgezeichnete Aktionen: {blue} — {bp} erfolgreiche Pässe, {bs} Schüsse, {bt} Balleroberungen; {red} — {rp} erfolgreiche Pässe, {rs} Schüsse, {rt} Balleroberungen.',
        'possession': 'Der Ereignisstrom verzeichnet in diesem Abschnitt {n} Ballbesitzwechsel.',
        'pressure': 'Höchster beobachteter Druck (Spieler innerhalb von 5 m um den Ball): {blue} {b}, {red} {r}.',
        'pending': 'Dieser Abschnitt läuft noch.',
    },
})


def clock(value):
    seconds = int(value)
    return f'{seconds // 60:02d}:{seconds % 60:02d}'


def source_row(event):
                                                                                 
    if event is None:
        return None
    return [event['id'], event['time'], event['kind'], event['team'], event['score'],
            event.get('details', {}) if event['kind'] in ('pressure', 'possession_change') else None]


def build_arc(events, start, end, complete, language='en'):
                                                                               

                                                                             
                                                                               
                                                                             
                                                                             
                                                             
       
    if (language not in COPY or type(complete) is not bool or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)) or
            not 0 <= start <= end <= 5400):
        raise ValueError('Invalid story arc request')
    known = []
    for event in events:
        at = event.get('time')
        if type(at) not in (int, float) or not math.isfinite(at) or at < 0:
            raise ValueError('Invalid story arc event time')
        if at > end:
            continue
        key, score, team = event.get('id'), event.get('score'), event.get('team')
        if (type(key) is not int or key < 1 or not isinstance(event.get('kind'), str) or
                not isinstance(score, list) or len(score) != 2 or
                any(type(v) is not int or v < 0 for v in score) or
                team is not None and (type(team) is not int or team not in (0, 1))):
            raise ValueError('Invalid story arc source event')
        known.append(event)
    known.sort(key=lambda e: (e['time'], e['id']))
    if len({e['id'] for e in known}) != len(known):
        raise ValueError('Duplicate story arc source event')
    by_id = {e['id']: e for e in known}
    interval = [e for e in known if e['time'] > start or start == 0]
    words = COPY[language]
    counts = {'completed_passes': [0, 0], 'shots': [0, 0], 'tackles': [0, 0],
              'possession_changes': 0, 'pressure_changes': 0, 'pressure_peak': [0, 0]}
    count_keys = {'pass_completed': 'completed_passes', 'shot': 'shots', 'tackle': 'tackles'}
    examples, peaks, goals, led = {}, [None, None], [], [False, False]
    lead_sources, goal_sources = [None, None], {}
    equalizers = [0, 0]
    prior_pressure, prior_pressure_id, prior_pressure_event = None, None, None
    previous = None
    previous_event = None
    opening = None
    source_rows = []
    source_context = {}
    for event in known:
        inside = event['time'] > start or start == 0
        score, team, kind = event['score'], event['team'], event['kind']
        before = previous[:] if previous is not None else score[:]
        if kind == 'goal':
            if team not in (0, 1) or score[team] < 1:
                raise ValueError('Invalid goal score')
            before = score[:]
            before[team] -= 1
            if previous is not None and before != previous:
                raise ValueError('Goal score disagrees with preceding event')
        if inside:
            if opening is None:
                opening = before[:]
                source_context = {'opening_score': before[:],
                                  'score_source': source_row(previous_event),
                                  'pressure_source': source_row(prior_pressure_event),
                                  'prior_leads': [source_row(by_id[key]) if key is not None else None
                                                  for key in lead_sources]}
                if prior_pressure is not None:
                    counts['pressure_peak'] = prior_pressure[:]
                    peaks = [prior_pressure_id if value else None for value in prior_pressure]
            source_rows.append(source_row(event))
            if kind in count_keys:
                if team not in (0, 1):
                    raise ValueError('Counted action has no team')
                counts[count_keys[kind]][team] += 1
                examples.setdefault(kind, event)
            elif kind == 'possession_change':
                counts['possession_changes'] += 1
                examples.setdefault(kind, event)
            elif kind == 'pressure':
                values = event.get('details', {}).get('counts')
                if (not isinstance(values, list) or len(values) != 2 or
                        any(type(v) is not int or not 0 <= v <= 11 for v in values)):
                    raise ValueError('Invalid pressure source')
                counts['pressure_changes'] += 1
                for side in (0, 1):
                    if values[side] > counts['pressure_peak'][side]:
                        counts['pressure_peak'][side] = values[side]
                        peaks[side] = event['id']
                examples.setdefault(kind, event)
            if kind == 'goal':
                if sum(before) == 0:
                    classification = 'opening_goal'
                elif score[0] == score[1]:
                    classification = 'equalizer'
                elif score[team] > score[1-team] and before[team] <= before[1-team]:
                    classification = 'lead_restored' if led[team] else 'takes_lead'
                else:
                    classification = 'extends_lead' if score[team] > score[1-team] else 'reduces_deficit'
                goals.append((event, classification))
                if classification == 'equalizer':
                    equalizers[team] += 1
                goal_sources[event['id']] = ([lead_sources[team], event['id']]
                    if classification == 'lead_restored' else [event['id']])
        elif kind == 'pressure':
            values = event.get('details', {}).get('counts')
            if (not isinstance(values, list) or len(values) != 2 or
                    any(type(v) is not int or not 0 <= v <= 11 for v in values)):
                raise ValueError('Invalid pressure source')
            prior_pressure, prior_pressure_id = values[:], event['id']
            prior_pressure_event = event
        if score[0] != score[1]:
            leader = 0 if score[0] > score[1] else 1
            if not led[leader]:
                lead_sources[leader] = event['id']
            led[leader] = True
        previous = score[:]
        previous_event = event
    chosen = goals
    if not chosen:
        chosen = [(examples[kind], label) for kind, label in
                  (('shot', 'first_shot'), ('tackle', 'first_tackle')) if kind in examples]
        if not chosen and 'pass_completed' in examples:
            chosen = [(examples['pass_completed'], 'first_pass')]
        chosen.sort(key=lambda item: (item[0]['time'], item[0]['id']))
    checkpoint_count = len(chosen)
    if checkpoint_count > MAX_CHECKPOINTS:
        chosen = chosen[:2] + chosen[-(MAX_CHECKPOINTS-2):]
    checkpoints = []
    for event, kind in chosen:
        title = words[kind].format(team=team_name(event['team'], language))
        checkpoints.append({'event_id': event['id'], 'time': event['time'], 'kind': kind,
                            'title': title, 'text': words['point'].format(title=title, time=clock(event['time']),
                            score=f"{event['score'][0]}:{event['score'][1]}"),
                            'score': event['score'][:], 'evidence_ids': goal_sources.get(event['id'], [event['id']])})
    if interval:
        after = interval[-1]['score']
        sentences = [words['level' if opening == after else 'range'].format(start=clock(start), end=clock(end),
                     before=f'{opening[0]}:{opening[1]}', after=f'{after[0]}:{after[1]}')]
        if checkpoints:
            first_point = next((point for point in checkpoints if point['kind'] == 'first_shot'), checkpoints[0])
            sentences.append(first_point['text'])
            for side, amount in enumerate(equalizers):
                if amount and (amount > 1 or checkpoints[0]['kind'] != 'equalizer' or chosen[0][0]['team'] != side):
                    count = ('once' if amount == 1 else 'twice' if amount == 2 else f'{amount} times') if language == 'en' else amount
                    sentences.append(words['equalizers'].format(team=team_name(side, language), count=count))
            if len(goals) > 1:
                sentences.append(checkpoints[-1]['text'])
        names = {'blue': team_name(0, language), 'red': team_name(1, language)}
        sentences.append(words['activity'].format(**names,
            bp=counts['completed_passes'][0], rp=counts['completed_passes'][1],
            bs=counts['shots'][0], rs=counts['shots'][1], bt=counts['tackles'][0], rt=counts['tackles'][1]))
        if counts['possession_changes']:
            sentences.append(words['possession'].format(n=counts['possession_changes']))
        if counts['pressure_changes']:
            sentences.append(words['pressure'].format(**names, b=counts['pressure_peak'][0], r=counts['pressure_peak'][1]))
        if not complete:
            sentences.append(words['pending'])
        narrative = ' '.join(sentences)
    else:
        narrative = words['empty']
    refs = {key for c in checkpoints for key in c['evidence_ids']}
    refs.update(e['id'] for e in examples.values())
    refs.update(key for key in peaks if key is not None)
    if interval:
        refs.update((interval[0]['id'], interval[-1]['id']))
    context_rows = [source_context.get('score_source'), source_context.get('pressure_source'),
                    *source_context.get('prior_leads', [])]
    context_ids = sorted({row[0] for row in context_rows if row is not None})
    refs.update(context_ids)
    return {'schema_version': 'eh-match-arc-1', 'title': words['title'], 'narrative': narrative,
            'start': start, 'end': end, 'complete': complete, 'checkpoints': checkpoints,
            'checkpoint_count': checkpoint_count, 'checkpoints_truncated': checkpoint_count > MAX_CHECKPOINTS,
            'source_event_ids': sorted(refs), 'counts': counts,
            'score_transitions': {'equalizers': equalizers},
            'coverage': {'event_count': len(interval),
                         'context_event_ids': context_ids,
                         'first_event_id': interval[0]['id'] if interval else None,
                         'last_event_id': interval[-1]['id'] if interval else None,
                         'source_sha256': hashlib.sha256(json.dumps({'interval': source_rows, 'context': source_context}, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()}}
