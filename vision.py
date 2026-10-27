                                                    

                                                                          
                                                                              
                                                                        
   
from collections import deque
from copy import deepcopy
import math

from raster import decode_png, KITS, BALL, WIDTH, PAD, SCALE
from roster import player_name
from pass_quality import assess


def locate(rgb, colour, minimum, previous=None):
    xs,ys=[],[]
    ranges=[(0,len(rgb))]
    if previous is not None:
        x,y=round(PAD+previous[0]*SCALE),round(PAD+previous[1]*SCALE)
        ranges=[((row*WIDTH+max(0,x-24))*3,(row*WIDTH+min(WIDTH,x+25))*3)
                for row in range(max(0,y-24),min(504,y+25))]
    for left,right in ranges:
        pos=left-3
        while True:
            pos=rgb.find(colour,pos+3,right)
            if pos<0:break
            if pos%3:pos-=2;continue
            index=pos//3;xs.append(index%WIDTH);ys.append(index//WIDTH)
    if len(xs)<minimum and previous is not None:return locate(rgb,colour,minimum)
    if len(xs)<minimum:return None
                                                                   
    if max(xs)-min(xs)>12 or max(ys)-min(ys)>12:return None
    return ((min(xs)+max(xs))/2-PAD)/SCALE,((min(ys)+max(ys))/2-PAD)/SCALE


class VideoRecognizer:
    version='eh-pixel-tracker-1'

    def __init__(self):
        self.clock=-1.;self.frame_id=0;self.tracks={};self.ball=None
        self.events=[];self.last_owner=None;self.candidate=None;self.candidate_count=0
        self.flight=None;self.pressure=None;self.period=1
        self.teams=[dict(attempts=0,passes=0,shots=0,tackles=0) for _ in range(2)]
        self.players={f'{t}:{n}':dict(attempts=0,passes=0,shots=0,tackles=0) for t,n in KITS}
        self.recent=deque(maxlen=40)

    def emit(self,kind,time,actors=(),**facts):
        event={'id':f'cv-{len(self.events)+1}','kind':kind,'time':round(time,2),
               'available_at':self.clock,'actors':[{'team':a[0],'number':a[1],'name':player_name(*a)} for a in actors],
               'frame_ids':[max(1,self.frame_id-1),self.frame_id],
               'facts':facts,'source':'pixels','model':self.version}
        self.events.append(event);self.recent.append(event)
        if actors and kind in ('pass_started','pass_completed','shot','tackle'):
            key={'pass_started':'attempts','pass_completed':'passes','shot':'shots','tackle':'tackles'}[kind]
            self.teams[actors[0][0]][key]+=1
            self.players[f'{actors[0][0]}:{actors[0][1]}'][key]+=1
        return event

    def observe(self,png,time,period=1,in_play=True):
        if not math.isfinite(time) or time<=self.clock or period not in (1,2):
            raise ValueError('Video timestamps must increase')
        rgb=decode_png(png)
        positions={key:p for key,colour in KITS.items() if (p:=locate(rgb,colour,6,self.tracks.get(key,{}).get('position'))) is not None}
        ball=locate(rgb,BALL,5,self.ball)
        old_ball=self.ball;previous=self.clock;self.clock=time;self.frame_id+=1
        detected=[]
        for key,p in positions.items():
            old=self.tracks.get(key);speed=None
            continuous=old is not None and 0<time-old['last_seen']<=.21
            delta=math.dist(p,old['position']) if continuous else 0
            if continuous and delta/(time-old['last_seen'])<=9:
                speed=delta/(time-old['last_seen'])
            else:delta=0
            track={'position':p,'last_seen':time,'distance_m':(old['distance_m'] if old else 0)+(delta if in_play else 0),
                   'speed_mps':round(speed,2) if in_play and speed is not None else None,
                   'name':player_name(*key),'team':key[0],'number':key[1]}
            self.tracks[key]=track
            detected.append({**track,'x':round(p[0],3),'y':round(p[1],3),'distance_m':round(track['distance_m'],1)})
        ball_speed=None
        if ball and old_ball and 0<time-previous<=.21:
            displacement=math.dist(ball,old_ball)
            if displacement/(time-previous)<=45:ball_speed=displacement/(time-previous)
        self.ball=ball
        reset=period!=self.period or not in_play or ball is None or (old_ball is not None and ball_speed is None)
                                                                                
                                                                              
        if self.flight and self.flight['event'] and self.flight['kind']=='shot' and ball and old_ball and period==self.period:
            end=105 if self.flight['direction']==1 else 0
            crossed=(old_ball[0]-end)*(ball[0]-end)<=0 and (ball[0]-old_ball[0])*self.flight['direction']>0
            if crossed and ball[0]!=old_ball[0]:
                y=old_ball[1]+(end-old_ball[0])/(ball[0]-old_ball[0])*(ball[1]-old_ball[1])
                if abs(y-34)<=3.66:
                    self.emit('goal',time,(self.flight['sender'],),start_id=self.flight['event']['id'],crossing_y=round(y,2))
                    self.flight=None
        self.period=period
        if reset:
            self.flight=None;self.last_owner=None;self.candidate=None;self.candidate_count=0;self.pressure=None
        elif ball is not None:
            nearest=min(positions,key=lambda k:math.dist(positions[k],ball)) if positions else None
            nearby=math.dist(positions[nearest],ball) if nearest else float('inf')
                                                                              
                                                                             
            owner=nearest if nearest and nearby<=1.6 and (ball_speed is None or ball_speed<9 or nearest==self.last_owner and nearby<=1.1) else None
            if owner==self.candidate:self.candidate_count+=1
            else:self.candidate,self.candidate_count=owner,1
            stable=owner if owner and self.candidate_count>=2 else None
            direction=(1 if self.last_owner and self.last_owner[0]==0 else -1)*(1 if period==1 else -1)
            if self.flight:
                flight=self.flight
                if owner and owner!=flight['sender'] and not flight.get('reception'):
                    flight['reception']={'owner':owner,'point':ball,'time':time,'frame_id':self.frame_id}
                if flight['event'] is None:
                    peak=max(flight['samples']+[ball_speed or 0])
                    shot=peak>=21 and (ball[0]-flight['origin'][0])*flight['direction']>0 and min(flight['origin'][0],105-flight['origin'][0])<=26
                    flight['kind']='shot' if shot else 'pass_started'
                    measurement=flight['measurement']
                    if ball_speed is not None and ball_speed>=max(flight['samples']):
                        measurement={'from':list(old_ball),'to':list(ball),'interval_s':round(time-previous,3),
                                     'distance_m':round(math.dist(old_ball,ball),3),'frame_ids':[self.frame_id-1,self.frame_id]}
                    flight['event']=self.emit(flight['kind'],flight['time'],(flight['sender'],),
                        speed_mps=round(peak,2),origin=list(flight['origin']),direction=flight['direction'],
                        measurement=measurement)
                    flight['event']['frame_ids']=[flight['frame_id'],self.frame_id]
                if old_ball and ball_speed is not None:
                    flight['path_m']+=math.dist(old_ball,ball)
                    if ball_speed>=10:
                        flight['samples'].append(ball_speed)
                        flight['sample_distance']+=math.dist(old_ball,ball)
                        flight['sample_time']+=time-previous
                if stable and stable!=flight['sender']:
                    sender=flight['sender'];success=sender[0]==stable[0]
                    reception=flight.get('reception')
                    endpoint=reception['point'] if reception and reception['owner']==stable else ball
                    kind=('pass_completed' if success else 'interception') if flight['kind']=='pass_started' else 'ball_recovered'
                    result=self.emit(kind,time,(sender,stable) if success else (stable,),
                        start_id=flight['event']['id'],success=success,distance_m=round(math.dist(flight['origin'],endpoint),2),
                        mean_speed_mps=round(sum(flight['samples'])/len(flight['samples']),2) if flight['samples'] else None,
                        elapsed_s=round(time-flight['time'],2),path_m=round(flight['path_m'],2))
                    result['frame_ids']=[flight['frame_id'],reception['frame_id'] if reception and reception['owner']==stable else self.frame_id]
                    result['facts']['reception_time']=reception['time'] if reception and reception['owner']==stable else time
                    result['facts']['end']=list(endpoint)
                    result['facts']['sender']={'team':sender[0],'number':sender[1],'name':player_name(*sender)}
                    result['facts']['receiver']={'team':stable[0],'number':stable[1],'name':player_name(*stable)}
                    result['facts']['speed_measurement']={'distance_m':round(flight['sample_distance'],3),'interval_s':round(flight['sample_time'],3),
                        'speed_mps':round(flight['sample_distance']/flight['sample_time'],2),'scope':'mean over moving ball intervals ≥10 m/s'}
                    result['facts']['mean_speed_mps']=result['facts']['speed_measurement']['speed_mps']
                    if flight['kind']=='pass_started':
                        result['facts']['quality']=assess(flight['origin'],endpoint,flight['opponents'],flight['direction'])
                    if sender[0]!=stable[0]:self.emit('possession_change',time,(stable,),from_team=sender[0],to_team=stable[0])
                    self.flight=None;self.last_owner=stable
                elif flight['kind']=='shot' and (ball[0]<0 or ball[0]>105) and abs(ball[1]-34)<=3.66:
                    self.emit('goal',time,(flight['sender'],),start_id=flight['event']['id'])
                    self.flight=None;self.last_owner=None
                elif time-flight['time']>6 or ball[0]<-.5 or ball[0]>105.5 or not -.5<=ball[1]<=68.5:
                    result=self.emit('pass_incomplete' if flight['kind']=='pass_started' else 'shot_end',time,(flight['sender'],),start_id=flight['event']['id'],success=False,
                        distance_m=round(math.dist(flight['origin'],ball),2),mean_speed_mps=round(flight['sample_distance']/flight['sample_time'],2),elapsed_s=round(time-flight['time'],2),
                        quality=assess(flight['origin'],ball,flight['opponents'],flight['direction']))
                    result['facts']['sender']={'team':flight['sender'][0],'number':flight['sender'][1],'name':player_name(*flight['sender'])}
                    self.flight=None;self.last_owner=None
            elif (self.last_owner and ball_speed is not None and ball_speed>=10 and owner is None and old_ball
                  and self.last_owner in positions and math.dist(positions[self.last_owner],ball)>1.8):
                sender=self.last_owner
                dx,dy=ball[0]-old_ball[0],ball[1]-old_ball[1]
                shot=ball_speed>=21 and dx*direction>0 and min(old_ball[0],105-old_ball[0])<=26
                kind='shot' if shot else 'pass_started'
                self.flight={'sender':sender,'kind':kind,'time':previous,'origin':old_ball,'path_m':math.dist(old_ball,ball),
                             'samples':[ball_speed],'event':None,'frame_id':self.frame_id-1,
                             'measurement':{'from':list(old_ball),'to':list(ball),'interval_s':round(time-previous,3),
                                 'distance_m':round(math.dist(old_ball,ball),3),'frame_ids':[self.frame_id-1,self.frame_id]},
                             'sample_distance':math.dist(old_ball,ball),'sample_time':time-previous,
                             'opponents':[p for k,p in positions.items() if k[0]!=sender[0]],'direction':direction}
            elif stable:
                if self.last_owner and stable!=self.last_owner and stable[0]!=self.last_owner[0]:
                    self.emit('tackle',time,(stable,),from_player=list(self.last_owner))
                    self.emit('possession_change',time,(stable,),from_team=self.last_owner[0],to_team=stable[0])
                self.last_owner=stable
            possession=stable or (self.flight['sender'] if self.flight else self.last_owner)
            if possession:
                opponents=[k for k,p in positions.items() if k[0]!=possession[0] and math.dist(p,ball)<=5]
                counts=(1-possession[0],len(opponents))
                if counts!=self.pressure:
                    self.emit('pressure',time,tuple(opponents),pressing_team=counts[0],count=counts[1])
                    self.pressure=counts
        self.current={'frame_id':self.frame_id,'time':round(time,2),'period':period,'in_play':in_play,
                      'players':detected,'ball':{'x':ball[0],'y':ball[1],'speed_mps':round(ball_speed,2) if ball_speed is not None else None} if ball else None,
                      'owner':list(stable) if not reset and stable else None}
        return deepcopy(self.current)

    def snapshot(self):
        teams=deepcopy(self.teams)
        for team in teams:team['accuracy_pct']=round(100*team['passes']/team['attempts'],1) if team['attempts'] else None
        players=deepcopy(self.players)
        for p in players.values():p['accuracy_pct']=round(100*p['passes']/p['attempts'],1) if p['attempts'] else None
        return {'schema_version':'eh-recognition-1','model':self.version,'observation':deepcopy(getattr(self,'current',None)),
                'events':deepcopy(list(self.recent)),'event_count':len(self.events),'teams':teams,'player_statistics':players}
