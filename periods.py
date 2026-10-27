                                                                

                                                                            
                                                                             
                                                                            
   

from global_localization import locale_map, translate_tree, translate_text
from copy import deepcopy
import hashlib
import json
from locales import team_name


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
                                    separators=(',', ':'),allow_nan=False).encode()).hexdigest()


def conclusion(window, team):
    a,b=window['current'],window['previous']
    if not window['comparable']:
        return 'opening'
    if a['attacks'][team]>b['attacks'][team] and a['shots'][team]>b['shots'][team]:
        return 'closer' if a['close_shots'][team]>b['close_shots'][team] else 'attacking'
    if a['attacks'][team]<b['attacks'][team] and a['shots'][team]<b['shots'][team]:
        return 'quieter'
    if a['shots'][team]>b['shots'][team]:return 'more_shots'
    if a['attacks'][team]>b['attacks'][team]:return 'more_attacks'
    if a['attacks'][team]==b['attacks'][team] and a['shots'][team]==b['shots'][team]:return 'steady'
    return 'mixed'


def period_view(window, team, language='en', audience='fan', metrics=None):
    a,b=window['current'],window['previous']
    code=conclusion(window,team);name=team_name(team,language)
    headlines={
        'opening': locale_map({'de':'Daten für den Vergleich zweier Zeiträume werden gesammelt.','en':'Building evidence for a comparison of two periods.','cs':'Sbíráme podklady pro porovnání dvou úseků.'}),
        'closer': locale_map({'de':f'{name} griff häufiger an und kam dem Tor näher: Es gab mehr Schüsse aus kurzer Distanz.',
                   'en':f'{name} began attacking more often and came closer to goal: more shots came from close range.',
                   'cs':f'{name} útočí častěji a přiblížili se gólu: přibylo střel zblízka.'}),
        'attacking': locale_map({'de':f'{name} griff häufiger an und kam häufiger zum Abschluss.',
                      'en':f'{name} began attacking more often and reaching shots more often.',
                      'cs':f'{name} útočí častěji a častěji zakončují.'}),
        'quieter': locale_map({'de':f'{name} greift seltener an und schießt seltener aufs Tor.',
                    'en':f'{name} are entering attack and shooting less often.',
                    'cs':f'{name} méně často útočí i střílejí.'}),
        'more_shots': locale_map({'de':f'{name} kommt häufiger zum Abschluss, ohne mehr Angriffe zu beginnen.',
                       'en':f'{name} are reaching shots more often, without starting more attacks.',
                       'cs':f'{name} častěji zakončují, i když nových útoků nepřibylo.'}),
        'more_attacks': locale_map({'de':f'{name} greift häufiger an, aber die Zahl der Schüsse ist noch nicht gestiegen.',
                         'en':f'{name} are entering attack more often, but shots have not increased.',
                         'cs':f'{name} častěji útočí, ale střel zatím nepřibylo.'}),
        'steady': locale_map({'de':f'{name} hält die bisherige Häufigkeit von Angriffen und Schüssen.',
                   'en':f'{name} maintain the same frequency of attacks and shots.',
                   'cs':f'{name} udržují stejnou četnost útoků i střel.'}),
        'mixed': locale_map({'de':f'Bei {name} steigen Angriffe und Schüsse nicht gleichzeitig an.',
                  'en':f'{name} have no simultaneous rise in attacks and shots.',
                  'cs':f'U týmu {name} současně neroste počet útoků i střel.'})}
    labels=locale_map({'de':['Angriffe','Schüsse','Ballbesitz','Begonnene Pässe / min','Druck, s','Raumgewinn, m','Schüsse aus ≤18 m'],
            'en':['Attacks','Shots','Possession','Pass starts / min','Pressure, s','Forward progress, m','Shots from ≤18 m'],
            'cs':['Útoky','Střely','Držení míče','Přihrávky / min','Tlak, s','Postup, m','Střely z ≤18 m']})[language]
    definitions=[('attacks','attacks'),('shots','shots'),('possession','possession'),('tempo','passes'),
                 ('pressure','pressure_seconds'),('progress','forward_m'),('shots','close_shots')]
    rows=[]
    for label,(preference,key) in zip(labels,definitions):
        if metrics is None or preference in metrics:
            rows.append({'key':key,'label':label,'previous':b[key][team] if window['comparable'] else None,
                         'current':a[key][team], 'delta':round(a[key][team]-b[key][team],1) if window['comparable'] else None,
                         'unit':'percentage_points' if key=='possession' else 'count' if key in ('attacks','shots','passes','close_shots') else 'seconds' if key=='pressure_seconds' else 'metres'})
    changes={
        'pressure': [round(a['pressure_seconds'][t]-b['pressure_seconds'][t],1) for t in (0,1)],
        'tempo': [a['passes'][t]-b['passes'][t] for t in (0,1)],
        'possession_pp': [a['possession'][t]-b['possession'][t] for t in (0,1)]}
                                                                                       
    old_balance=b['shots'][0]-b['shots'][1];new_balance=a['shots'][0]-a['shots'][1]
    changes['initiative_shift'] = (0 if new_balance>0 else 1) if window['comparable'] and old_balance*new_balance<0 else None
    evidence=sorted(set(a['evidence_ids']+b['evidence_ids']))
    return {'id':f"period-{a['end']:.2f}", 'team':team, 'audience':audience,
            'headline':headlines[code][language], 'conclusion':code, 'comparable':window['comparable'],
            'facts':deepcopy(window), 'fact_fingerprint':fingerprint(window),
            'rows':rows if audience=='analyst' else [],'changes':changes,
            'evidence_ids':evidence,'time':a['end'],
            'boundary':locale_map({'de':'Angriff: Ballbesitz mit einer Ballaktion im letzten Drittel. Nahschuss: ≤18 m. Beobachtungen, keine Torwahrscheinlichkeit.',
                        'en':'Attack: a possession with a ball action in the final third. Close shot: ≤18 m. Observations, not scoring probability.',
                        'cs':'Útok: držení s akcí v poslední třetině. Střela zblízka: ≤18 m. Pozorování, nikoli pravděpodobnost gólu.'})[language]}
