                                                                                     

import json
import asyncio
import logging
import os
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue, Empty, Full
import threading
import time
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit
from copy import copy, deepcopy

from simulation import GeneratorSettings, Match, STEP_SECONDS
from pipeline import MatchPipeline, EventContractError
from editorial import EditorialDesk, EditorialConflict
from foundry_narrative import from_environment, validate_draft
from broadcast_peer import from_environment as broadcast_peer_from_environment
from content import ContentService
from experience import build_experience
from locales import event_display, translated_packet, pipeline_display, story
from journal import EventJournal
from uuid import uuid4
import sqlite3
import math
from delivery import MaterialStream, metric_selection
from presentation import package
from telemetry import PresentationTiming
from camera import SyntheticCamera
from match_report import MatchReport
from generator_checks import GeneratorChecks, GeneratorConsistencyError
from language_contract import language_proof
from story_languages import LANGUAGES as STORY_LANGUAGES, render as render_story_language
from scenarios import catalogue
from dataset import export_dataset, duration_ticks
from roster import named_metadata
from cloud_contract import envelope, digest, decode, MAX_BODY
from demonstration_store import DemoReader
from ingress import from_environment as ingress_from_environment, IngressConflict
from observability import observe
import operator_access
from http_security import BoundedHTTPServer, REQUEST_TIMEOUT, body_length, host_allowed, policy
from media import read_scene
from reproducibility_lab import ReplayLab
from journey import build as build_journey
from intelligence_provenance import build_provenance
from viewer_sessions import ViewerSessions, ViewerBusy, ViewerExpired


ROOT = Path(__file__).resolve().parent
stop = threading.Event()


dataset_slot = threading.BoundedSemaphore(1)


class MatchSession:
                                                                                

    def __init__(self, settings=None, wall_clock=time.monotonic, journal=None, vision_enabled=False, transport=None):
        self.lock = threading.Lock()
        self.wall_clock = wall_clock
        self.match = Match(settings)
        self.started_at = wall_clock()
        self.run_id = 1
        self.generator_checks = GeneratorChecks(self.match)
        self.pipeline = MatchPipeline(self.match)
        self.insights = self.pipeline.insights
        self.journal = journal
        self.run_key = journal.start(self.match.metadata()) if journal else uuid4().hex
        self.saved_count = 0
        self.materials = MaterialStream()
        self.timing = PresentationTiming()
        self.timed_count = 0
        self.camera = SyntheticCamera() if vision_enabled else None
        self.reports = MatchReport()
        if self.camera:self.camera.advance(self.match)
        self._confirm_frame()
        self.desk = EditorialDesk()
        self.content = ContentService()
        self.narrator = None
        self.broadcast_peer = broadcast_peer_from_environment()
        self.narrator_status = 'Local factual narrative'
        self.ai_queue = Queue(maxsize=24)
        self.ai_claimed = set()
        self.transport = transport
        self.pending_ingress = None
        self.last_ingress = None
        self.ingress_failures = 0
        self.ingress_retry_at = 0.
        self.ingress_error = False

    def pump(self, now=None):
        if self.transport is not None:
            return self._pump_functions(now)
        with self.lock:
            if self.pipeline.last_error is not None:
                return
            elapsed = max(0, (self.wall_clock() if now is None else now) - self.started_at)
            due = int(elapsed / STEP_SECONDS + 1e-8)
            while self.match.tick < due and not self.match.finished:
                stopped = bool(self.match.restart)
                period = self.match.period
                event_started = self.timing.clock()
                self.match.advance()
                previous = self.insights.revision
                active = not stopped and not self.match.finished and self.match.period == period
                self._commit_tick(active, event_started, previous)
                if self.pipeline.last_error is not None:return

    def _commit_tick(self, active, event_started, previous, pending=None):
        try:
            with observe.span('eh.analysis.publish', run_key=self.run_key, tick=self.match.tick):
                if pending is None or not pending.get('validated'):
                    self.generator_checks.validate(self.match)
                    self.pipeline.validate_next(self.match)
                    if pending is not None:pending['validated'] = True
                if self.journal and not (pending and pending.get('archived')):
                    self.journal.append(self.run_key, self.match.events[self.saved_count:])
                self.saved_count = len(self.match.events)
                self.pipeline.advance(self.match, active)
                self._confirm_frame(event_started)
                if self.narrator is not None and previous != self.insights.revision:
                    self._queue_narratives()
        except (EventContractError, GeneratorConsistencyError, ValueError):
            self.pipeline.last_error = 'Event contract rejected; processing stopped.'
            self.pipeline.revision += 1
            logging.getLogger('event_horizon').error('Football event contract rejected; processing stopped')
        except (sqlite3.Error, OSError):
                                                                            
                                                                            
            if pending is not None and self.pipeline.tick < self.match.tick:raise
            self.pipeline.last_error = 'Event archive unavailable; processing stopped.'
            self.pipeline.revision += 1

    def _pump_functions(self, now=None):
                                                                             
                                                                          
        with self.lock:
            if self.pipeline.last_error is not None:return
            clock = self.wall_clock() if now is None else now
            if clock < self.ingress_retry_at:return
            if self.pending_ingress is None:
                due = int(max(0, clock-self.started_at)/STEP_SECONDS+1e-8)
                if self.match.finished or self.match.tick >= due:return
                ticks=[]
                while self.match.tick < due and not self.match.finished and len(ticks)<100:
                    stopped, period = bool(self.match.restart), self.match.period
                    started = self.timing.clock()
                    self.match.advance()
                    frame=copy(self.match)
                    for name,value in vars(self.match).items():
                        if isinstance(value,(list,dict,set)):
                            setattr(frame,name,self.match.events[:] if name=='events' else deepcopy(value))
                    frame.event_digest=self.match.event_digest.copy()
                    ticks.append({'match':frame,'active':not stopped and not self.match.finished and self.match.period==period,
                                  'started':started,'validated':False})
                    if len(self.match.events)-self.saved_count>=40:break
                payload = envelope(self)
                if self.pipeline.tick == 0:payload['events'] = self.match.events[:]
                self.pending_ingress = {'payload':payload,'digest':digest(payload),
                    'ticks':ticks,'index':0,'committed':False}
            pending = self.pending_ingress
        try:
            self.transport.submit(pending['payload'])
            with self.lock:
                if self.pending_ingress is pending:
                    if not pending['committed']:raise OSError('Receipt arrived before processing')
                    self.pending_ingress = None
                    self.ingress_failures = 0
                    self.ingress_error = False
        except (OSError, ValueError) as error:
            with self.lock:
                if self.pending_ingress is pending:
                    self.ingress_failures += 1
                    self.ingress_error = True
                    self.ingress_retry_at = self.wall_clock()+min(10., .25*2**min(self.ingress_failures-1,6))
            logging.getLogger('event_horizon').warning('Functions delivery deferred: %s', type(error).__name__)

    def receive_ingress(self, payload):
        fingerprint = digest(payload)
        with self.lock:
            if self.last_ingress and fingerprint == self.last_ingress['digest']:
                return {**self.last_ingress,'duplicate':True}
            pending = self.pending_ingress
            if pending is None or fingerprint != pending['digest']:
                raise IngressConflict('Batch is not the current pending source tick')
        if self.journal and hasattr(self.journal,'append_batch') and not pending.get('archived'):
            self.journal.append_batch(payload['run_key'],payload['events'])
            pending['archived']=True
        while True:
            with self.lock:
                if self.pending_ingress is not pending:
                    raise IngressConflict('Match changed during delivery')
                if self.pipeline.last_error is not None:raise OSError('Pipeline stopped')
                if pending['index']>=len(pending['ticks']):
                    pending['committed'] = True
                    self.last_ingress = {'accepted':True,'tick':payload['tick'],'digest':fingerprint,
                                         'run_key':self.run_key,'event_count':self.confirmed_count}
                    return {**self.last_ingress,'duplicate':False}
                generated=self.match
                item=pending['ticks'][pending['index']]
                item['archived']=pending.get('archived',False)
                try:
                    self.match=item['match']
                    with observe.span('eh.ingress.commit',run_key=self.run_key,tick=self.match.tick):
                        self._commit_tick(item['active'],item['started'],self.insights.revision,item)
                    if self.pipeline.last_error is not None:raise OSError('Pipeline stopped')
                    pending['index']+=1
                finally:
                    self.match=generated
            time.sleep(0)

    def restart(self, seed=None, scenario=None):
        with self.lock:
            current = self.match.settings
            settings = GeneratorSettings(current.seed if seed is None else seed,
                                         current.scenario if scenario is None else scenario)
            match = Match(settings)
            checks = GeneratorChecks(match)
            pipeline = MatchPipeline(match)
            run_key = self.journal.start(match.metadata()) if self.journal else uuid4().hex
            if self.journal:
                self.journal.append(run_key,pipeline.events)
            self.match, self.pipeline, self.run_key = match, pipeline, run_key
            self.generator_checks = checks
            self.started_at = self.wall_clock()
            self.run_id += 1
            self.insights = pipeline.insights
            self.saved_count = len(pipeline.events)
            self.materials = MaterialStream()
            self.timing = PresentationTiming()
            self.timed_count = 0
            self.camera = SyntheticCamera() if self.camera else None
            self.reports = MatchReport()
            if self.camera:self.camera.advance(self.match)
            self._confirm_frame()
            self.desk = EditorialDesk()
            self.ai_claimed.clear()
            self.pending_ingress = self.last_ingress = None
            self.ingress_failures = 0
            self.ingress_retry_at = 0.
            self.ingress_error = False

    def _confirm_frame(self, event_started=None):
                                                                                
        if self.journal:
            self.journal.append(self.run_key, self.pipeline.events[self.saved_count:])
        self.saved_count = len(self.pipeline.events)
        self.confirmed_frame = self.match.snapshot()
        self.confirmed_frame.update(self.pipeline.metrics.snapshot(
            self.match.players, self.match.ball, bool(self.match.restart) or self.match.finished))
        self.confirmed_count = len(self.pipeline.events)
        self.confirmed_hash = self.match.event_digest.hexdigest()
        self.materials.sync(self.pipeline)
        if self.camera:
            self.camera.evaluation.watch(self.generator_checks.expectations.matches)
            if self.camera.recognizer.clock < self.match.clock:self.camera.advance(self.match)
        if self.match.clock in (2700,5400):self.reports.snapshot(self.pipeline)
        ready = self.timing.clock()
        for event in self.pipeline.events[self.timed_count:]:
            self.timing.produced(event['id'],ready if event_started is None else event_started,ready)
        self.timed_count = self.confirmed_count

    def _queue_narratives(self):
        for moment in self.insights.moments.values():
            key = (self.run_id, moment.id, moment.revision)
            if not moment.complete or moment.source == 'foundry' or key in self.ai_claimed:
                continue
            self.ai_claimed.add(key)
            try:
                self.ai_queue.put_nowait((key, self.insights.moment_data(moment), observe.headers()))
                moment.ai_status = 'pending'
            except Full:
                moment.ai_status = 'fallback'

    async def process_narrative_job(self, key, packet, trace_headers=None):
        with self.lock:
            moment = self.insights.moments.get(key[1])
            current = key[0] == self.run_id and moment is not None and moment.revision == key[2]
            run_key = self.run_key
        if not current:return False
        try:
            with observe.incoming(trace_headers or {}), observe.span('eh.narrative', run_key=self.run_key, episode=key[1], revision=key[2]):
                draft = await self.narrator.compose({**packet, '_run_key':run_key})
                if draft is not None and self.broadcast_peer is not None:
                    await self.broadcast_peer.review(packet, draft)
                    if self.narrator.history:
                        self.narrator.history[-1]['stages'].append(
                            {'role':'broadcast_a2a','status':'approved'})
        except Exception as error:
            logging.getLogger('event_horizon').warning('Narrative fallback: %s',type(error).__name__)
            observe.record('eh.narrative.fallback',0,'error')
            draft = None
            if self.narrator is not None and self.broadcast_peer is not None and self.narrator.history:
                trace = self.narrator.history[-1]
                if trace['status'] == 'verified':
                    trace['status'] = 'fallback'
                    trace['failure'] = type(error).__name__
                    trace['stages'].append({'role':'broadcast_a2a','status':'failed'})
        return self.apply_narrative(key,draft)

    def apply_narrative(self, key, draft):
        with self.lock:
            run_id, moment_id, revision = key
            moment = self.insights.moments.get(moment_id)
            if run_id != self.run_id or moment is None or revision != moment.revision:
                return False
            if draft is not None:
                try:
                    validate_draft(draft, self.insights.moment_data(moment))
                except ValueError:
                    draft = None
            if draft is not None:
                moment.interpretation = {field:draft[field] for field in ('what','why','change','evidence_ids')}
                moment.source, moment.ai_status = 'foundry', 'verified'
                moment.revision += 1
            else:
                moment.ai_status = 'fallback'
            self.insights.revision += 1
            self.materials.sync(self.pipeline)
            return True

    def editorial_action(self, payload):
        with self.lock:
            if payload.get('run_id') != self.run_id:
                raise EditorialConflict('This material belongs to the previous match. Refresh the panel.')
            moment = self.insights.moments.get(payload.get('moment_id'))
            if moment is not None and payload.get('fact_fingerprint') != self.insights.fact_fingerprint(moment):
                raise EditorialConflict('The source data changed. Refresh the material before reviewing it.')
            language=payload.get('language','en')
            if language not in ('en','cs','de','fr','it','es','pt'): raise ValueError('Invalid language')
            result = self.desk.act(self.insights, payload.get('moment_id'), payload.get('revision'),
                                   payload.get('action'), payload.get('copy'), language)
            return result

    def acknowledge_display(self, payload):
        with self.lock:
            if payload.get('run_id') != self.run_id:
                raise EditorialConflict('This acknowledgement belongs to the previous match.')
            self.pipeline.acknowledge_display(payload.get('event_id'))

    def acknowledge_presentation(self, payload):
        with self.lock:
            if payload.get('run_key') != self.run_key:
                raise EditorialConflict('Display receipt belongs to a previous match.')
            accepted = self.timing.acknowledge(payload)
            if accepted:
                observe.record('eh.event.display_ack', self.timing.samples[-1]['event_to_display_ack_ms'])
            return accepted

    def material_feed(self, **preferences):
        with self.lock:
            return package(self, **preferences)

    def snapshot(self, after=0, run_id=None, team=None, player=None, view='fan',
                 insight_revision=-1, desk_revision='', pipeline_revision=-1, overview_revision='', audience='fan', language='en', selected=None, experience_revision='', metrics=None, compact=False, scene_revision=''):
        with self.lock:
            metrics = metric_selection(metrics)
            count = self.confirmed_count
            reset = run_id != self.run_id or after > count
            data = deepcopy(self.confirmed_frame)
            data.update(run_id=self.run_id, reset=reset,
                        settings=self.match.settings.as_dict(), event_count=count,
                        event_hash=self.confirmed_hash,
                        events=([{'id':event['id'],'time':event['time']}
                                 for event in self.pipeline.events[0 if reset else after:count]] if compact
                                else deepcopy(self.pipeline.events[0 if reset else after:count])))
            data['metadata'] = named_metadata(self.match.metadata())
            data['generator'] = self.generator_checks.snapshot(
                self.confirmed_frame['clock'],self.camera.evaluation.verdicts if self.camera else None)
            data['vision'] = self.camera.snapshot() if self.camera else {'enabled':False}
            data['reports'] = self.reports.snapshot(self.pipeline,player,language,audience,team)
            data['run_key'] = self.run_key
            data['language'] = language
            data['audience'] = audience
            data['presentation'] = package(self,audience,language,team,player,metrics,after=len(self.materials.history),limit=1,channel='broadcast' if view=='editor' else 'viewer')
            data['event'].update(event_display(data['event'],language))
            experience_version = f'{self.confirmed_frame["clock"]}:{self.insights.revision}:{audience}:{language}:{team}:{player}:{selected}:{metrics}'
            data['experience_revision'] = experience_version
            if reset or experience_revision != experience_version:
                data['experience'] = build_experience(self,audience,language,team,player,selected,metrics,scene_revision if compact and not reset else '')
            data['narrator_status'] = self.narrator_status
            data['intelligence_provenance'] = build_provenance(self)
            data['insight_revision'] = self.insights.revision
            data['pipeline_revision'] = self.pipeline.revision
            if reset or pipeline_revision != self.pipeline.revision:
                data['pipeline'] = pipeline_display(self.pipeline.snapshot(),language)
            if reset or insight_revision != self.insights.revision:
                data['insights'] = self.insights.view(team, player)
                for packet in data['insights']['moments']:
                    packet['materials'] = self.content.render(packet, team, player, packet.get('contribution'),language,audience)
                    packet.update({key:value for key,value in translated_packet(packet,language,audience).items() if key in ('title','what','why','change','attack_path','evidence','interpretation')})
                data['insights']['summary'] = ' → '.join(p['what'] for p in reversed(data['insights']['moments'][:3]))
                data['insights']['focus'] = data['insights']['moments'][0]['materials']['formats']['stream']['focus'] if data['insights']['moments'] else ''
            overview = self.content.overview(self.insights)
            overview['revision'] += ':'+language+':'+audience
            for entry in overview['entries']:
                local = story(self.materials.latest[entry['id']]['packet'],language,audience)
                entry.update({k:local[k] for k in ('title','what','why','change')})
            data['overview_revision'] = overview['revision']
            if reset or overview_revision != overview['revision']:
                data['overview'] = overview
            if view == 'editor':
                version = f'{self.insights.revision}:{self.desk.revision}:{language}:{team}:{player}'
                data['desk_revision'] = version
                if reset or version != desk_revision:
                    data['editorial'] = self.desk.snapshot(self.insights,language)
                    for packet in data['editorial']['items']:
                        contribution = self.insights.player_contribution(self.insights.moments[packet['id']], player) if player else None
                        packet['materials'] = self.content.render(packet, team, player, contribution,language,'analyst')
                        packet.update({key:value for key,value in translated_packet(packet,language,'analyst').items() if key in ('title','what','why','change','attack_path','evidence','interpretation')})
                    active = data['editorial']['active']
                    if active is not None:
                        data['editorial']['active'] = deepcopy(next(packet for packet in data['editorial']['items'] if packet['id'] == active['id']))
            if compact:
                def strip_frames(value):
                    if isinstance(value,dict):
                        value.pop('frame',None)
                        for child in value.values():strip_frames(child)
                    elif isinstance(value,list):
                        for child in value:strip_frames(child)
                for key in ('events','insights','editorial'):
                    if key in data:strip_frames(data[key])
                experience=data.get('experience')
                if experience:
                    strip_frames(experience.get('focus'))
                    selected_packet=experience.get('selected')
                    if selected_packet:
                        for material in selected_packet['materials']['formats'].values():strip_frames(material)
                presentation=data['presentation']
                presentation.pop('cards',None)
                if presentation.get('period'):
                    presentation['period'].pop('facts',None)
                    for item in presentation['period']['periods']:item.pop('facts',None)
                for item in presentation['live_changes']:item.pop('facts',None)
            return data


session = MatchSession()
replay_lab = ReplayLab()


def create_viewer_match():
    match = MatchSession(journal=session.journal,vision_enabled=session.camera is not None,
                         transport=ingress_from_environment())
    match.narrator, match.narrator_status = session.narrator, session.narrator_status
    return match


viewer_sessions = ViewerSessions(create_viewer_match)



class Handler(BaseHTTPRequestHandler):
    server_version = 'EventHorizon'
    sys_version = ''

    def setup(self):
        self.request.settimeout(REQUEST_TIMEOUT)
        super().setup()

    def parse_request(self):
        if not super().parse_request():return False
        health_probe = self.command == 'GET' and self.path in ('/health/live','/health/ready') and len(self.headers.get_all('Host',[])) == 1
        if not health_probe and not host_allowed(self.headers, self.server.server_port, os.getenv('EVENT_HORIZON_PUBLIC_ORIGIN','')):
            self.send_json({'error':'Invalid application host'},403)
            return False
        return True

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','SAMEORIGIN')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy',getattr(self,'response_policy',policy()))
        super().end_headers()

    def require_operator(self):
        if operator_access.authorized(self.headers.get('Authorization','')):return True
        body = b'{"error":"Editor sign-in required"}'
        self.send_response(401)
        self.send_header('WWW-Authenticate','Basic realm="Event Horizon editor", charset="UTF-8"')
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def do_GET(self):
        try:self._get()
        except (OSError,sqlite3.Error):
            observe.record('eh.http.failure',0,'error')
            self.send_json({'error':'Requested data is temporarily unavailable'},503)

    def _get(self):
        url = urlsplit(self.path)
        scoped_paths={'/state','/event','/runs','/materials','/generator','/vision','/video/frame.png',
                      '/agent-trace','/operations','/journey/state','/story-language','/language-proof'}
        token=self.headers.get('X-EH-Viewer-Session')
        query_token=parse_qs(url.query).get('viewer_session',[None])[0]
        if query_token is not None:
            url=url._replace(query=urlencode([(k,v) for k,v in parse_qsl(url.query,keep_blank_values=True) if k!='viewer_session']))
        if (token or query_token) and url.path in scoped_paths:
            try:session=viewer_sessions.get(token or query_token)
            except ViewerExpired as error:self.send_json({'error':str(error)},410);return
        else:session=globals()['session']
        ui_query=parse_qs(url.query)
        self.ui_language=ui_query.get('language',[self.headers.get('X-EH-Language','en')])[0]
        self.ui_audience=ui_query.get('audience',['analyst'])[0]
        if (url.path in ('/editor','/replay-lab/control') or
                (url.path == '/state' and 'editor' in parse_qs(url.query).get('view',[]))):
            if not self.require_operator():return
        if url.path == '/story-language':
            try:
                query=parse_qs(url.query,keep_blank_values=True)
                if set(query)-{'source','at','episode','language','audience','team','player','run_key','fingerprint'} or any(len(v)!=1 for v in query.values()):
                    raise ValueError('Invalid story query')
                source=query.get('source',['live'])[0];language=query.get('language',['en'])[0]
                audience=query.get('audience',['fan'])[0];side=query.get('team',['all'])[0]
                if source not in ('live','demo') or language not in STORY_LANGUAGES or audience not in ('fan','analyst','player') or side not in ('all','0','1'):
                    raise ValueError('Invalid story rendition')
                team=None if side=='all' else int(side);text=query.get('player',['none'])[0];player=None
                if text!='none':
                    t,n=map(int,text.split(':'))
                    if t not in (0,1) or not 1<=n<=11:raise ValueError('Invalid story player')
                    player={'team':t,'number':n}
                episode=query.get('episode',[None])[0]
                if episode is not None and (not episode or len(episode)>100):raise ValueError('Invalid story episode')
                with observe.span('eh.story.language',language=language):
                    if source=='demo':
                        reader=DemoReader(Path(__file__).parent/'data/full-match.sqlite3')
                        result=reader.story_language(float(query.get('at',['0'])[0]),language,audience,team,player,episode)
                    else:
                        if 'at' in query:raise ValueError('Live story does not accept a replay clock')
                        with session.lock:
                            if query.get('run_key',[session.run_key])[0]!=session.run_key:
                                self.send_json({'error':'Story belongs to a different run'},409);return
                            moment=session.insights.moments.get(episode) if episode else next(reversed(session.insights.moments.values()),None)
                            if episode and moment is None:raise KeyError('Unknown story episode')
                            packet=session.insights.moment_data(moment) if moment else None
                            summary=None
                            if session.confirmed_frame['clock']>=5400:
                                original=language if language in ('en','cs','de') else 'en'
                                summary=session.reports.snapshot(session.pipeline,player,original,audience,team)['full_time']
                            result={**render_story_language(packet,language,audience,team,player,session.confirmed_frame['clock'],summary),
                                    'run_key':session.run_key,'match_id':session.match.match_id,'source':'live'}
                if 'run_key' in query and query['run_key'][0]!=result['run_key']:
                    self.send_json({'error':'Story belongs to a different run'},409);return
                if 'fingerprint' in query and query['fingerprint'][0]!=(result.get('episode') or {}).get('fact_fingerprint'):
                    self.send_json({'error':'Story facts have changed; refresh the episode'},409);return
                self.send_json(result)
            except KeyError:self.send_json({'error':'Story episode not found'},404)
            except (ValueError,TypeError,OverflowError):self.send_json({'error':'Invalid story query'},400)
            return
        if url.path == '/journey/state':
            try:
                query = parse_qs(url.query, keep_blank_values=True)
                if set(query) - {'episode', 'team', 'player', 'language', 'run_key'} or any(
                        len(values) != 1 for values in query.values()):
                    raise ValueError('Invalid journey query')
                episode = query.get('episode', [None])[0]
                if episode is not None and (not episode or len(episode) > 80):
                    raise ValueError('Invalid episode')
                language = query.get('language', ['en'])[0]
                side = query.get('team', ['all'])[0]
                selected_player = query.get('player', ['none'])[0]
                if language not in ('en', 'cs', 'de', 'fr', 'it', 'es', 'pt') or side not in ('all', '0', '1'):
                    raise ValueError('Invalid journey preferences')
                player = None
                if selected_player != 'none':
                    team_number, number = map(int, selected_player.split(':'))
                    if team_number not in (0, 1) or not 1 <= number <= 11:
                        raise ValueError('Invalid player')
                    player = {'team': team_number, 'number': number}
                with session.lock:
                    if 'run_key' in query and query['run_key'][0] != session.run_key:
                        self.send_json({'error': 'Episode belongs to another run'}, 409);return
                    result = build_journey(session, episode, None if side == 'all' else int(side),
                                           player, language)
                self.send_json(result)
            except KeyError:
                self.send_json({'error': 'Episode not found'}, 404)
            except (ValueError, TypeError):
                self.send_json({'error': 'Invalid journey query'}, 400)
            return
        if url.path in ('/replay-lab/state','/replay-lab/receipt'):
            try:
                query=parse_qs(url.query,keep_blank_values=True)
                if url.path.endswith('/receipt'):
                    if set(query)!={'run_key'} or len(query['run_key'])!=1 or len(query['run_key'][0])!=32:
                        self.send_json({'error':'A verification run identity is required'},400);return
                    result=replay_lab.receipt(query['run_key'][0])
                else:
                    if url.query:self.send_json({'error':'State does not accept query parameters'},400);return
                    result=replay_lab.snapshot()
                self.send_json(result)
            except (ValueError,RuntimeError) as error:self.send_json({'error':str(error)},409)
            return
        if url.path == '/studio/scene':
            try:
                query=parse_qs(url.query,keep_blank_values=True)
                if set(query)-{'at','episode','run_key'} or any(len(v)!=1 for v in query.values()):
                    raise ValueError('Invalid studio query')
                selected=query.get('episode',[None])[0]
                if selected is not None and (not selected or len(selected)>80):raise ValueError('Invalid episode')
                path=Path(os.getenv('EVENT_HORIZON_DEMO_ARCHIVE',str(ROOT/'data/full-match.sqlite3')))
                if not path.is_file():
                    self.send_json({'error':'Full match archive is unavailable'},404);return
                with observe.span('eh.media.scene'):
                    result=read_scene(path,float(query.get('at',['0'])[0]),selected)
                if 'run_key' in query and result['run_key']!=query['run_key'][0]:
                    self.send_json({'error':'Demonstration archive changed'},409);return
                self.send_json(result)
            except KeyError:self.send_json({'error':'Episode not found'},404)
            except (ValueError,TypeError,OverflowError):self.send_json({'error':'Invalid studio query'},400)
            except (sqlite3.Error,OSError):self.send_json({'error':'Studio archive unavailable'},503)
            return
        if url.path in ('/demo/manifest','/demo/state','/demo/event','/demo/report','/demo/lenses'):
            path=Path(os.getenv('EVENT_HORIZON_DEMO_ARCHIVE',str(ROOT/'data'/'full-match.sqlite3')))
            if not path.is_file():
                self.send_json({'error':'Full match archive has not been generated','status':'not_ready'},404);return
            try:
                query=parse_qs(url.query,keep_blank_values=True)
                allowed=({'id','language','run_key'} if url.path=='/demo/event' else
                         {'run_key'} if url.path in ('/demo/manifest','/demo/report') else
                         {'at','episode','run_key'} if url.path=='/demo/lenses' else
                         {'at','language','audience','team','player','episode','metrics','run_key'})
                if set(query)-allowed or any(len(v)!=1 for v in query.values()):raise ValueError('Invalid demonstration query')
                reader=DemoReader(path)
                language=query.get('language',['en'])[0];audience=query.get('audience',['fan'])[0]
                if language not in ('en','cs','de','fr','it','es','pt') or audience not in ('fan','analyst','player'):raise ValueError('Invalid rendition')
                side=query.get('team',['all'])[0]
                if side not in ('all','0','1'):raise ValueError('Invalid team')
                team=None if side=='all' else int(side)
                text=query.get('player',['none'])[0];player=None
                if text!='none':
                    t,n=map(int,text.split(':'))
                    if t not in (0,1) or not 1<=n<=11:raise ValueError('Invalid player')
                    player={'team':t,'number':n}
                if url.path=='/demo/event':
                    result=reader.event(int(query.get('id',['0'])[0]),language)
                elif url.path=='/demo/lenses':
                    result=reader.lenses(query['episode'][0],float(query.get('at',['0'])[0]))
                elif url.path in ('/demo/manifest','/demo/report'):
                    result=reader.manifest()
                    if url.path=='/demo/report':
                        if 'run_key' in query and result['run_key']!=query['run_key'][0]:
                            self.send_json({'error':'Demonstration archive changed'},409);return
                        result=result['report']
                else:
                    raw=query.get('metrics',[None])[0]
                    metrics=metric_selection(None if raw is None else raw.split(',') if raw else [])
                    result=reader.state(float(query.get('at',['0'])[0]),language,audience,team,player,
                                        query.get('episode',[None])[0],metrics)
                if 'run_key' in query and result.get('run_key') and result['run_key']!=query['run_key'][0]:
                    self.send_json({'error':'Demonstration archive changed'},409);return
                self.send_json(result)
            except KeyError:self.send_json({'error':'Demonstration item not found'},404)
            except (ValueError,TypeError,OverflowError):self.send_json({'error':'Invalid demonstration query'},400)
            return
        if url.path in ('/health/live','/health/ready'):
            with session.lock:
                ready = session.pipeline.last_error is None
            status = 200 if url.path.endswith('/live') or ready else 503
            self.send_json({'status':'ok' if status==200 else 'degraded'},status)
            return
        if url.path == '/agent-trace':
            if url.query:
                self.send_json({'error':'Agent trace does not accept query parameters'},400);return
            with session.lock:
                result = {'run_key':session.run_key,
                          'provider':'foundry' if session.narrator else 'local',
                          'runs':[run for run in session.narrator.trace()
                                  if run['run_key']==session.run_key] if session.narrator else []}
            self.send_json(result)
            return
        if url.path == '/operations':
                                                                             
            with session.lock:
                result = {'ingress':'functions' if session.transport else 'local',
                    'delivery':'retrying' if session.ingress_error else 'ok',
                    'pending_tick':session.pending_ingress['payload']['tick'] if session.pending_ingress else None,
                    'confirmed_tick':session.pipeline.tick,'confirmed_events':session.confirmed_count,
                    'narrative_provider':'foundry' if session.narrator else 'local',
                    'telemetry':observe.snapshot()}
            self.send_json(result)
            return
        if url.path == '/state':
            try:
                query = parse_qs(url.query, keep_blank_values=True)
                after = int(query.get('after', ['0'])[0])
                run_id = int(query['run'][0]) if 'run' in query else None
                if after < 0:
                    raise ValueError('Negative cursor')
                team_text = query.get('team', ['all'])[0]
                if team_text not in ('all', '0', '1'):
                    raise ValueError('Invalid team')
                team = None if team_text == 'all' else int(team_text)
                player_text = query.get('player', ['none'])[0]
                player = None
                if player_text != 'none':
                    side, number = map(int, player_text.split(':'))
                    if side not in (0, 1) or not 1 <= number <= 11:
                        raise ValueError('Invalid player')
                    player = {'team': side, 'number': number}
                view = query.get('view', ['fan'])[0]
                if view not in ('fan', 'editor'):
                    raise ValueError('Invalid view')
                insight_revision = int(query.get('insight_revision', ['-1'])[0])
                desk_revision = query.get('desk_revision', [''])[0]
                pipeline_revision = int(query.get('pipeline_revision', ['-1'])[0])
                overview_revision = query.get('overview_revision', [''])[0]
                audience = query.get('audience',['fan'])[0]
                language = query.get('language',['en'])[0]
                selected = query.get('episode',[None])[0] or None
                experience_revision = query.get('experience_revision',[''])[0]
                raw_metrics=query.get('metrics',[None])[0]
                metrics=metric_selection(None if raw_metrics is None else raw_metrics.split(',') if raw_metrics else [])
                compact=query.get('compact',['0'])[0]=='1'
                scene_revision=query.get('scene_revision',[''])[0]
                if audience not in ('fan','analyst','player') or language not in ('en','cs','de','fr','it','es','pt'):
                    raise ValueError('Invalid audience or language')
            except (ValueError, IndexError):
                self.send_json({'error': 'Invalid event number.'}, status=400)
                return
            content = json.dumps(session.snapshot(after, run_id, team, player, view,
                                                 insight_revision, desk_revision, pipeline_revision, overview_revision, audience, language, selected, experience_revision, metrics, compact, scene_revision), ensure_ascii=False).encode('utf-8')
            kind = 'application/json; charset=utf-8'
        elif url.path == '/language-proof':
            query=parse_qs(url.query)
            try:
                if set(query)-{'episode','audience','run_key'} or any(len(v)!=1 for v in query.values()):raise ValueError('Invalid language-proof query')
                audience=query.get('audience',['fan'])[0]
                if audience not in ('fan','analyst','player'):raise ValueError('Invalid audience')
                with session.lock:
                    if query.get('run_key',[session.run_key])[0]!=session.run_key:
                        self.send_json({'error':'Episode belongs to another run'},409);return
                    moment=session.insights.moments.get(query.get('episode',[''])[0])
                    if moment is None:
                        self.send_json({'error':'Episode not found'},404);return
                    result=language_proof(session.insights.moment_data(moment),audience,session.run_key,session.match.match_id)
                self.send_json(result)
            except ValueError as error:self.send_json({'error':str(error)},400)
            return
        elif url.path == '/generator':
            with session.lock:
                self.send_json({'run_key':session.run_key, 'match_id':session.match.match_id,
                                'settings':session.match.settings.as_dict(),
                                'validation':session.generator_checks.snapshot(
                                    session.confirmed_frame['clock'],
                                    session.camera.evaluation.verdicts if session.camera else None)})
            return
        elif url.path == '/scenarios':
            self.send_json({'scenarios': catalogue()})
            return
        elif url.path == '/dataset.zip':
            from io import BytesIO
            query = parse_qs(url.query)
            try:
                if set(query) - {'seed', 'scenario', 'seconds'} or any(len(v)!=1 for v in query.values()):
                    raise ValueError('Invalid dataset query')
                settings = GeneratorSettings(int(query.get('seed', ['42'])[0]), query.get('scenario', ['open_play'])[0])
                seconds = float(query.get('seconds', ['15'])[0])
                duration_ticks(seconds, 30)
            except ValueError as error:
                self.send_json({'error': str(error)}, 400)
                return
            if not dataset_slot.acquire(blocking=False):
                self.send_json({'error': 'Dataset export already in progress'}, 429)
                return
            try:
                out = BytesIO()
                export_dataset(out, settings, seconds)
                content = out.getvalue()
            except ValueError as error:
                self.send_json({'error': str(error)}, 422)
                return
            finally:
                dataset_slot.release()
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', f'attachment; filename="eh-{settings.scenario}-{settings.seed}.zip"')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content)
            return
        elif url.path == '/materials':
            try:
                query=parse_qs(url.query,keep_blank_values=True)
                audience=query.get('audience',['fan'])[0];language=query.get('language',['en'])[0]
                team=query.get('team',['all'])[0];player=query.get('player',['none'])[0]
                channel=query.get('channel',['viewer'])[0]
                if channel not in ('viewer','broadcast'):raise ValueError('Invalid channel')
                if audience not in ('fan','analyst','player') or language not in ('en','cs','de','fr','it','es','pt') or team not in ('all','0','1'):
                    raise ValueError('Invalid viewer')
                if player!='none':
                    side,number=map(int,player.split(':'))
                    if side not in (0,1) or not 1<=number<=11:raise ValueError('Invalid player')
                    player={'team':side,'number':number}
                else:player=None
                raw=query.get('metrics',[None])[0]
                metrics=metric_selection(None if raw is None else raw.split(',') if raw else [])
                after=int(query.get('after',['0'])[0]);limit=int(query.get('limit',['100'])[0])
                at=float(query['at'][0]) if 'at' in query else None
                if after<0 or not 1<=limit<=1000 or (at is not None and (not math.isfinite(at) or not 0<=at<=5400)):
                    raise ValueError('Invalid material cursor or playback time')
                self.send_json(session.material_feed(audience=audience,language=language,
                    team=None if team=='all' else int(team),player=player,metrics=metrics,after=after,limit=limit,at=at,channel=channel))
            except (ValueError,TypeError):self.send_json({'error':'Invalid material query'},400)
            return
        elif url.path in ('/runs','/event'):
            query=parse_qs(url.query)
            if url.path=='/runs':
                data=session.journal.runs() if session.journal else [{'run_key':session.run_key,'metadata':session.match.metadata(),'event_count':session.confirmed_count}]
                self.send_json({'runs':data,'current':session.run_key})
            else:
                try:
                    key=query.get('run_key',[session.run_key])[0]
                    number=int(query.get('id',['0'])[0]); language=query.get('language',['en'])[0]
                    if number<1 or language not in ('en','cs','de','fr','it','es','pt'): raise ValueError()
                    with session.lock:
                        found=session.journal.find(key,number) if session.journal else ({'event':deepcopy(session.pipeline.events[number-1]),'metadata':session.match.metadata(),'run_key':key} if key==session.run_key and number<=session.confirmed_count else None)
                        if key == session.run_key and number > session.confirmed_count:
                            found = None
                    if found: found['display']=event_display(found['event'],language)
                    self.send_json(found or {'error':'Event not found'},200 if found else 404)
                except ValueError: self.send_json({'error':'Invalid event query'},400)
            return
        elif url.path == '/video/frame.png':
            try:
                query=parse_qs(url.query);number=int(query['id'][0]) if 'id' in query else None
                with session.lock:
                    if 'run_key' in query and query['run_key'][0]!=session.run_key:
                        self.send_json({'error':'Frame belongs to a different run'},409);return
                    camera=session.camera
                    image=(camera.frames.get(number) if number is not None else camera.png) if camera else None
                if image is None:self.send_json({'error':'Frame unavailable or outside rolling buffer'},404);return
                self.send_content(image,'image/png')
            except ValueError:self.send_json({'error':'Invalid frame number'},400)
            return
        elif url.path == '/vision':
            with session.lock:
                data=session.camera.snapshot(False) if session.camera else {'enabled':False}
                data.update(match_id=session.match.match_id,run_key=session.run_key)
            self.send_json(data);return
        elif url.path in ('/viewer.js','/viewer-session.js','/i18n.js','/preferences.js','/story.js','/output.js','/video.js', '/scenario.js','/language.js','/demo.js','/studio.js','/studio-core.js','/replay-lab.js','/journey.js','/match-arc.js','/intelligence-provenance.js','/rhythm-lens.js','/story-languages.js','/global-locales.js','/global-locale.js','/enhanced-ui.js','/field-renderer.js'):
            content=(ROOT/url.path[1:]).read_bytes(); kind='text/javascript; charset=utf-8'
        elif url.path in ('/jury-theme.css','/jury-pages.css','/match-arc.css','/intelligence-provenance.css','/rhythm-lens.css','/story-languages.css','/enhanced-ui.css','/kickoff.css'):
            content=(ROOT/url.path[1:]).read_bytes(); kind='text/css; charset=utf-8'
        elif url.path in ('/replay-lab','/replay-lab/control'):
            content=(ROOT/'replay-lab.html').read_bytes();kind='text/html; charset=utf-8'
            if not operator_access.authorized(self.headers.get('Authorization','')):
                content=content.replace(b'<body>',b'<body data-readonly="true">',1)
        elif url.path == '/studio':
            content=(ROOT/'studio.html').read_bytes();kind='text/html; charset=utf-8'
        elif url.path == '/journey':
            content=(ROOT/'journey.html').read_bytes();kind='text/html; charset=utf-8'
        elif url.path == '/demo':
            content=(ROOT/'demo.html').read_bytes();kind='text/html; charset=utf-8'
        elif url.path == '/output':
            content=(ROOT/'output.html').read_bytes();kind='text/html; charset=utf-8'
        elif url.path in ('/schemas/material.schema.json','/schemas/overlay.schema.json','/schemas/recognition.schema.json'):
            content=(ROOT/url.path[1:]).read_bytes();kind='application/json; charset=utf-8'
        elif url.path in ('/', '/live', '/editor'):
            content = (ROOT / 'index.html').read_bytes()
            if operator_access.required():
                content = content.replace(b'<body>',b'<body data-operator-required="true">',1)
            kind = 'text/html; charset=utf-8'
        else:
            self.send_error(404)
            return
        self.send_content(content, kind)

    def do_POST(self):
        self.ui_language=self.headers.get('X-EH-Language','en')
        session=globals()['session']
        if self.path in ('/restart','/editorial','/replay-lab/start','/replay-lab/stop') and not self.require_operator():return
        if self.path == '/ingest':
            token = os.getenv('EVENT_HORIZON_INGEST_TOKEN','')
            if (session.transport is None or len(token)<32 or
                    not hmac.compare_digest(self.headers.get('Authorization','').encode('utf-8'),('Bearer '+token).encode('utf-8'))):
                self.send_json({'error':'Unauthorized ingress'},401);return
            try:
                length = body_length(self.headers,MAX_BODY)
                if self.headers.get_content_type()!='application/json' or not 0<length<=MAX_BODY:
                    raise ValueError('Invalid ingress body')
                payload = decode(self.rfile.read(length))
                target=viewer_sessions.find_run(payload['run_key']) or session
                with observe.incoming({k.lower():v for k,v in self.headers.items()}):
                    result = target.receive_ingress(payload)
                self.send_json(result)
            except IngressConflict as error:self.send_json({'error':str(error)},409)
            except (ValueError,UnicodeError):self.send_json({'error':'Invalid ingress envelope'},400)
            except OSError:self.send_json({'error':'Processing unavailable'},503)
            return
        if self.path not in ('/restart', '/editorial', '/displayed', '/presentation','/replay-lab/start','/replay-lab/stop','/viewer-session','/viewer-session/start','/viewer-session/release'):
            self.send_error(404)
            return
                                                                        
        allowed_hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        host = self.headers.get('Host', '')
        origin = self.headers.get('Origin')
        public_origin = os.getenv('EVENT_HORIZON_PUBLIC_ORIGIN','')
        public = urlsplit(public_origin)
        if public.scheme=='https' and public.netloc:allowed_hosts.add(public.netloc)
        expected_origin = public_origin if public_origin and host==public.netloc else f'http://{host}'
        if host not in allowed_hosts or (origin is not None and origin != expected_origin):
            self.send_json({'error': 'The request must originate from the application.'}, status=403)
            return
        try:
            length = body_length(self.headers,4096)
            if self.headers.get_content_type() != 'application/json' or not 0 < length <= 4096:
                raise ValueError('Expected a small JSON object with match settings.')
            settings = json.loads(self.rfile.read(length))
            if self.path.startswith('/viewer-session'):
                if settings!={}:raise ValueError('Viewer session requests require an empty object')
                try:
                    if self.path=='/viewer-session':
                        self.send_json({'token':viewer_sessions.create()});return
                    token=self.headers.get('X-EH-Viewer-Session','')
                    if self.path.endswith('/release'):
                        viewer_sessions.release(token);self.send_json({'released':True});return
                    target=viewer_sessions.start(token)
                    self.send_json({'started':True,'run_key':target.run_key});return
                except ViewerBusy as error:self.send_json({'error':str(error)},429);return
                except ViewerExpired as error:self.send_json({'error':str(error)},410);return
            if self.path in ('/displayed','/presentation') and self.headers.get('X-EH-Viewer-Session'):
                try:session=viewer_sessions.get(self.headers['X-EH-Viewer-Session'])
                except ViewerExpired as error:self.send_json({'error':str(error)},410);return
            if self.path in ('/replay-lab/start','/replay-lab/stop'):
                try:
                    if self.path.endswith('/start'):
                        if not isinstance(settings,dict) or set(settings)!={'seed','seconds','speed'}:
                            raise ValueError('Seed, seconds and speed are required')
                        result=replay_lab.start(**settings)
                    else:
                        if not isinstance(settings,dict) or set(settings)!={'run_key'}:
                            raise ValueError('Run identity is required')
                        result=replay_lab.cancel(settings['run_key'])
                except RuntimeError as error:self.send_json({'error':str(error)},409);return
                self.send_json(result);return
            if self.path == '/presentation':
                allowed={'run_key','token','material_id','revision','event_id','render_ms','request_ms','visible'}
                if not isinstance(settings,dict) or set(settings)!=allowed:raise ValueError('Invalid presentation receipt')
                self.send_json({'accepted':session.acknowledge_presentation(settings)})
                return
            if self.path == '/displayed':
                if not isinstance(settings, dict) or set(settings) != {'run_id', 'event_id'}:
                    raise ValueError('Invalid display acknowledgement.')
                session.acknowledge_display(settings)
                self.send_json({'displayed': True})
                return
            if self.path == '/editorial':
                allowed = {'run_id', 'moment_id', 'revision', 'fact_fingerprint', 'action', 'copy','language'}
                if not isinstance(settings, dict) or set(settings) - allowed:
                    raise ValueError('Invalid material review request.')
                if not isinstance(settings.get('moment_id'), str) or type(settings.get('revision')) is not int:
                    raise ValueError('The episode and its revision are required.')
                result = session.editorial_action(settings)
                self.send_json({'editorial': result})
                return
            if not isinstance(settings, dict) or set(settings) - {'seed', 'scenario'}:
                raise ValueError('Only seed and scenario settings are supported.')
            if ('seed' in settings and settings['seed'] is None) or ('scenario' in settings and settings['scenario'] is None):
                raise ValueError('Settings cannot be null.')
            session.restart(settings.get('seed'), settings.get('scenario'))
        except (sqlite3.Error, OSError):
            self.send_json({'error': 'Event archive unavailable. The previous match is preserved.'}, status=503)
            return
        except EditorialConflict as error:
            self.send_json({'error': str(error)}, status=409)
            return
        except (ValueError, UnicodeDecodeError) as error:
            self.send_json({'error': str(error)}, status=400)
            return
        self.send_json(session.snapshot())

    def send_json(self, data, status=200):
        self.send_content(json.dumps(data, ensure_ascii=False).encode('utf-8'),
                          'application/json; charset=utf-8', status)

    def send_content(self, content, kind, status=200):
        if kind.startswith('application/json') and getattr(self,'ui_language','en') in ('fr','it','es','pt') and urlsplit(self.path).path != '/story-language':
            from global_localization import translate_tree
            content=json.dumps(translate_tree(json.loads(content),self.ui_language,audience=getattr(self,'ui_audience','analyst')),ensure_ascii=False).encode('utf-8')
        self.response_policy = policy(content,kind)
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_):
        pass


def run_clock():
    while not stop.wait(.02):
        try:session.pump()
        except Exception as error:
            with session.lock:
                session.pipeline.last_error = 'Match worker stopped unexpectedly.'
            observe.record('eh.worker.failure',0,'error')
            logging.getLogger('event_horizon').error('Match worker stopped: %s',type(error).__name__)


def run_replay_lab():
    previous=None
    while not stop.wait(.02):
        try:
            with replay_lab.lock:
                current=replay_lab.run
                active=current and not (current.complete or current.cancelled or current.error or current.first_mismatch)
            if active:replay_lab.pump()
                                                                         
            with replay_lab.lock:
                run=replay_lab.run
                terminal=(run.run_key,run.complete,bool(run.first_mismatch or run.error),run.cancelled) if run else None
                elapsed_ms=max(0,run.last_now-run.started)*1000 if run else 0
            if terminal!=previous and terminal and any(terminal[1:]):
                observe.record('eh.replay.verification',elapsed_ms,'error' if terminal[2] else 'ok')
            previous=terminal
        except Exception as error:
            with replay_lab.lock:
                if replay_lab.run:replay_lab.run.error='Verification worker failed: '+type(error).__name__
            observe.record('eh.replay.failure',0,'error')


def run_narrator():
    loop = asyncio.new_event_loop()
    try:
        while not stop.is_set():
            work=False
            for target in [session,*viewer_sessions.active()]:
                try:key,packet,trace_headers=target.ai_queue.get_nowait()
                except Empty:continue
                work=True
                loop.run_until_complete(target.process_narrative_job(key,packet,trace_headers))
            if not work:stop.wait(.2)
    finally:
        if session.narrator is not None:
            loop.run_until_complete(session.narrator.close())
        loop.close()


def main():
    global session
    operator_access.validate_configuration()
    observe.configure()
    transport = ingress_from_environment()
    if os.getenv('EVENT_HORIZON_BLOB_ACCOUNT_URL'):
        from azure_journal import BlobEventJournal
        journal = BlobEventJournal.from_environment()
    else:
        data = Path(os.getenv('EVENT_HORIZON_DATA_DIR',str(ROOT/'data')))
        data.mkdir(parents=True,exist_ok=True)
        journal = EventJournal(data/'events.sqlite3')
    session = MatchSession(journal=journal,vision_enabled=True,transport=transport)
    session.narrator, session.narrator_status = from_environment()
    bind = os.getenv('EVENT_HORIZON_BIND','127.0.0.1')
    port = int(os.getenv('EVENT_HORIZON_PORT','8000'))
    server = BoundedHTTPServer((bind,port), Handler)
    worker = threading.Thread(target=run_clock,daemon=True)
    narrator_worker = threading.Thread(target=run_narrator,daemon=True) if session.narrator else None
    replay_worker = threading.Thread(target=run_replay_lab,daemon=True)
    replay_worker.start()
    worker.start()
    if narrator_worker:narrator_worker.start()
    import signal
    def terminate(*_):
        stop.set()
        threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,terminate)
    print(f'Event Horizon listening on {bind}:{port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        stop.set()
        server.server_close()
        viewer_sessions.close()
        worker.join(timeout=12)
        replay_worker.join(timeout=3)
        if narrator_worker:narrator_worker.join(timeout=32)
        if transport:transport.close()
        journal.close()
        observe.close()


if __name__ == '__main__':main()
