                                                                            
import hashlib
import json
import math
import re

MAX_BODY = 512 * 1024


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def envelope(session):
    match = session.match
    return {'schema': 'eh.ingress.v1', 'run_key': session.run_key,
            'match_id': match.match_id, 'tick': match.tick, 'time': match.clock,
            'metadata': match.metadata(), 'event_hash': match.event_digest.hexdigest(),
            'events': match.events[session.saved_count:], 'frame': match.snapshot()}


def decode(body):
    if not 0 < len(body) <= MAX_BODY:
        raise ValueError('Ingress body exceeds limit')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    value = json.loads(body, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
    expected = {'schema','run_key','match_id','tick','time','metadata','event_hash','events','frame'}
    if not isinstance(value, dict) or set(value) != expected or value['schema'] != 'eh.ingress.v1':
        raise ValueError('Invalid ingress schema')
    if not isinstance(value['run_key'], str) or not re.fullmatch('[0-9a-f]{32}', value['run_key']):
        raise ValueError('Invalid run identity')
    if type(value['tick']) is not int or not 1 <= value['tick'] <= 108000:
        raise ValueError('Invalid model tick')
    if type(value['time']) not in (float,int) or not math.isfinite(value['time']) or abs(value['time']-value['tick']*.05)>1e-6:
        raise ValueError('Invalid match time')
    if not isinstance(value['events'], list) or len(value['events']) > 64:
        raise ValueError('Invalid event batch')
    if not isinstance(value['metadata'],dict) or not isinstance(value['frame'],dict):
        raise ValueError('Missing frame or metadata')
    if not isinstance(value['event_hash'],str) or not re.fullmatch('[0-9a-f]{64}',value['event_hash']):
        raise ValueError('Invalid source digest')
                                                                               
                                                                         
    encode(value)
    return value
