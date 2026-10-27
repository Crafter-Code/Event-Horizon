import re
import threading
import time
from uuid import uuid4


class ViewerExpired(ValueError):
    pass


class ViewerBusy(RuntimeError):
    pass


class ViewerSessions:
    def __init__(self, factory, limit=1, idle_seconds=60, clock=time.monotonic):
        self.factory, self.limit, self.idle_seconds, self.clock = factory, limit, idle_seconds, clock
        self.lock = threading.RLock()
        self.entries = {}
        self.generation = 1000

    def create(self):
        with self.lock:
            self._expire()
            if len(self.entries) >= self.limit:
                raise ViewerBusy('All personal match slots are in use. Retrying shortly.')
            token = uuid4().hex
            match = self.factory()
            self.generation += 1
            match.run_id = self.generation
            entry = {'match':match, 'touched':self.clock(), 'started':False, 'stop':threading.Event()}
            thread = threading.Thread(target=self._work,args=(token,entry),daemon=True)
            entry['thread'] = thread
            self.entries[token] = entry
            thread.start()
            return token

    def _expire(self):
        for token, entry in list(self.entries.items()):
            if self.clock()-entry['touched'] > self.idle_seconds:
                entry['stop'].set()
                self.entries.pop(token,None)

    def get(self, token):
        if not isinstance(token,str) or not re.fullmatch('[0-9a-f]{32}',token):
            raise ViewerExpired('Personal match expired. Reconnecting from kick-off.')
        with self.lock:
            self._expire()
            entry = self.entries.get(token)
            if entry is None:raise ViewerExpired('Personal match expired. Reconnecting from kick-off.')
            entry['touched'] = self.clock()
            return entry['match']

    def start(self, token):
        match = self.get(token)
        with self.lock:
            entry = self.entries.get(token)
            if entry is None:raise ViewerExpired('Personal match expired.')
            if not entry['started']:
                match.started_at = match.wall_clock()
                entry['started'] = True
        return match

    def release(self, token):
        with self.lock:
            entry = self.entries.pop(token,None)
            if entry:entry['stop'].set()

    def find_run(self, key):
        with self.lock:
            return next((entry['match'] for entry in self.entries.values() if entry['match'].run_key==key),None)

    def active(self):
        with self.lock:
            self._expire()
            return [entry['match'] for entry in self.entries.values() if entry['started']]

    def _work(self, token, entry):
        match = entry['match']
        try:
            while not entry['stop'].wait(.02):
                with self.lock:
                    if self.clock()-entry['touched']>self.idle_seconds:
                        self.entries.pop(token,None)
                        break
                    started = entry['started']
                if started:match.pump()
        except Exception:
            with match.lock:match.pipeline.last_error = 'Personal match worker unavailable.'
        finally:
            if match.transport:match.transport.close()

    def close(self):
        with self.lock:
            entries = list(self.entries.values())
            self.entries.clear()
            for entry in entries:entry['stop'].set()
        deadline = time.monotonic()+12
        for entry in entries:entry['thread'].join(max(0,deadline-time.monotonic()))
