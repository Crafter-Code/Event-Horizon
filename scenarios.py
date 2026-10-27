                                                                             

                                                                           
                                                                          
                                                                                
   

from global_localization import locale_map, translate_tree, translate_text
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

BASE = {'id':'open_play','version':1,
        'title':locale_map({'de':'Freies Spiel','en':'Open play','cs':'Otevřená hra'}),
        'description':locale_map({'de':'Freies Spiel: Spielerentscheidungen und Ballphysik bestimmen den Spielverlauf.',
                       'en':'Free play: player decisions and ball physics determine the match.',
                       'cs':'Volná hra: průběh určují rozhodnutí hráčů a fyzika míče.'}),
        'expectations':[]}
POLICY = {'chasers':1,'closing_gap_m':3,'defending_shift_m':-8,
          'tackle_rate':.25,'forward_weight':.28,'decision_scale':1,'closing_mps':2.7}


def player_index(value):
    if not isinstance(value,str) or not re.fullmatch(r'[01]:(?:[1-9]|10|11)',value):
        raise ValueError('Invalid scenario player id')
    team,number=map(int,value.split(':'))
    return team*11+number-1


def finite(value, low, high):
    return type(value) in (int,float) and math.isfinite(value) and low<=value<=high


def validate_profile(data):
    if not isinstance(data,dict) or set(data)!={'id','version','title','description','initial','policy','sequence','expectations'}:
        raise ValueError('Invalid scenario fields')
    if not isinstance(data['id'],str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',data['id']) or data['id']=='open_play':
        raise ValueError('Invalid scenario name')
    if type(data['version']) is not int or data['version']<1:
        raise ValueError('Invalid scenario version')
    for key in ('title','description'):
        if not isinstance(data[key],dict) or set(data[key])!={'en','cs','de'} or any(not isinstance(s,str) or not s.strip() or len(s)>400 for s in data[key].values()):
            raise ValueError('Scenario copy requires en, cs and de')
    initial=data['initial']
    if not isinstance(initial,dict) or set(initial)!={'owner','ball','players'}:
        raise ValueError('Invalid initial state')
    owner=player_index(initial['owner']);ball=initial['ball']
    if not isinstance(ball,list) or len(ball)!=2 or not finite(ball[0],0,105) or not finite(ball[1],0,68):
        raise ValueError('Initial ball outside pitch')
    roster=initial['players']
    if not isinstance(roster,list) or len(roster)!=22:
        raise ValueError('A scenario needs 22 players')
    ids=set()
    for p in roster:
        if not isinstance(p,dict) or set(p)!={'id','x','y'}:
            raise ValueError('Invalid player position')
        index=player_index(p['id'])
        if index in ids or not finite(p['x'],.5,104.5) or not finite(p['y'],.5,67.5):
            raise ValueError('Duplicate player or position outside pitch')
        ids.add(index)
        if index==owner and math.dist(ball,(p['x'],p['y']))>1.8:
            raise ValueError('Initial owner cannot reach ball')
    ranges={'chasers':(1,4),'closing_gap_m':(0,3),'defending_shift_m':(-15,15),
            'tackle_rate':(.1,3),'forward_weight':(0,1),'decision_scale':(.4,2),'closing_mps':(2.7,6.2)}
    policy=data['policy']
    if not isinstance(policy,dict) or set(policy)!=set(ranges) or any(not finite(policy[k],*v) for k,v in ranges.items()) or type(policy['chasers']) is not int:
        raise ValueError('Invalid tactical policy')
    if not isinstance(data['sequence'],list) or len(data['sequence'])>20:
        raise ValueError('Invalid intent sequence')
    for step in data['sequence']:
        if not isinstance(step,dict) or step.get('action') not in ('pass','shot'):
            raise ValueError('Invalid intent')
        fields={'actor','action','after_control_s'}|({'receiver'} if step['action']=='pass' else set())
        if set(step)!=fields or not finite(step['after_control_s'],.4,5):
            raise ValueError('Invalid intent fields')
        actor=player_index(step['actor'])
        if step['action']=='pass':
            receiver=player_index(step['receiver'])
            if receiver==actor or receiver//11!=actor//11:
                raise ValueError('Intent must pass to a teammate')
    if not isinstance(data['expectations'],list) or len(data['expectations'])>20:
        raise ValueError('Invalid expectations')
    seen=set()
    for e in data['expectations']:
        required={'id','kind','team','by_s','label'}
        if not isinstance(e,dict) or not required<=set(e) or set(e)-required-{'actor','after','minimum_count'}:
            raise ValueError('Invalid expectation fields')
        if not isinstance(e['id'],str) or not e['id'] or e['id'] in seen or e['kind'] not in ('pass_started','pass_completed','shot','tackle','possession_change','pressure','interception'):
            raise ValueError('Invalid expectation identity or kind')
        if type(e['team']) is not int or e['team'] not in (0,1) or not finite(e['by_s'],.05,120):
            raise ValueError('Invalid expectation team or time')
        if 'after' in e and e['after'] not in seen:raise ValueError('Expectation dependency must precede it')
        if 'actor' in e:player_index(e['actor'])
        if 'minimum_count' in e and (e['kind']!='pressure' or type(e['minimum_count']) is not int or not 1<=e['minimum_count']<=11):
            raise ValueError('Invalid pressure expectation')
        if not isinstance(e['label'],dict) or set(e['label'])!={'en','cs','de'} or any(not isinstance(x,str) or not x or len(x)>200 for x in e['label'].values()):
            raise ValueError('Invalid expectation label')
        seen.add(e['id'])
    return deepcopy(data)


def load_catalog(directory):
    result={'open_play':BASE}
    for file in sorted(Path(directory).glob('*.json')):
        data=validate_profile(json.loads(file.read_text(encoding='utf-8')))
        if data['id'] in result:raise ValueError('Duplicate scenario id')
        data['sha256']=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        result[data['id']]=data
    return result


_CATALOG=load_catalog(Path(__file__).with_name('scenarios'))


def profile(scenario):
    if not isinstance(scenario,str) or scenario not in _CATALOG:raise ValueError('Unknown match scenario.')
    return deepcopy(_CATALOG[scenario])


def catalogue():
    return [{k:deepcopy(p[k]) for k in ('id','version','title','description','expectations')}
            for p in _CATALOG.values()]


class ScenarioDirector:
    def __init__(self, definition):
        self.definition=definition;self.policy=definition.get('policy',POLICY)
        self.sequence=definition.get('sequence',[]);self.step=0;self.cancelled=False

    def initialize(self, match):
        if 'initial' not in self.definition:return
        initial=self.definition['initial']
        for item in initial['players']:
            p=match.players[player_index(item['id'])];p.x,p.y=item['x'],item['y']
        match.owner=player_index(initial['owner'])
        match.ball=initial['ball'][:]
        match.possession_team=match.last_touch_team=match.players[match.owner].team

    def directing(self,match):
        return bool(self.sequence) and not self.cancelled and self.step<len(self.sequence) and match.clock<15 and not match.restart

    def targets(self,match,targets):
        if not self.directing(match):return targets
                                                                             
                                                                                 
        side=player_index(self.sequence[0]['actor'])//11
        for item in self.definition['initial']['players']:
            i=player_index(item['id']);p=match.players[i]
            if p.team==side:targets[i]=(item['x'],item['y'])
            elif p.number!=1:targets[i]=(match.world_x(8,p.team),item['y'])
        if match.flight and 'receiver' in match.flight:targets[match.flight['receiver']]=match.flight['target']
        return targets

    def act(self,match):
        if not self.directing(match):return False
        step=self.sequence[self.step]
        if match.owner!=player_index(step['actor']):
            self.cancelled=True;return False
        if match.control_time<step['after_control_s']:return True
        if step['action']=='pass':
            receiver=player_index(step['receiver'])
                                                                            
            if receiver not in [i for _,i in match.pass_options()]:
                self.cancelled=True;return False
            match.start_pass(receiver)
        elif not match.start_shot():
            self.cancelled=True;return False
        self.step+=1
        return True


class ScenarioExpectations:
                                                                                   
    def __init__(self,definition):
        self.definition=definition;self.matches={};self.last_id=0

    def consume(self,events):
        for e in events:
            if e['id']<=self.last_id:continue
            for test in self.definition.get('expectations',[]):
                if test['id'] in self.matches or e['time']>test['by_s']:continue
                prior=self.matches.get(test.get('after'))
                if 'after' in test and (not prior or prior['event_id']>=e['id']):continue
                if e['kind']!=test['kind'] or e['team']!=test['team']:continue
                if 'actor' in test and (not e['actors'] or f"{e['actors'][0]['team']}:{e['actors'][0]['number']}"!=test['actor']):continue
                if 'minimum_count' in test and e['details']['counts'][test['team']]<test['minimum_count']:continue
                self.matches[test['id']]={'event_id':e['id'],'time':e['time']}
            self.last_id=e['id']

    def snapshot(self,clock):
        tests=[dict(test,status='passed' if test['id'] in self.matches else 'failed' if clock>=test['by_s'] else 'pending',
                    evidence=self.matches.get(test['id'])) for test in self.definition.get('expectations',[])]
        status='failed' if any(t['status']=='failed' for t in tests) else 'pending' if any(t['status']=='pending' for t in tests) else 'passed' if tests else 'not_applicable'
        return {'id':self.definition['id'],'version':self.definition['version'],
                'title':deepcopy(self.definition['title']),'description':deepcopy(self.definition['description']),
                'status':status,'expectations':tests}
