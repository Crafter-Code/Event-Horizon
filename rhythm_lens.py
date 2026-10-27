                                                                              
import math

from periods import fingerprint


SCHEMA = 'eh-rhythm-lens-1'


def build(window):
                                                                               

                                                                                
                                                                             
                                                                             
       
    current, previous = window['current'], window['previous']
    for part in (previous, current):
        start, end = part['start'], part['end']
        if any(type(n) not in (int, float) or not math.isfinite(n) for n in (start, end)) or not 0 <= start <= end <= 5400:
            raise ValueError('Invalid rhythm interval')
        for key in ('losses', 'passes', 'shots', 'pressure_seconds'):
            values = part[key]
            if (not isinstance(values, list) or len(values) != 2 or
                    any(type(n) not in (int, float) or not math.isfinite(n) or n < 0 for n in values)):
                raise ValueError('Invalid rhythm metric')
            if key != 'pressure_seconds' and any(type(n) is not int for n in values):
                raise ValueError('Invalid rhythm count')
            if key == 'pressure_seconds' and any(n > end-start+.1 for n in values):
                raise ValueError('Pressure exceeds observed duration')
        if any(type(n) is not int or n < 1 for n in part['evidence_ids']):
            raise ValueError('Invalid rhythm source')
    comparable = window['comparable']
    if type(comparable) is not bool or previous['end'] != current['start']:
        raise ValueError('Rhythm windows must be adjacent')
    if comparable and any(abs(part['end']-part['start']-60) > .01 for part in (previous, current)):
        raise ValueError('Comparison requires two complete minutes')
    rows = []
    for key, preference, field, team, unit in (
            ('turnovers', 'possession', 'losses', None, 'count'),
            ('pass_starts', 'tempo', 'passes', None, 'count'),
            ('shots', 'shots', 'shots', None, 'count'),
            ('pressure_blue', 'pressure', 'pressure_seconds', 0, 'seconds'),
            ('pressure_red', 'pressure', 'pressure_seconds', 1, 'seconds')):
        a = round(sum(current[field]) if team is None else current[field][team], 1)
        b = round(sum(previous[field]) if team is None else previous[field][team], 1)
        rows.append({'key': key, 'preference': preference, 'team': team,
                     'previous': b if comparable else None, 'current': a,
                     'delta': round(a-b, 1) if comparable else None, 'unit': unit})
    ids = sorted(set(previous['evidence_ids'] + current['evidence_ids']))
    source = {'windows': [{key: part[key] for key in
               ('start', 'end', 'losses', 'passes', 'shots', 'pressure_seconds', 'evidence_ids')}
               for part in (previous, current)], 'comparable': comparable}
    return {'schema_version': SCHEMA, 'status': 'ready' if comparable else 'collecting',
            'clock': current['end'], 'windows': {
                'previous': {'start': previous['start'], 'end': previous['end']},
                'current': {'start': current['start'], 'end': current['end']}},
            'rows': rows, 'source_count': len(ids),
            'source_event_ids': ids if len(ids) <= 12 else ids[:4] + ids[-8:],
            'source_fingerprint': fingerprint(source)}
