                                                                         
from pathlib import Path
import sqlite3

from demonstration_store import DemoReader, SCHEMA
from media import read_scene
from reproducibility_lab import verify

ROOT = Path(__file__).resolve().parent


def validate(path=None):
    path = Path(path) if path is not None else ROOT/'data/full-match.sqlite3'
    if not path.is_file():
        raise ValueError('Full match archive is missing. Generate it with: '
                         'python3 -B full_match_acceptance.py --output data/full-match.sqlite3')
    try:
        reader = DemoReader(path)
        manifest = reader.manifest()
        report = manifest['report']
        if (manifest['schema'] != SCHEMA or report.get('complete_match') is not True
                or report.get('status') != 'passed' or report.get('match_seconds') != 5400):
            raise ValueError('The demo archive must contain a verified complete 90-minute match')
        with reader.connect() as db:
            events = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
            frames, first, last = db.execute('SELECT COUNT(*), MIN(tick), MAX(tick) FROM frames').fetchone()
        expected_last = round(5400/manifest['settings']['step_seconds'])
        if events != report['event_count'] or (first,last,frames) != (0,expected_last,expected_last+1):
            raise ValueError('The demo archive has missing source events or frames')
        final = reader.state(5400, language='en', audience='fan')
        if not final['finished'] or final['score'] != report['score'] or not final['summary']:
            raise ValueError('The demo archive has no consistent final frame and summary')
        rehearsals = [e for e in manifest['episodes'] if e['kind'] != 'trend']
        if not rehearsals:raise ValueError('The demo archive has no media rehearsal episodes')
        for episode in rehearsals:
            scene = read_scene(path,episode['available_at'],episode['id'])
            if scene['status'] != 'ready':
                raise ValueError('Media rehearsal source check failed: '+episode['id'])
        proof=verify(42,30)
        if proof['status']!='passed':raise ValueError('Independent replay verification failed')
        return {'replay_preflight':{'seconds':30,'events':proof['compared_events'],
                                    'event_sha256':proof['stream']['event_sha256']},
                'schema':manifest['schema'], 'run_key':manifest['run_key'],
                'seconds':report['match_seconds'], 'events':events, 'frames':frames,
                'episodes':len(manifest['episodes']), 'media_rehearsals':len(rehearsals)}
    except (sqlite3.Error, KeyError, TypeError, OSError) as error:
        raise ValueError('The full match archive is unreadable or incomplete') from error
