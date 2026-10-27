                                                                                  

                                                                                
                                                                              
                                                                              
   
from base64 import b64encode
from collections import OrderedDict
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import struct
import threading
from urllib.parse import quote
import zlib

from delivery import MaterialStream, overlay, metric_selection
from language_contract import language_proof
from display_adapter import DisplayAdapter
from locales import event_display, translated_packet
from presentation import preference_key
from raster import render, CALIBRATION
from roster import named_metadata, player_name
from match_arc import build_arc
from rhythm_lens import build as rhythm_lens

SCHEMA='eh-full-match-demo-1'
_arc_cache=OrderedDict()
_arc_cache_lock=threading.Lock()
_ARC_CACHE_LIMIT=4


def archive_story_arc(path,db,identity,language):
                                                                              

                                                                                
                                                                             
                                                                               
                                                                              
       
    if language not in ('en','cs','de','fr','it','es','pt'):
        raise ValueError('Unsupported story arc language')
    path=Path(path).resolve()
    def generation():
        stat=path.stat()
        return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
    stamp=generation()
    key=(str(path),stamp,identity['run_key'],identity['match_id'])
    with _arc_cache_lock:
        if key in _arc_cache:
            _arc_cache.move_to_end(key)
            return deepcopy(_arc_cache[key][language])
        events=[]
        for row in db.execute('SELECT payload FROM events WHERE time<=5400 ORDER BY time,id'):
            event=unpack(row[0])
            events.append({field:event[field] for field in ('id','time','kind','team','score','details') if field in event})
        arcs={code:build_arc(events,0,5400,True,code) for code in ('en','cs','de','fr','it','es','pt')}
        if generation()==stamp:
            _arc_cache[key]=arcs
            while len(_arc_cache)>_ARC_CACHE_LIMIT:
                _arc_cache.popitem(last=False)
        return deepcopy(arcs[language])


def pack(value):
    return zlib.compress(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),3)


def unpack(value):return json.loads(zlib.decompress(value))


def compact(value):
                                                                                 
    if isinstance(value,dict):return {k:compact(v) for k,v in value.items() if k!='frame'}
    if isinstance(value,list):return [compact(v) for v in value]
    return value


class DemoWriter:
    def __init__(self,path,session):
        self.db=sqlite3.connect(path)
        self.db.executescript('''
          CREATE TABLE meta(key TEXT PRIMARY KEY,value BLOB NOT NULL);
          CREATE TABLE frames(tick INTEGER PRIMARY KEY,geometry BLOB NOT NULL,screen BLOB NOT NULL);
          CREATE TABLE events(id INTEGER PRIMARY KEY,time REAL NOT NULL,payload BLOB NOT NULL);
          CREATE TABLE materials(sequence INTEGER PRIMARY KEY,id TEXT NOT NULL,available REAL NOT NULL,record BLOB NOT NULL);
          CREATE INDEX material_time ON materials(available);
          CREATE TABLE episodes(id TEXT PRIMARY KEY,time REAL NOT NULL,available REAL NOT NULL,packet BLOB NOT NULL);
          CREATE TABLE summaries(key TEXT PRIMARY KEY,packet BLOB NOT NULL);
        ''')
        self.saved_events=self.saved_materials=0
        self.run_key=hashlib.sha256(('demo:'+session.match.match_id).encode()).hexdigest()[:32]
        self.put('identity',{'schema':SCHEMA,'run_key':self.run_key,'match_id':session.match.match_id,
            'metadata':named_metadata(session.match.metadata()),'settings':session.match.settings.as_dict(),
            'players':[{'team':p.team,'number':p.number,'name':player_name(p.team,p.number)} for p in session.match.players]})

    def put(self,key,value):self.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,pack(value)))

    def capture(self,session):
        match=session.match;state=session.confirmed_frame
        geometry=struct.pack('<46d',*[v for p in match.players for v in (p.x,p.y)],*match.ball)
        observation=deepcopy(getattr(session.camera.recognizer,'current',None)) if session.camera else None
        screen={k:state[k] for k in ('clock','score','possession','passes','attempts','shots','pressure','phase','period','finished')}
        screen.update(event_count=session.confirmed_count,observation=observation)
        self.db.execute('INSERT INTO frames VALUES(?,?,?)',(match.tick,geometry,pack(screen)))
        for event in session.pipeline.events[self.saved_events:]:
            self.db.execute('INSERT INTO events VALUES(?,?,?)',(event['id'],event['time'],pack(event)))
        self.saved_events=len(session.pipeline.events)
        for record in session.materials.history[self.saved_materials:]:
            self.db.execute('INSERT INTO materials VALUES(?,?,?,?)',
                (record['sequence'],record['material_id'],record['available_at'],pack(compact(record))))
        self.saved_materials=len(session.materials.history)
        if match.tick%1200==0:self.db.commit()

    def finalize(self,session,report,summaries):
        for moment in session.insights.moments.values():
            packet=session.insights.moment_data(moment)
            available=max(r['available_at'] for r in session.materials.history if r['material_id']==moment.id)
            self.db.execute('INSERT INTO episodes VALUES(?,?,?,?)',(moment.id,moment.time,available,pack(compact(packet))))
        for key,value in summaries.items():self.db.execute('INSERT INTO summaries VALUES(?,?)',(key,pack(value)))
        self.put('report',report);self.db.commit();self.db.close()

    def close(self):self.db.close()


def summary_key(language,audience,team,player):return f'{language}:{audience}:{team}:{player}'


class DemoReader:
    def __init__(self,path):self.path=Path(path)

    def connect(self):return closing(sqlite3.connect('file:'+quote(str(self.path.resolve()))+'?mode=ro&immutable=1',uri=True))

    @staticmethod
    def meta(db,key):
        row=db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        if row is None:raise ValueError('Incomplete demonstration archive')
        return unpack(row[0])

    def manifest(self):
        with self.connect() as db:
            identity=self.meta(db,'identity');report=self.meta(db,'report')
            episodes=[]
            for key,time,available,body in db.execute('SELECT id,time,available,packet FROM episodes ORDER BY time'):
                packet=unpack(body)
                episodes.append({'id':key,'time':time,'available_at':available,'kind':packet['kind'],
                                 'team':packet['team'],'actors':packet['actors'],'verified':packet['verified']})
            return {**identity,'report':report,'episodes':episodes}

    def event(self,event_id,language='en'):
        with self.connect() as db:
            identity=self.meta(db,'identity')
            row=db.execute('SELECT payload FROM events WHERE id=?',(event_id,)).fetchone()
            if row is None:raise KeyError('Unknown demonstration event')
            event=unpack(row[0])
            return {'event':event,'display':event_display(event,language),'run_key':identity['run_key'],'match_id':identity['match_id']}

    def story_language(self,at,language='en',audience='fan',team=None,player=None,episode=None):
                                                                                   
        from story_languages import render
        if type(at) not in (int,float) or not math.isfinite(at) or not 0<=at<=5400:
            raise ValueError('Invalid story playback time')
        with self.connect() as db:
            identity=self.meta(db,'identity');duration=self.meta(db,'report')['match_seconds']
            if at>duration:raise ValueError('Story playback exceeds archive')
            if episode is not None:
                if not db.execute('SELECT 1 FROM episodes WHERE id=?',(episode,)).fetchone():
                    raise KeyError('Unknown story episode')
            else:
                row=db.execute('SELECT id FROM episodes WHERE available<=? ORDER BY time DESC LIMIT 1',(at,)).fetchone()
                episode=row[0] if row else None
            row=db.execute('SELECT record FROM materials WHERE id=? AND available<=? ORDER BY sequence DESC LIMIT 1',(episode,at)).fetchone() if episode else None
            packet=unpack(row[0])['packet'] if row else None
        summary=None
        if at>=5400:
            original=language if language in ('en','cs','de') else 'en'
            summary=self.state(at,original,audience,team,player)['summary']
        result=render(packet,language,audience,team,player,at,summary)
        return {**result,'run_key':identity['run_key'],'match_id':identity['match_id'],'source':'demo'}

    def lenses(self,episode_id,at):
                                                                                     
        if type(at) not in (int,float) or not math.isfinite(at) or not 0<=at<=5400:
            raise ValueError('Invalid playback time')
        with self.connect() as db:
            identity=self.meta(db,'identity')
            duration=self.meta(db,'report')['match_seconds']
            if at>duration:raise ValueError('Playback exceeds recorded duration')
            if not db.execute('SELECT 1 FROM episodes WHERE id=?',(episode_id,)).fetchone():
                raise KeyError('Unknown demonstration episode')
            tick=min(int(at*20+1e-8),round(duration*20))
            clock=tick/20
            row=db.execute('SELECT record FROM materials WHERE id=? AND available<=? ORDER BY sequence DESC LIMIT 1',
                           (episode_id,clock)).fetchone()
            result={'schema':'eh-demo-lenses-1','episode_id':episode_id,'clock':clock,
                    'run_key':identity['run_key'],'match_id':identity['match_id']}
            if row is None:return {**result,'status':'waiting','views':[],'checks':[]}
            record=unpack(row[0]);packet=record['packet']
            proofs=[language_proof(packet,mode,identity['run_key'],identity['match_id'])
                    for mode in ('fan','analyst','player')]
            views=[{'mode':mode,'language':view['language'],
                    **{key:view[key] for key in ('title','what','why','change','caption')},
                    'facts_sha256':view['facts_sha256']}
                   for mode,proof in zip(('fan','analyst','player'),proofs) for view in proof['views']]
            protected=[view['protected'] for proof in proofs for view in proof['views']]
            checks=[{'key':'protected_facts_across_modes','passed':all(value==protected[0] for value in protected)},
                    {'key':'nine_renditions','passed':len(views)==9}]
            checks.extend({'key':f'{mode}_language_{check["key"]}','passed':check['passed']}
                          for mode,proof in zip(('fan','analyst','player'),proofs)
                          for check in proof['parity']['checks'])
            return {**result,'status':'passed' if all(c['passed'] for c in checks) else 'failed',
                    'revision':packet['revision'],'facts_sha256':views[0]['facts_sha256'],
                    'source_event_ids':packet['evidence_ids'],'views':views,'checks':checks}

    def state(self,at=0,language='en',audience='fan',team=None,player=None,selected=None,metrics=None):
        if type(at) not in (int,float) or not math.isfinite(at) or not 0<=at<=5400:raise ValueError('Invalid playback time')
        selected_metrics=metric_selection(metrics)
        with self.connect() as db:
            identity=self.meta(db,'identity');duration=self.meta(db,'report')['match_seconds']
            if at>duration:raise ValueError('Playback exceeds recorded duration')
            tick=min(int(at*20+1e-8),round(duration*20))
            row=db.execute('SELECT geometry,screen FROM frames WHERE tick=?',(tick,)).fetchone()
            if row is None:raise KeyError('Missing camera frame')
            coordinates=struct.unpack('<46d',row[0]);screen=unpack(row[1]);clock=screen['clock']
            players=[{**p,'x':coordinates[i*2],'y':coordinates[i*2+1]} for i,p in enumerate(identity['players'])]
            png=render(players,coordinates[-2:])
            records=[unpack(r[0]) for r in db.execute('SELECT record FROM materials WHERE available>=? AND available<=? ORDER BY sequence',(max(0,clock-12),clock))]
                                                                               
            latest={r['material_id']:r for r in records}
            stream=MaterialStream();kwargs=dict(audience=audience,language=language,team=team,player=player,metrics=selected_metrics)
            cues=[]
            for record in latest.values():
                if record['available_at']>=5400:continue
                cue=overlay(stream.render(record,**kwargs),identity['match_id'],identity['run_key'],**kwargs)
                cue['priority']=(100 if record['kind']=='moment' and record['facts'].get('outcome')=='goal' else
                    (4 if player and player in record['actors'] else 0)+(2 if team is not None and record['team']==team else 0)+(1 if record['kind'] in ('moment','period') else 0))
                cues.append(cue)
            feed={'match_id':identity['match_id'],'run_key':identity['run_key'],
                  'viewer_key':preference_key(audience,language,team,player,selected_metrics),
                  'playback_clock':clock,'overlays':cues}
            adapter=DisplayAdapter();adapter.update(feed,clock)
            active=adapter.visible.get('narrative')
            record=latest.get(active['material_id']) if active else None
            card=stream.render(record,**kwargs) if record else None
            comparison=None
            if record:
                comparison={mode:stream.render(record,**{**kwargs,'audience':mode}) for mode in ('fan','analyst','player')}
            episode=None
            if selected:
                                                                               
                row=db.execute('SELECT record FROM materials WHERE id=? AND available<=? ORDER BY sequence DESC LIMIT 1',(selected,clock)).fetchone()
                if row:
                    selected_record=unpack(row[0])
                    if selected_record['kind']=='moment':
                        packet=selected_record['packet'];episode=translated_packet(packet,language,audience)
                        episode['sources']=[{'id':n,'href':f'/demo/event?id={n}&language={language}'} for n in packet['evidence_ids']]
                        episode['card']=stream.render(selected_record,**kwargs)
                        last_id=packet['evidence_ids'][-1]
                        source=db.execute('SELECT payload FROM events WHERE id=?',(last_id,)).fetchone()
                        episode['scene_event']=unpack(source[0]) if source else None
                        comparison={mode:stream.render(selected_record,**{**kwargs,'audience':mode}) for mode in ('fan','analyst','player')}
                                                                           
                                                                               
            rhythm_row=db.execute("SELECT record FROM materials WHERE id GLOB 'period-[0-9]*' AND available<=? ORDER BY available DESC LIMIT 1",(clock,)).fetchone()
            rhythm=rhythm_lens(unpack(rhythm_row[0])['facts']) if rhythm_row else None
            summary=None
            if clock>=5400:
                key=summary_key('en' if language in ('fr','it','es','pt') else language,audience,team, None if player is None else f"{player['team']}:{player['number']}")
                row=db.execute('SELECT packet FROM summaries WHERE key=?',(key,)).fetchone()
                if row:summary=unpack(row[0])
                if summary is not None:summary['story_arc']=archive_story_arc(self.path,db,identity,language)
            result={**screen,'schema':SCHEMA,'run_key':identity['run_key'],'match_id':identity['match_id'],
                'frame_png':b64encode(png).decode(),'calibration':deepcopy(CALIBRATION),
                'card':card,'overlay':active,'episode':episode,'comparison':comparison,'summary':summary,'rhythm':rhythm,
                'language':language,'audience':audience,'team':team,'player':player,
                'selected_metrics':selected_metrics,'source':'recorded synthetic match; statistics are the confirmed original read model'}
            if language in ('fr','it','es','pt'):
                from global_localization import translate_tree
                return translate_tree(result,language,audience=audience)
            return result
