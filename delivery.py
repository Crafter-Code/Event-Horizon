                                                                              

                                                                           
                                                                             
   

from global_localization import locale_map, translate_tree, translate_text
from copy import deepcopy
from locales import event_display, team_name, story, personal
from periods import fingerprint, period_view
from content import english_personal

METRICS=('possession','passes','shots','pressure','attacks','tempo','progress','tackles','movement')
DEFAULT_METRICS=METRICS
EVENT_KINDS={'pass_started','pass_completed','pass_incomplete','interception','shot','goal','save','shot_blocked',
             'tackle','ball_recovered','possession_change','goal_kick','restart_taken'}


def metric_selection(value=None):
    if value is None:return list(DEFAULT_METRICS)
    if not isinstance(value,list) or any(not isinstance(v,str) or v not in METRICS for v in value) or len(set(value))!=len(value):
        raise ValueError('Unknown or repeated metric')
    return [key for key in METRICS if key in value]


class MaterialStream:
    def __init__(self):
        self.history=[]
        self.latest={}
        self.last_event=0
        self.period_count=0
        self.moment_versions={}

    def _append(self, record):
        record['schema_version']='eh-material-record-1'
        record['sequence']=len(self.history)+1
        record['fact_fingerprint']=fingerprint({'facts':record['facts'],'evidence_ids':record['evidence_ids']})
        self.history.append(record)
        self.latest[record['material_id']]=record

    def sync(self, pipeline):
        for event in pipeline.events[self.last_event:]:
            if event['kind'] not in EVENT_KINDS:continue
            details=event['details']
            facts={'kind':event['kind'],'attack_start':bool(pipeline.context.attacks and pipeline.context.attacks[-1]['event_id']==event['id']),'details':deepcopy(details),'ball':event['ball'][:],
                   'passes':pipeline.metrics.completed[:],'shots':pipeline.metrics.shots[:],
                   'score':pipeline.metrics.score[:], 'team':event['team']}
            evidence=[event['id']]
            if 'pass_start_id' in details:evidence.insert(0,details['pass_start_id'])
            self._append({'material_id':f"event-{event['id']}",'episode_id':f"action-{event['id']}",
                          'kind':'event','revision':1,'time':event['time'],'available_at':event['time'],
                          'team':event['team'],'actors':deepcopy(event['actors']),
                          'evidence_ids':evidence,'trigger_event_id':event['id'],
                          'facts':facts,'source_event':deepcopy(event)})
        self.last_event=len(pipeline.events)
        for moment in pipeline.insights.moments.values():
            if self.moment_versions.get(moment.id)==moment.revision:continue
            packet=pipeline.insights.moment_data(moment)
            self.moment_versions[moment.id]=moment.revision
            self._append({'material_id':moment.id,'episode_id':moment.id,'kind':'moment',
                          'revision':moment.revision,'time':moment.time,'available_at':round(pipeline.clock,2),
                          'team':moment.team,'actors':deepcopy(moment.actors),
                          'evidence_ids':moment.evidence_ids[:], 'trigger_event_id':moment.evidence_ids[-1],
                          'facts':deepcopy(moment.facts),'packet':packet})
        for window in pipeline.context.periods[self.period_count:]:
            end=window['current']['end']
            self._append({'material_id':f'period-{int(end)}','episode_id':f'period-{int(end)}','kind':'period',
                          'revision':1,'time':end,'available_at':end,'team':None,'actors':[],
                          'evidence_ids':sorted(set(window['current']['evidence_ids']+window['previous']['evidence_ids'])),
                          'trigger_event_id':None,'facts':deepcopy(window)})
        self.period_count=len(pipeline.context.periods)

    def ranked(self, team=None, player=None, at=None):
        if at is None:latest=self.latest
        else:
            latest={}
            for record in self.history:
                if record['available_at']<=at:latest[record['material_id']]=record
        recent=list(latest.values())[-100:]
        def rank(record):
            focused=player is not None and player in record['actors']
            return (int(focused)*2+int(team is not None and team==record['team']),record['available_at'],record['sequence'])
        return sorted(recent,key=rank,reverse=True)

    def _event_copy(self, record, language):
        event=record['source_event'];kind=event['kind'];facts=record['facts'];cs=language=='cs';de=language=='de'
        display=event_display(event,language);details=event['details']
        if kind=='pass_completed':
            progress=(details['end'][0]-details['origin'][0])*details['direction']
            if progress >= 1:
                significance=(f'Der Pass brachte den Ball {progress:.1f} m näher zum gegnerischen Tor.' if de else
                              f'Přihrávka posunula míč k soupeřově brance o {progress:.1f} m.' if cs else
                              f'The pass moved the ball {progress:.1f} m towards the opponent goal.')
            elif progress <= -1:
                significance=(f'Der Ball wurde {abs(progress):.1f} m zurückgespielt; die Mannschaft blieb in Ballbesitz.' if de else
                              f'Míč šel o {abs(progress):.1f} m zpět; tým udržel držení.' if cs else
                              f'The ball went {abs(progress):.1f} m backwards; the team kept possession.')
            else:
                significance=locale_map({'de':'Ein Querpass half der Mannschaft, den Ball zu halten.',
                              'en':'A lateral pass helped the team keep the ball.',
                              'cs':'Příčná přihrávka pomohla týmu udržet míč.'})[language]
        elif kind=='pass_incomplete':
            significance=locale_map({'de':'Der Pass wurde nicht angenommen; der Ball ist frei. Kein erfolgreicher Pass wird gezählt.',
                          'en':'The pass was not received; the ball is loose. No completed pass is counted.',
                          'cs':'Přihrávka nebyla přijata; míč je volný. Přesná přihrávka se nezapočítává.'})[language]
        elif kind=='pass_started':
            significance=locale_map({'de':'Der Ball ist auf dem Weg zu einem Mitspieler. Erst die Ballannahme bestätigt den Pass.',
                          'en':'The ball is travelling to a teammate. Completion is counted only after reception.',
                          'cs':'Míč míří ke spoluhráči. Přesnost se započte až po přijetí.'})[language]
        elif kind in ('tackle','interception','possession_change','ball_recovered','save','shot_blocked'):
            significance=locale_map({'de':'Die Mannschaft hat den Ball erobert. Die nächsten Aktionen zeigen, wie sich die Szene entwickelt.',
                          'en':'The team gained control of the ball. Subsequent actions will show how the episode develops.',
                          'cs':'Tým získal kontrolu nad míčem. Další akce ukážou vývoj epizody.'})[language]
        elif kind=='shot':
            significance=locale_map({'de':'Der Angriff führte zu einem Schuss. Der Ausgang steht noch aus.',
                          'en':'The attack reached a shot. The outcome is pending.',
                          'cs':'Útok dospěl ke střele. Čekáme na výsledek.'})[language]
        elif kind=='goal':
            significance=locale_map({'de':'Das Tor hat den Spielstand verändert. Schuss und Ausgang lassen sich anhand der Ereignisse prüfen.',
                          'en':'The goal changed the score. Its shot and outcome can be checked in the event sources.',
                          'cs':'Gól změnil skóre. Střelu a výsledek lze ověřit ve zdrojích.'})[language]
        else:
            significance=locale_map({'de':'Die Szene verändert die Spielsituation; ihre Quelle ist mit der Spielzeit verknüpft.',
                          'en':'The episode changes the state of play; its source is tied to match time.',
                          'cs':'Epizoda mění stav hry; zdroj je svázán s časem zápasu.'})[language]
        if facts.get('attack_start'):
            display['title']=locale_map({'de':'Angriffsfolge beginnt','en':'Attacking sequence begins','cs':'Začíná útočná série'})[language]+' · '+team_name(event['team'],language)
            significance += locale_map({'de':' Die erste Ballaktion dieses Ballbesitzes im letzten Drittel.',
                             'en':' The first ball action of this possession in the final third.',
                             'cs':' První akce s míčem v poslední třetině při tomto držení.'})[language]
        return display['title'],display['text'],significance

    def render(self, record, audience='fan',language='en',team=None,player=None,metrics=None):
        selection=metric_selection(metrics)
        result={key:deepcopy(record[key]) for key in ('schema_version','sequence','material_id','episode_id','kind','revision','time','available_at','team','actors','evidence_ids','trigger_event_id','facts','fact_fingerprint')}
        result.update(audience=audience,language=language,metrics=[],selected_metrics=selection)
        if record['kind']=='period':
            sides=[team] if team is not None else [0,1]
            periods=[period_view(record['facts'],side,language,audience,selection) for side in sides]
            perspectives=[]
            for side in sides:
                views={role:period_view(record['facts'],side,language,role,selection)
                       for role in ('fan','analyst')}
                perspectives.append({'team':side,'fact_fingerprint':record['fact_fingerprint'],
                                     'evidence_ids':record['evidence_ids'][:],
                                     'fan':{'headline':views['fan']['headline'],
                                            'conclusion':views['fan']['conclusion']},
                                     'analyst':{'headline':views['analyst']['headline'],
                                                'conclusion':views['analyst']['conclusion'],
                                                'rows':views['analyst']['rows'],
                                                'boundary':views['analyst']['boundary']}})
            result.update(event=locale_map({'de':'Wie diese Minute das Spiel verändert hat','en':'How the minute changed the game','cs':'Jak minuta změnila hru'})[language],
                          significance=' '.join(p['headline'] for p in periods),periods=periods,
                          perspectives=perspectives)
            result['metrics']=[{'team':p['team'],**row} for p in periods for row in p['rows']]
        elif record['kind']=='moment':
            packet=record['packet']
            interpretation=packet.get('interpretation')
            result['ai_interpretation']=deepcopy(interpretation) if interpretation and interpretation.get('language','en')==language else None
            result['interpretation_label']=locale_map({'de':'KI-Interpretation','en':'AI interpretation','cs':'Interpretace AI'})[language]
            localized=story(packet,language,audience)
            contribution=None
            if player:
                keys={'passes_made':0,'passes_received':0,'shots':0,'saves':0,'regains':0};ids=[]
                for event in packet['evidence']:
                    actors=event['actors'];kind=event['kind']
                    if player not in actors:continue
                    ids.append(event['id'])
                    keys['passes_made']+=kind=='pass_completed' and actors[0]==player
                    keys['passes_received']+=kind=='pass_completed' and actors[-1]==player
                    keys['shots']+=kind=='shot' and actors[0]==player
                    keys['saves']+=kind=='save' and actors[-1]==player
                    keys['regains']+=kind in ('tackle','interception','ball_recovered') and actors[-1]==player
                contribution={'counts':keys,'evidence_ids':ids}
            _,personal_text,_=english_personal(packet,team,player,contribution) if language=='en' else personal(packet,team,player,contribution,language)
            result.update(event=localized['title'],significance=localized['why'],
                          explanation=localized['what'],change=localized['change'],personal=personal_text)
            if audience=='analyst':
                labels=locale_map({'de':['Erfolgreiche Pässe im Angriff','Schüsse im Zeitraum'],
                        'en':['Completed passes in attack','Shots in interval'],
                        'cs':['Přesné přihrávky v útoku','Střely v úseku']})[language]
                if 'passes' in selection and 'passes_in_attack' in packet['facts']:
                    result['metrics'].append({'key':'passes','label':labels[0],'value':packet['facts']['passes_in_attack'],'unit':'count'})
                if 'shots' in selection:
                    result['metrics'].append({'key':'shots','label':labels[1],'value':packet['facts']['window']['shots'],'unit':'count'})

        else:
            title,text,why=self._event_copy(record,language)
            result.update(event=title,explanation=text,significance=why)
            if audience=='analyst':
                labels=locale_map({'de':['Erfolgreiche Pässe','Schüsse','Spielstand'],'en':['Completed passes','Shots','Score'],'cs':['Přesné přihrávky','Střely','Skóre']})[language]
                for key,label in zip(('passes','shots','score'),labels):
                    if key in selection:result['metrics'].append({'key':key,'label':label,'value':record['facts'][key],'unit':'count'})
        result['evidence']={'event_ids':record['evidence_ids'][:], 'lookup':'/event?id={event_id}&run_key={run_key}'}
        return result


def overlay(record, match_id, run_key, audience='fan', language='en', team=None, player=None,metrics=None):
    card=record
    duration=12 if card['kind'] in ('moment','period') else 7
    variant=fingerprint({'audience':audience,'language':language,'team':team,'player':player,'metrics':metric_selection(metrics)})[:12]
    return {'schema_version':'eh-overlay-1','overlay_id':f"{run_key}:{card['material_id']}:{variant}",
            'match_id':match_id,'run_key':run_key,'episode_id':card['episode_id'],
            'material_id':card['material_id'],'revision':card['revision'],
            'episode_time':card['time'],'show_at':card['available_at'],
            'remove_at':round(min(5400,card['available_at']+duration),2),
            'timebase':{'kind':'match_clock','unit':'seconds','origin':0},'layer':'narrative',
            'text':{'event':card['event'],'significance':card['significance'],
                    'evidence':' · '.join('#'+str(n) for n in card['evidence_ids'])},
            'metrics':deepcopy(card['metrics']),'facts':deepcopy(card['facts']),
            'fact_fingerprint':card['fact_fingerprint'],'source_event_ids':card['evidence_ids'][:]}
