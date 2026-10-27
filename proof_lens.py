                                                                                 

from global_localization import locale_map, translate_tree, translate_text


LABELS = locale_map({
    'en': {'opening': 'Sequence begins', 'recovery': 'Ball recovery',
           'build': 'Passing build-up', 'shot': 'Shot', 'outcome': 'Shot outcome',
           'context': 'Match context', 'player': 'Your player',
           'passes': 'completed passes', 'pending': 'Outcome pending',
           'involvement': 'recorded actions', 'score': 'Score', 'after_recovery': 'after the recovery',
           'after_start': 'after the sequence began'},
    'de': {'opening': 'Beginn der Folge', 'recovery': 'Ballgewinn',
           'build': 'Passfolge', 'shot': 'Schuss', 'outcome': 'Schussergebnis',
           'context': 'Spielkontext', 'player': 'Ihr Spieler',
           'passes': 'erfolgreiche Pässe', 'pending': 'Ausgang offen',
           'involvement': 'erfasste Aktionen', 'score': 'Spielstand', 'after_recovery': 'nach dem Ballgewinn',
           'after_start': 'nach Beginn der Folge'},
    'cs': {'opening': 'Začátek série', 'recovery': 'Zisk míče',
           'build': 'Série přihrávek', 'shot': 'Střela', 'outcome': 'Výsledek střely',
           'context': 'Kontext zápasu', 'player': 'Váš hráč',
           'passes': 'přesné přihrávky', 'pending': 'Výsledek čeká',
           'involvement': 'zaznamenané akce', 'score': 'Skóre', 'after_recovery': 'po zisku míče',
           'after_start': 'od začátku série'},
})


def claim_map(packet, contribution=None, language='en'):
                                                                            
    labels = LABELS[language]
    evidence = packet['evidence']
    if not evidence:
        return []
    ids = {event['id'] for event in evidence}
    def entry(key, label, detail, source_ids, value=None):
        source_ids = list(dict.fromkeys(source_ids))
        if not source_ids or not set(source_ids) <= ids:
            raise ValueError('A claim has no confirmed episode sources')
        return {'key': key, 'label': label, 'detail': detail, 'event_ids': source_ids,
                'focus_event_id': source_ids[-1], 'value': value,
                'verified': bool(packet['verified'])}

    if packet['kind'] == 'trend':
        comparison = packet['facts'].get('comparison')
        if comparison:
            current, previous = comparison['current'], comparison['previous']
            kind = 'pressure_seconds' if packet['facts'].get('context_change') == 'pressure' else 'passes'
            before = previous[kind]
            after = current[kind]
            value = f'{before[0]}:{before[1]} → {after[0]}:{after[1]}'
        else:
            window = packet['facts']['window']
            value = f"{window['previous_shots'][0]}:{window['previous_shots'][1]} → {window['shots'][0]}:{window['shots'][1]}"
        return [entry('context', labels['context'], packet['why'], packet['evidence_ids'], value)]

    shot = next((event for event in evidence if event['kind'] == 'shot'), None)
    regain = next((event for event in evidence if event['kind'] in ('tackle', 'interception')), None)
    first = regain or evidence[0]
    cards = [entry('recovery' if regain else 'opening',
                   labels['recovery' if regain else 'opening'],
                   first['text'], [first['id']])]
    passes = [event['id'] for event in evidence if event['kind'] == 'pass_completed']
    if passes:
        count = packet['facts'].get('passes_in_attack', len(passes))
        if count != len(passes):
            raise ValueError('Pass claim differs from confirmed episode sources')
        cards.append(entry('build', labels['build'],
                           f"{count} {labels['passes']}", passes, count))
    if shot:
        elapsed = round(shot['time'] - first['time'], 1)
        cards.append(entry('shot', labels['shot'],
                           f"{shot['text']} {elapsed:.1f} s {labels['after_recovery' if regain else 'after_start']}.",
                           [shot['id']], elapsed))
    if packet['complete'] and evidence[-1]['kind'] != 'shot':
        outcome = evidence[-1]
        cards.append(entry('outcome', labels['outcome'], outcome['text'],
                           [outcome['id']], packet['facts'].get('outcome')))
    elif shot:
        cards.append(entry('outcome', labels['outcome'], labels['pending'],
                           [shot['id']]))
    if shot and 'score' in packet['facts']:
        score = packet['facts']['score']
        last = evidence[-1]
        if score != last['score']:
            raise ValueError('Score claim differs from confirmed episode sources')
        cards.append(entry('context', labels['context'],
                           f"{labels['score']} {score[0]}:{score[1]}", [last['id']], score[:]))
    if contribution and contribution['evidence_ids']:
        involved = contribution['evidence_ids']
        if not set(involved) <= ids:
            raise ValueError('Player contribution has an unknown source')
        total = sum(contribution['counts'].values())
        cards.append(entry('player', labels['player'],
                           f"{total} {labels['involvement']}", involved, total))
    return cards
