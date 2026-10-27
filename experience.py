                                                                              

from global_localization import locale_map, translate_tree, translate_text
from copy import deepcopy
from locales import story, translated_packet, event_display, team_name
from roster import named_metadata
from proof_lens import claim_map


def context_text(context, language):
    a,b=context['current'],context['previous']
    if not context['comparable']:
        return locale_map({'de':'Die Anfangsphase wird beobachtet. Ein Vergleich benötigt zwei vollständige benachbarte Zeiträume.',
                'en':'Observing the opening. Comparison needs two complete adjacent windows.',
                'cs':'Sledujeme začátek. Porovnání vyžaduje dva celé sousední úseky.'})[language]
    parts=[]
    for t in (0,1):
        name=team_name(t,language)
        parts.append(f"{name}: "+(locale_map({'de':'begonnene Pässe','en':'pass starts','cs':'zahájené přihrávky'})[language])+f" {b['passes'][t]} → {a['passes'][t]}, "+(locale_map({'de':'Schüsse','en':'shots','cs':'střely'})[language])+f" {b['shots'][t]} → {a['shots'][t]}.")
        if a['forward_m'][t]>b['forward_m'][t] and a['shots'][t]>b['shots'][t]:
            parts.append(locale_map({'de':f'{name} kam häufiger zum Abschluss; auch der gesamte Raumgewinn durch erfolgreiche Pässe nahm zu.',
                          'en':f'{name} reached shots more often; cumulative forward progress through completed passes also increased.',
                          'cs':f'{name} častěji zakončují; vzrostl i součet postupu přesnými přihrávkami.'})[language])
    parts.append(locale_map({'de':'Druck misst die Nähe der Gegner zum Ball; die taktische Ursache der Veränderungen ist nicht belegt.',
                  'en':'Pressure measures opponent proximity to the ball; the tactical cause of changes is not established.',
                  'cs':'Presink zde měří blízkost soupeřů k míči; taktická příčina změn není určena.'})[language])
    return ' '.join(parts)


def build_experience(session, audience, language, team, player, selected, metrics=None, scene_revision=''):
    insights=session.insights
    moments=list(insights.moments.values())
    moment=insights.moments.get(selected) if selected else None
    if moment is None and moments:
        goals=[m for m in moments if m.kind=='goal' and 0<=session.match.clock-m.time<=12]
        moment=max(goals,key=lambda m:m.time) if goals else max(moments[-16:],key=lambda m:(int(player is not None and player in m.actors)*2+int(team is not None and m.team==team),m.time))
    context=session.pipeline.context.window()
    result={'finished':session.match.finished,'selected_metrics':metrics,'audience':audience,'language':language,'context':context,
            'context_text':context_text(context,language),'selected':None,
            'focus':session.pipeline.context.focus(player),
            'metadata':named_metadata(session.match.metadata()),'run_key':session.run_key,
            'stages':{'received':session.confirmed_count,'processed':session.pipeline.metrics.last_id,
                      'explained':len(moments),'audience':audience}}
    if result['focus']:
        for event in result['focus']['events']: event['display']=event_display(event,language)
    result['scene_revision']=''
    result['scene_unchanged']=False
    if moment:
        source=session.materials.latest[moment.id]
        version=f"{session.run_key}:{moment.id}:{moment.revision}:{audience}:{language}:{team}:{player}:{metrics}"
        result['scene_revision']=version
        if scene_revision==version:
            result['scene_unchanged']=True
            return result
        packet=deepcopy(source['packet']) if scene_revision else insights.moment_data(moment)
        contribution=insights.player_contribution(moment,player) if player else None
        local=translated_packet(packet,language,audience)
        local['materials']=session.content.render(local,team,player,contribution,language,audience)
        local['proof_lens']=claim_map(local,contribution,language)
        local['simple']=local['materials']['formats']['broadcast']['text']
        local['chain_metrics']={'passes':moment.facts.get('passes_in_attack',0),
                'elapsed_seconds':round(moment.time-insights.events[moment.evidence_ids[0]]['time'],1),
                'counterattack':moment.facts.get('counterattack',False)}
        result['selected']=local
    return result
