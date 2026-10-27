                                                                          

                                                                            
                                                                       
                                                                                 
   
import math
from scenarios import ScenarioExpectations


class GeneratorConsistencyError(ValueError):
    pass


class GeneratorChecks:
    def __init__(self,match):
        self.tick=-1;self.last_id=0;self.score=[0,0];self.attempts=[0,0]
        self.completed=[0,0];self.shots=[0,0];self.shooting=None
        self.team=match.possession_team;self.positions=None;self.ball=None
        self.in_play=0.;self.possession=[0.,0.];self.stopped=False;self.period=match.period
        self.checked_frames=0;self.error=None;self.violations=0
        self.expectations=ScenarioExpectations(match.scenario)
        self.validate(match)

    def require(self,condition,message):
        if not condition:raise ValueError(message)

    def validate(self,m):
        try:self._validate(m)
        except (ValueError,IndexError,KeyError,TypeError) as error:
            self.error=str(error);self.violations+=1
            raise GeneratorConsistencyError('Generator consistency: '+str(error)) from error

    def _validate(self,m):
        self.require(m.tick==self.tick+1,'Non-consecutive tick')
        self.require(math.isfinite(m.clock) and abs(m.clock-m.tick*.05)<1e-7,'Invalid clock')
        self.require(len(m.players)==22 and {(p.team,p.number) for p in m.players}=={(t,n) for t in (0,1) for n in range(1,12)},'Invalid lineup')
        for i,p in enumerate(m.players):
            self.require(math.isfinite(p.x) and math.isfinite(p.y) and .5<=p.x<=104.5 and .5<=p.y<=67.5,'Player outside pitch')
            if self.positions:self.require(math.dist(p.position,self.positions[i])<=6.2*.05+1e-7,'Player movement exceeds limit')
        self.require(len(m.ball)==2 and all(type(x) in (float,int) and math.isfinite(x) for x in m.ball),'Invalid ball coordinates')
        if self.ball:self.require(math.dist(m.ball,self.ball)<=25*.05+1e-7,'Ball movement exceeds limit')
        new=m.events[self.last_id:]
        if not (0<=m.ball[0]<=105 and 0<=m.ball[1]<=68):
            boundary=any(e['kind'] in ('goal','goal_kick','corner','throw_in') for e in new)
            self.require(bool(m.restart) and (self.stopped or boundary),'Ball left pitch without a boundary stoppage')
        if m.owner is not None:
            self.require(type(m.owner) is int and 0<=m.owner<22,'Invalid owner')
            self.require(m.players[m.owner].team==m.possession_team and math.dist(m.players[m.owner].position,m.ball)<=1.8,'Possession owner disagrees with ball')
        before=self.team
        active=self.tick>=0 and not self.stopped and not m.finished and m.period==self.period
        if active:self.in_play+=.05;self.possession[before]+=.05
        for e in new:
            self.require(e['id']==self.last_id+1 and e['tick']==m.tick and e['time']==round(m.clock,2),'Invalid event sequence or time')
            kind,team=e['kind'],e['team']
            self.require(team in (0,1),'Invalid event team')
            if kind=='pass_started':self.attempts[team]+=1;self.shooting=None
            elif kind=='pass_completed':self.completed[team]+=1
            elif kind=='shot':self.shots[team]+=1;self.shooting=team
            elif kind=='goal':
                self.require(self.shooting==team,'Goal has no preceding shot by that team')
                direction=(1 if team==0 else -1)*(1 if e['period']==1 else -1)
                end=105 if direction==1 else 0
                self.require(self.ball is not None and (e['ball'][0]>105 if direction==1 else e['ball'][0]<0), 'Goal has no line crossing')
                fraction=(end-self.ball[0])/(e['ball'][0]-self.ball[0])
                crossing_y=self.ball[1]+fraction*(e['ball'][1]-self.ball[1])
                self.require(0<=fraction<=1 and abs(crossing_y-34)<=3.66+.00001,'Goal does not cross between posts')
                self.score[team]+=1;self.shooting=None
            if kind in ('save','shot_blocked','goal_kick','corner','throw_in','second_half','full_time','restart_taken'):self.shooting=None
            if kind in ('kickoff','restart_taken','pass_completed','interception','save','shot_blocked','tackle','ball_recovered'):self.team=team
            if kind=='pressure':
                counts=e['details']['counts'];radius=e['details']['radius_m']
                gaps=[math.dist((p['x'],p['y']),e['ball']) for p in e['frame'] if p['team']==team]
                self.require(radius==5 and counts[1-team]==0 and (sum(g<=4.999 for g in gaps)<=counts[team]<=sum(g<=5.001 for g in gaps) or counts==[0,0] and (m.restart or m.finished)), 'Pressure disagrees with coordinates')
            for field,expected in (('score',self.score),('attempts',self.attempts),('passes',self.completed),('shots',self.shots)):
                self.require(e[field]==expected,'Event '+field+' disagrees with actions')
            self.last_id=e['id']
        for field,expected in (('score',self.score),('attempts',self.attempts),('completed',self.completed),('shots',self.shots)):
            self.require(getattr(m,field)==expected,'State '+field+' disagrees with events')
        self.require(m.possession_team==self.team,'Possession changed without a touch')
        changes=[e for e in new if e['kind']=='possession_change']
        self.require(len(changes)==int(self.tick>=0 and before!=self.team),'Missing or spurious possession change')
        if changes:self.require(changes[0]['details']=={'from_team':before,'to_team':self.team},'Wrong possession transition')
        self.require(abs(m.in_play_time-self.in_play)<1e-6 and all(abs(a-b)<1e-6 for a,b in zip(m.possession_time,self.possession)),'Possession duration disagrees with live intervals')
        self.expectations.consume(new)
        self.tick=m.tick;self.checked_frames+=1;self.positions=[p.position for p in m.players]
        self.ball=tuple(m.ball);self.stopped=bool(m.restart);self.period=m.period

    def snapshot(self,clock,recognition=None):
        scenario=self.expectations.snapshot(clock)
        if recognition is not None:
            for item in scenario['expectations']:
                evidence=item['evidence']
                item['recognition']=(recognition.get(evidence['event_id'],{'status':'pending'})
                                     if evidence else {'status':'no_source_event' if item['status']=='failed' else 'pending_source'})
        return {'schema_version':'eh-generator-checks-1','status':'failed' if self.error else 'passed',
                'checked_frames':self.checked_frames,'checked_events':self.last_id,
                'violations':self.violations,'error':self.error,
                'rules':['score_from_goals','passes_from_touches','possession_from_touches',
                         'pitch_boundaries','bounded_movement','pressure_from_positions','ordered_event_clock'],
                'scenario':scenario}
