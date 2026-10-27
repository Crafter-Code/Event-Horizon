                                                                                 

                                                                              
                                                                           
   
import argparse
from collections import deque
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import platform
import threading
import time
from uuid import uuid4

from generator_checks import GeneratorChecks
from pipeline import MatchPipeline
from simulation import GeneratorSettings, Match, STEP_SECONDS

SCHEMA = 'eh-replay-proof-1'
ROOT = Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',', ':'),allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def implementation():
    files = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
             ('simulation.py','scenarios.py','pipeline.py','generator_checks.py','reproducibility_lab.py',
              'insights.py','context.py','periods.py','roster.py')}
    return {'sha256':digest(files),'files':files,'python':platform.python_version()}


def first_difference(expected, actual, path='$'):
                                                                             
    if type(expected) is not type(actual):return {'field':path,'expected':expected,'actual':actual}
    if isinstance(expected,dict):
        if set(expected)!=set(actual):return {'field':path+'.keys','expected':sorted(expected),'actual':sorted(actual)}
        for key in sorted(expected):
            result=first_difference(expected[key],actual[key],path+'.'+key)
            if result:return result
    elif isinstance(expected,list):
        if len(expected)!=len(actual):return {'field':path+'.length','expected':len(expected),'actual':len(actual)}
        for i,(left,right) in enumerate(zip(expected,actual)):
            result=first_difference(left,right,f'{path}[{i}]')
            if result:return result
    elif expected!=actual:return {'field':path,'expected':expected,'actual':actual}
    return None


class Lane:
    def __init__(self,settings):
        self.match=Match(settings)
        self.checks=GeneratorChecks(self.match)
        self.pipeline=MatchPipeline(self.match)
        self.timings=deque(maxlen=512)
        self.processed_batches=0
        self.event_hash=hashlib.sha256()
        for event in self.pipeline.events:self.event_hash.update(canonical(event)+b'\n')

    def advance(self):
        started=time.perf_counter()
        m=self.match
        stopped,period=bool(m.restart),m.period
        before=len(m.events)
        m.advance()
        self.checks.validate(m)
        self.pipeline.validate_next(m)
        self.pipeline.advance(m,not stopped and not m.finished and m.period==period)
        for event in self.pipeline.events[before:]:self.event_hash.update(canonical(event)+b'\n')
        if len(m.events)>before:
            self.timings.append((time.perf_counter()-started)*1000)
            self.processed_batches+=1

    def witness(self):
        m=self.match
        return {'tick':m.tick,'event_count':len(m.events),'event_sha256':self.event_hash.hexdigest(),
                'frame_sha256':digest(m.snapshot()),
                'metrics_sha256':digest(self.pipeline.metrics.snapshot(m.players,m.ball,bool(m.restart) or m.finished))}

    def summary(self):
        m=self.match
        times=sorted(self.timings)
        metrics=self.pipeline.metrics.snapshot(m.players,m.ball,bool(m.restart) or m.finished)
        return {**self.witness(),'clock':round(m.clock,2),'metrics':metrics,
                'analysis_p95_ms':round(times[max(0,math.ceil(len(times)*.95)-1)],3) if times else None,
                'timed_batches':self.processed_batches,'timing_window':len(times),
                'recent_events':[{'id':e['id'],'time':e['time'],'kind':e['kind'],'title':e['title']}
                                 for e in m.events[-6:]]}


class ReplayProof:
    def __init__(self,settings=None,seconds=120,speed=1,now=0.,previous=None):
        self.settings=settings or GeneratorSettings()
        if type(seconds) is not int or not 1<=seconds<=5400:raise ValueError('Duration must be 1 to 5400 seconds')
        if type(speed) is not int or speed not in (1,8):raise ValueError('Speed must be 1 or 8')
        self.seconds,self.speed=seconds,speed
        self.started=now;self.last_now=now
        self.run_key=uuid4().hex
        self.reference=Lane(self.settings);self.stream=Lane(self.settings)
        self.pending=deque()
        self.matched_tick=0;self.compared_events=1
        self.first_mismatch=None;self.error=None;self.complete=False;self.cancelled=False
        self.checkpoints=[];self.previous=deepcopy(previous)
        self.build=implementation()
        self._compare(self.reference.witness())

    def _compare(self,expected):
        actual=self.stream.witness()
        if expected!=actual:
            count=max(expected['event_count'],actual['event_count'])
            left=self.reference.pipeline.events[:count];right=self.stream.pipeline.events[:count]
            delta=first_difference(left,right)
            self.first_mismatch={'tick':actual['tick'],'clock':round(actual['tick']*STEP_SECONDS,2),
                'difference':delta or first_difference(expected,actual)}
            return
        self.matched_tick=actual['tick'];self.compared_events=actual['event_count']
        if self.matched_tick%1200==0 or self.matched_tick==round(self.seconds/STEP_SECONDS):
            self.checkpoints.append(actual)

    def pump(self,now,max_ticks=40):
        if self.complete or self.first_mismatch or self.error or self.cancelled:return
        if not math.isfinite(now):raise ValueError('Invalid wall clock')
        if type(max_ticks) is not int or not 1<=max_ticks<=40:raise ValueError('Tick budget must be 1 to 40')
        self.last_now=max(self.last_now,now)
        elapsed=max(0,self.last_now-self.started)
        limit=round(self.seconds/STEP_SECONDS)
        reference_due=min(limit,int(elapsed*self.speed/STEP_SECONDS+1e-8))
                                                                              
        delivered=math.floor((elapsed+1e-9)/.4)*.4
        stream_due=min(limit,int(delivered*self.speed/STEP_SECONDS+1e-8))
        try:
            for _ in range(min(max_ticks,reference_due-self.reference.match.tick)):
                self.reference.advance();self.pending.append(self.reference.witness())
            for _ in range(min(max_ticks,stream_due-self.stream.match.tick,len(self.pending))):
                self.stream.advance();self._compare(self.pending.popleft())
                if self.first_mismatch:return
            self.complete=self.matched_tick==limit
        except (ValueError,KeyError,TypeError,IndexError) as error:
            self.error=type(error).__name__+': '+str(error)

    def snapshot(self):
        a,b=self.reference.summary(),self.stream.summary()
        target=min(self.seconds,max(0,self.last_now-self.started)*self.speed)
        identity={'settings':self.settings.as_dict(),'duration_seconds':self.seconds,'implementation':self.build}
        same_previous=bool(self.previous and self.previous['identity']==identity)
        repeat=(self.previous['event_sha256']==b['event_sha256']) if self.complete and same_previous else None
        return {'schema_version':SCHEMA,'run_key':self.run_key,'identity':identity,
                'status':'failed' if self.error or self.first_mismatch or repeat is False else 'stopped' if self.cancelled else 'passed' if self.complete else 'running',
                'speed':self.speed,'delivery_window_ms':400,'reference':a,'stream':b,
                'matched_tick':self.matched_tick,'matched_seconds':round(self.matched_tick*STEP_SECONDS,2),
                'compared_events':self.compared_events,'first_mismatch':deepcopy(self.first_mismatch),'error':self.error,
                'scheduled_seconds':round(target,2),'backlog_seconds':round(max(0,target-b['clock']),2),
                'previous_run_match':repeat,'checkpoints':deepcopy(self.checkpoints),
                'scope':'Independent synthetic generators and incremental analysis in this process. No cloud transport or AI prose determinism claim.',
                'timing_definition':'p95 of the latest 512 event-bearing ticks, generation through validated analysis; excludes network and screen display.'}

    def receipt(self):
        data=self.snapshot()
        if data['status']!='passed':raise ValueError('A passing complete run is required')
        return data


class ReplayLab:
                                                                                  
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.lock=threading.Lock();self.run=None;self.previous=None

    def start(self,seed=42,seconds=120,speed=8):
        if type(seconds) is not int or seconds not in (30,120,300):raise ValueError('Choose 30, 120 or 300 seconds')
        settings=GeneratorSettings(seed)
        with self.lock:
            if self.run and not (self.run.complete or self.run.error or self.run.first_mismatch or self.run.cancelled):
                raise RuntimeError('A verification is already running')
            run=ReplayProof(settings,seconds,speed,self.clock(),self.previous)
            self.run=run
            return run.snapshot()

    def pump(self):
        with self.lock:
            if not self.run:return
            self.run.pump(self.clock())
            if self.run.complete:
                data=self.run.snapshot()
                self.previous={'identity':data['identity'],'event_sha256':data['stream']['event_sha256']}

    def snapshot(self):
        with self.lock:
            return self.run.snapshot() if self.run else {'schema_version':SCHEMA,'status':'idle'}

    def cancel(self,run_key):
        with self.lock:
            if not self.run or self.run.run_key!=run_key:raise RuntimeError('Verification run changed')
            if not self.run.complete:self.run.cancelled=True
            return self.run.snapshot()

    def receipt(self,run_key=None):
        with self.lock:
            if run_key is not None and (not self.run or run_key!=self.run.run_key):
                raise RuntimeError('Verification run changed')
            if not self.run:raise ValueError('No verification has completed')
            return self.run.receipt()


def verify(seed=42,seconds=120):
    run=ReplayProof(GeneratorSettings(seed),seconds,8)
                                                                                  
    while not (run.complete or run.error or run.first_mismatch):run.pump(seconds+1)
    return run.snapshot()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=42);parser.add_argument('--seconds',type=int,default=120)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=verify(args.seed,args.seconds)
    body=json.dumps(result,indent=2)+'\n'
    if args.output:args.output.write_text(body)
    else:print(body,end='')
    raise SystemExit(0 if result['status']=='passed' else 1)
