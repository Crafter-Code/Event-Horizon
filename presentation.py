                                                                            

from global_localization import locale_map, translate_tree, translate_text
from copy import deepcopy
from delivery import metric_selection, overlay
from periods import fingerprint, period_view
from locales import team_name
from rhythm_lens import build as rhythm_lens


def statistics(session, language, selected):
    state=session.confirmed_frame;context=session.pipeline.context
    window=context.window()['current']
    labels=locale_map({'de':['Ballbesitz','Pässe','Schüsse','Druck · 5 m','Angriffe','Begonnene Pässe / min','Raumgewinn, m','Balleroberungen'],
            'en':['Possession','Passes','Shots','Pressure · 5 m','Attacks','Pass starts / min','Forward progress, m','Tackles'],
            'cs':['Držení','Přihrávky','Střely','Presink · 5 m','Útoky','Přihrávky / min','Postup, m','Odebrání míče']})[language]
    keys=['possession','passes','shots','pressure','attacks','tempo','progress','tackles']
    values=[state['possession'],[f"{state['passes'][t]}/{state['attempts'][t]}" for t in (0,1)],state['shots'],state['pressure'],
            [sum(a['team']==t for a in context.attacks) for t in (0,1)],window['passes'],window['forward_m'],
            [sum(p['tackles'] for key,p in context.players.items() if key.startswith(f'{t}:')) for t in (0,1)]]
    return [{'key':key,'label':label,'value':deepcopy(value),'unit':'percent' if key=='possession' else 'metres' if key=='progress' else 'count'}
            for key,label,value in zip(keys,labels,values) if key in selected]


def preference_key(audience,language,team,player,metrics):
    return fingerprint({'audience':audience,'language':language,'team':team,'player':player,'metrics':metrics})[:16]


def package(session,audience='fan',language='en',team=None,player=None,metrics=None,after=0,limit=100,at=None,channel='viewer'):
    selected=metric_selection(metrics)
    stream=session.materials
    clock=session.confirmed_frame['clock']
    media_time=clock if at is None else at
    match_id=session.match.match_id;run_key=session.run_key
    viewer=preference_key(audience,language,team,player,selected)+':'+channel
    kwargs=dict(audience=audience,language=language,team=team,player=player,metrics=selected)
    def wire(record):
        card=stream.render(record,**kwargs)
        card.update(match_id=match_id,run_key=run_key)
        return card
    known=[record for record in stream.history if at is None or record['available_at']<=media_time]
    records=[record for record in known if record['sequence']>after][:limit]
                                                                                
    candidates=[record for record in stream.history if media_time-12<=record['available_at']<=media_time]
    cues=[]
    for record in candidates:
        if record['available_at']>=5400:continue
        card=wire(record);cue=overlay(card,match_id,run_key,**kwargs)
        cue['priority']=(100 if record['kind']=='moment' and record['facts'].get('outcome')=='goal' else
                         (4 if player and player in record['actors'] else 0)+
                         (2 if team is not None and record['team']==team else 0)+
                         (1 if record['kind'] in ('moment','period') else 0))
        cue['replacement_policy']='highest_priority_then_latest_in_layer'
        if cue['show_at']<=media_time<cue['remove_at']:cues.append(cue)
    if channel=='broadcast':
        active=session.desk.snapshot(session.insights,language)['active']
        cues=[]
        if active:
            record=stream.latest.get(active['id'])
            selections=[entry for entry in session.desk.history if entry['action']=='select' and entry['moment_id']==active['id'] and entry['language']==language]
            if record and selections and selections[-1]['time']<5400:
                cue=overlay(wire(record),match_id,run_key,**kwargs)
                cue.update(show_at=selections[-1]['time'],remove_at=min(5400,selections[-1]['time']+12),priority=100,
                           editorial_receipt=active['editorial']['receipt'])
                cue['text']['significance']=active['editorial']['copy']
                if cue['show_at']<=media_time<cue['remove_at']:cues.append(cue)
    rows=statistics(session,language,selected) if at is None else []
    if rows and at is None and clock<5400:
        cues.append({'schema_version':'eh-overlay-1','overlay_id':f'{run_key}:statistics:{viewer}',
            'match_id':match_id,'run_key':run_key,'episode_id':f'action-{session.confirmed_count}','material_id':'statistics-live',
            'revision':int(round(clock/.05)),'episode_time':clock,'show_at':clock,'remove_at':min(5400,clock+2),
            'timebase':{'kind':'match_clock','unit':'seconds','origin':0},'layer':'statistics','priority':0,
            'replacement_policy':'highest_priority_then_latest_in_layer',
            'text':{'event':'','significance':'','evidence':''},'metrics':rows,
            'facts':{'clock':clock,'metrics':[{k:r[k] for k in ('key','value','unit')} for r in rows]},
            'fact_fingerprint':fingerprint({'clock':clock,'metrics':[{k:r[k] for k in ('key','value','unit')} for r in rows]}),
            'source_event_ids':[session.confirmed_count]})
    ranked=stream.ranked(team,player) if at is None else stream.ranked(team,player,media_time)
    cards=[wire(record) for record in ranked[:6]]
    recent_period=next((r for r in reversed(known) if r['kind']=='period'),None)
    period_record=wire(recent_period) if recent_period else None
    narrative=sorted((c for c in cues if c['layer']=='narrative'),key=lambda c:(c['priority'],c['show_at'],c['revision']),reverse=True)
    active=narrative[0] if narrative else None
    active_source=stream.latest.get(active['material_id']) if active else None
    focus_moments=[]
    if player and at is None:
        focus_moments=[{'material_id':r['material_id'],'time':r['time'],
                        'title':wire(r)['event'],'evidence_ids':r['evidence_ids'][:]}
                       for r in reversed(list(stream.latest.values())) if r['kind']=='moment' and player in r['actors']][:12]
    live_windows=session.pipeline.context.window()
    sides=[team] if team is not None else [0,1]
    live_changes=[period_view(live_windows,t,language,audience,selected) for t in sides] if at is None else []
    return {'language':language,'audience':audience,'schema_version':'eh-material-feed-1','match_id':match_id,'run_key':run_key,'viewer_key':viewer,
            'rhythm':rhythm_lens(session.pipeline.context.periods[-1] if session.pipeline.context.periods else live_windows) if at is None else None,
            'match_clock':clock,'playback_clock':media_time,'timebase':{'kind':'match_clock','unit':'seconds','origin':0},
            'cursor':records[-1]['sequence'] if records else after,'latest_cursor':known[-1]['sequence'] if known else 0,
            'has_more':bool(records and records[-1]['sequence']<known[-1]['sequence']),
            'records':[wire(r) for r in records],'cards':cards,'period':period_record,
            'live_changes':live_changes,'focus_moments':focus_moments,
            'overlays':cues,'active_overlay':active,'statistics':rows,'selected_metrics':selected,
            'disabled_layers':['statistics'] if not rows else [],
            'delivery':session.timing.offer(active_source) if at is None else None,
            'latency':session.timing.summary(),'focus':session.pipeline.context.focus_summary(player) if at is None else None,'channel':channel,
            'definitions':{'attack':'One uninterrupted possession with a recorded ball action in the opponent final third.',
                           'tempo':'Pass starts per 60 seconds.', 'close_shot':'A shot originating at most 18 metres from goal.',
                           'initiative':'A change in the sign of the shot-count balance between adjacent windows.',
                           'pressure':'In-play seconds with an opponent within 5 metres of the ball.',
                           'movement':'Distance integrated from in-play model coordinates; not a real tracking feed.'}}
