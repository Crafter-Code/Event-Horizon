                                                                                 

from global_localization import locale_map, translate_tree, translate_text
from copy import deepcopy
from locales import translated_packet, team_name
from roster import player_name
from pass_quality import assess
from match_arc import build_arc
import hashlib
import json


class MatchReport:
    def __init__(self):
        self.cache={};self.finalized={}

    def build(self,pipeline,start,end,complete,player,language,audience='analyst',team=None):
        events=[e for e in pipeline.events if start<=e['time']<=end and (start==0 or e['time']>start)]
        attempts=[0,0];passes=[0,0];shots=[0,0];goals=[0,0];tackles=[0,0]
        players={f'{t}:{n}':dict(attempts=0,passes=0,shots=0,goals=0,tackles=0) for t in (0,1) for n in range(1,12)}
        longest=None;pass_actions=[]
        for e in events:
            bucket={'pass_started':attempts,'pass_completed':passes,'shot':shots,'goal':goals,'tackle':tackles}.get(e['kind'])
            key={'pass_started':'attempts','pass_completed':'passes','shot':'shots','goal':'goals','tackle':'tackles'}.get(e['kind'])
            if bucket is not None:
                bucket[e['team']]+=1
                if e['actors']:
                    actor=e['actors'][-1 if e['kind']=='tackle' else 0];players[f"{actor['team']}:{actor['number']}"][key]+=1
            if e['kind']=='pass_completed':
                origin=e['details']['origin'];endpoint=e['details']['end']
                source=pipeline.events[e['details']['pass_start_id']-1]
                opponents=[(p['x'],p['y']) for p in source['frame'] if p['team']!=e['team']]
                quality=assess(origin,endpoint,opponents,e['details']['direction'])
                action={'event_id':e['id'],'time':e['time'],'sender':e['actors'][0],**quality,'success':True,
                        'source_ids':[source['id'],e['id']],'source':'event geometry; separate from pixel estimates'}
                if longest is None or quality['distance_m']>longest['distance_m']:longest=action
                pass_actions.append(action)
        for p in players.values():p['accuracy_pct']=round(p['passes']/p['attempts']*100,1) if p['attempts'] else None
        moments=[m for m in pipeline.insights.moments.values() if start<m.time<=end or start==0 and m.time==0]
        ranked=sorted(moments,key=lambda m:(2*int(player is not None and player in m.actors)+int(team is not None and m.team==team),m.kind=='goal',m.facts.get('counterattack',False),m.kind!='trend',m.time),reverse=True)[:6]
        goals_in_period=[m for m in moments if m.kind=='goal']
        if goals_in_period and goals_in_period[-1] not in ranked:
            ranked=(ranked[:5]+[goals_in_period[-1]])
        selected=sorted(ranked,key=lambda m:m.time)
        episodes=[]
        for m in selected:
            packet=pipeline.insights.moment_data(m);local=translated_packet(packet,language,audience)
            episodes.append({'id':m.id,'time':m.time,'kind':m.kind,'title':local['title'],
                             'text':local['what'],'significance':local['why'],'evidence_ids':m.evidence_ids[:],
                             'comparison':deepcopy(m.facts.get('comparison')),'source':'observed facts'})
        labels=locale_map({'de':('Endstand','Live-Überblick','Erfolgreiche Pässe','Schüsse','Tore'),
                'en':('Final','Live overview','Completed passes','shots','goals'),
                'cs':('Souhrn','Průběžný přehled','Přesné přihrávky','střely','góly')})[language]
        lines=[f"{team_name(t,language)}: {labels[2]} {passes[t]}/{attempts[t]}, {labels[3]} {shots[t]}, {labels[4]} {goals[t]}." for t in (0,1)]
        focus=None
        if player:
            key=f"{player['team']}:{player['number']}";stats=players[key]
            involved=[m for m in moments if player in m.actors]
            focus={'player':{**player,'name':player_name(player['team'],player['number'])},'statistics':stats,
                   'episode_ids':[m.id for m in involved],
                   'evidence_ids':[e['id'] for e in events if player in e['actors']],
                   'team_share_shots_pct':round(stats['shots']/shots[player['team']]*100,1) if shots[player['team']] else None,
                   'team_passes':passes[player['team']],
                   'period_comparison':self.player_periods(events,player,end)}
        chronology=[]
        if start==0 and end>=5400:
            for a,b in ((0,2700),(2700,5400)):
                items=[e for e in events if (a==0 or e['time']>a) and e['time']<=b]
                chronology.append({'start':a,'end':b,'goals':[sum(e['kind']=='goal' and e['team']==t for e in items) for t in (0,1)],
                    'shots':[sum(e['kind']=='shot' and e['team']==t for e in items) for t in (0,1)],
                    'passes':[sum(e['kind']=='pass_completed' and e['team']==t for e in items) for t in (0,1)],
                    'evidence_ids':[e['id'] for e in items if e['kind'] in ('shot','goal')]})
        facts={'start':start,'end':end,'complete':complete,'attempts':attempts,'passes':passes,'shots':shots,'goals':goals,'tackles':tackles,'players':players,'periods':chronology}
        fingerprint=hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest()
        max_shots=max((p['shots'] for p in players.values()),default=0)
        leaders=[{'name':player_name(*map(int,key.split(':'))),'player_id':key,'shots':p['shots'],
                  'evidence_ids':[e['id'] for e in events if e['kind']=='shot' and e['actors'] and f"{e['actors'][0]['team']}:{e['actors'][0]['number']}"==key]}
                 for key,p in players.items() if max_shots>0 and p['shots']==max_shots]
        text=' '.join(lines)
        if audience=='fan':
            text=locale_map({'de':f'Tore in diesem Zeitraum: {goals[0]}:{goals[1]}. Die wichtigsten Szenen folgen unten.',
                  'en':f'Goals in this period: {goals[0]}:{goals[1]}. Key episodes follow below.',
                  'cs':f'Góly v tomto úseku: {goals[0]}:{goals[1]}. Klíčové epizody jsou níže.'})[language]
            if team is not None:
                name=team_name(team,language)
                text=locale_map({'de':f'{name}: {goals[team]} Tore und {shots[team]} Schüsse in diesem Zeitraum. Tore nach Mannschaft: {goals[0]}:{goals[1]}.',
                      'en':f'{name}: {goals[team]} goals and {shots[team]} shots in this period. Goals by team: {goals[0]}:{goals[1]}.',
                      'cs':f'{name}: góly — {goals[team]}, střely — {shots[team]}. Góly týmů v tomto úseku: {goals[0]}:{goals[1]}.'})[language]
        if audience=='player' and focus:
            p=focus['statistics'];name=focus['player']['name']
            text=locale_map({'de':f"{name}: Pässe {p['passes']}/{p['attempts']}, Schüsse {p['shots']}, Balleroberungen {p['tackles']}. Tore nach Mannschaft: {goals[0]}:{goals[1]}.",
                  'en':f"{name}: passes {p['passes']}/{p['attempts']}, shots {p['shots']}, tackles {p['tackles']}. Goals by team: {goals[0]}:{goals[1]}.",
                  'cs':f"{name}: přihrávky {p['passes']}/{p['attempts']}, střely {p['shots']}, odebrání míče {p['tackles']}. Góly týmů: {goals[0]}:{goals[1]}."})[language]
        return {'id':f'report-{start}-{end}','title':labels[0] if complete else labels[1],
                'preferences':{'team':team,'player':deepcopy(player),'audience':audience,'language':language},
                'chronology':chronology,'generated_from':'calculated_facts','text':text,'facts':facts,'fact_fingerprint':fingerprint,'episodes':episodes,'player':focus,
                'achievement':longest,'shot_leaders':leaders,'pass_actions':pass_actions[-5:],'interpretation':None,
                'story_arc':build_arc(pipeline.events,start,end,complete,language),
                'interpretation_label':locale_map({'de':'KI-Interpretation','en':'AI interpretation','cs':'Interpretace AI'})[language]}

    @staticmethod
    def player_periods(events,player,end):
        result=[]
        for a,b in ((max(0,end-120),max(0,end-60)),(max(0,end-60),end)):
            relevant=[e for e in events if a<e['time']<=b and e['actors'] and e['actors'][-1 if e['kind']=='tackle' else 0]==player]
            result.append({'start':a,'end':b,'passes':sum(e['kind']=='pass_completed' for e in relevant),
                           'shots':sum(e['kind']=='shot' for e in relevant),'tackles':sum(e['kind']=='tackle' for e in relevant),
                           'evidence_ids':[e['id'] for e in relevant]})
        return {'comparable':end>=120,'previous':result[0],'current':result[1]}

    def snapshot(self,pipeline,player=None,language='en',audience='analyst',team=None):
                                                                                 
        second=int(pipeline.clock);key=(second,pipeline.insights.revision,language,str(player),audience,team)
        if key not in self.cache:
            self.cache={key:self.build(pipeline,0,pipeline.clock,False,player,language,audience,team)}
        result={'live':deepcopy(self.cache[key]),'halves':[],'full_time':None}
        for start,end in ((0,2700),(2700,5400)):
            if pipeline.clock<end:continue
            frozen_key=(start,end,language,str(player),audience,team)
            if frozen_key not in self.finalized:
                self.finalized[frozen_key]=self.build(pipeline,start,end,True,player,language,audience,team)
            result['halves'].append(deepcopy(self.finalized[frozen_key]))
        if pipeline.clock>=5400:
            final_key=('full',language,str(player),audience,team)
            if final_key not in self.finalized:self.finalized[final_key]=self.build(pipeline,0,5400,True,player,language,audience,team)
            result['full_time']=deepcopy(self.finalized[final_key])
        return result
