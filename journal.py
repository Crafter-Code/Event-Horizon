                                                                                 
import json
import sqlite3
from threading import RLock
from uuid import uuid4


class EventJournal:
    def __init__(self, path):
        self.lock = RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS runs (
                run_key TEXT PRIMARY KEY, metadata TEXT NOT NULL,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS events (
                run_key TEXT NOT NULL REFERENCES runs(run_key),
                event_id INTEGER NOT NULL, time REAL NOT NULL, kind TEXT NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(run_key,event_id));
        ''')
        self.db.commit()

    def start(self, metadata):
        key = uuid4().hex
        with self.lock, self.db:
            self.db.execute('INSERT INTO runs(run_key,metadata) VALUES(?,?)',
                            (key, json.dumps(metadata, ensure_ascii=False)))
        return key

    def append(self, key, events):
        if not events:
            return
        with self.lock, self.db:
            for event in events:
                payload = json.dumps(event, ensure_ascii=False, sort_keys=True, allow_nan=False)
                existing = self.db.execute('SELECT payload FROM events WHERE run_key=? AND event_id=?',
                                           (key, event['id'])).fetchone()
                if existing:
                    if existing[0] != payload:
                        raise ValueError('Conflicting archived event')
                    continue
                self.db.execute('INSERT INTO events VALUES(?,?,?,?,?)',
                                (key, event['id'], event['time'], event['kind'], payload))

    def find(self, key, event_id):
        with self.lock:
            row = self.db.execute('SELECT payload FROM events WHERE run_key=? AND event_id=?', (key,event_id)).fetchone()
            metadata = self.db.execute('SELECT metadata FROM runs WHERE run_key=?', (key,)).fetchone()
        return {'event': json.loads(row[0]), 'metadata': json.loads(metadata[0]), 'run_key': key} if row and metadata else None

    def runs(self):
        with self.lock:
            rows = self.db.execute('''SELECT r.run_key,r.metadata,r.created,COUNT(e.event_id)
                FROM runs r LEFT JOIN events e ON r.run_key=e.run_key
                GROUP BY r.run_key ORDER BY r.created DESC,r.rowid DESC LIMIT 30''').fetchall()
        return [{'run_key': key, 'metadata': json.loads(meta), 'created_utc': created, 'event_count': count}
                for key,meta,created,count in rows]

    def close(self):
        self.db.close()
