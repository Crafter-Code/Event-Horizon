                                                                                        

from global_localization import locale_map, translate_tree, translate_text
from copy import deepcopy
from math import dist
from roster import player_name

LANGUAGES=('en','cs','de','fr','it','es','pt')
TEAMS=locale_map({'de':['Blau','Rot'],'en':['Blue','Red'],'cs':['Modří','Červení']})
KIND_KEYS=['kickoff','pass_started','pass_completed','pass_incomplete','interception','shot','goal','save','shot_blocked','goal_kick','corner','throw_in','restart_taken','tackle','ball_recovered','second_half','full_time','pressure','possession_change']
KINDS=locale_map({
 'de':['Anstoß','Pass begonnen','Erfolgreicher Pass','Fehlpass','Abgefangener Pass','Schuss','Tor','Parade','Geblockter Schuss','Abstoß','Eckstoß','Einwurf','Spielfortsetzung','Balleroberung','Freien Ball gewonnen','Zweite Halbzeit','Spielende','Druck','Ballbesitzwechsel'],
 'en':['Kick-off','Pass started','Completed pass','Incomplete pass','Interception','Shot','Goal','Save','Blocked shot','Goal kick','Corner','Throw-in','Restart','Tackle','Ball recovery','Second half','Full time','Pressure','Possession change'],
 'cs':['Výkop','Zahájení přihrávky','Přesná přihrávka','Nepřesná přihrávka','Zachycení přihrávky','Střela','Gól','Zákrok brankáře','Zablokovaná střela','Kop od branky','Roh','Aut','Obnovení hry','Odebrání míče','Získání míče','Druhý poločas','Konec zápasu','Presink','Změna držení míče']})


def tr(language,de,en,cs):
    if language not in LANGUAGES:raise ValueError('Unsupported language')
    return locale_map({'en':en,'cs':cs,'de':de})[language]


def team_name(team,language):return TEAMS[language][team]


def identity(actor):
    return player_name(actor['team'],actor['number'])


def named(actor):return f"{identity(actor)} (#{actor['number']})"


def event_display(event,language):
    kind=event['kind'];d=event['details'];actors=event['actors'];team=team_name(event['team'],language)
    title=dict(zip(KIND_KEYS,KINDS[language])).get(kind,kind)+' · '+team
    a=named(actors[0]) if actors else team;b=named(actors[-1]) if actors else team
    if kind=='kickoff' and d.get('scenario_start'):
        title=tr(language,'Szenario beginnt','Scenario starts','Začátek scénáře')
        text=tr(language,f'{a} kontrolliert den Ball an der Startposition des Szenarios.',f'{a} controls the ball at the scenario’s starting position.',f'{a} má míč ve výchozí pozici scénáře.')
    elif kind=='pass_started':
        text=tr(language,f'{a} passt in Richtung {b}. Die Ballannahme steht noch aus.',f'{a} passes towards {b}. Reception is pending.',f'Přihrávka: {a} → {b}. Čekáme na přijetí míče.')
    elif kind=='pass_completed':
        if 'origin' not in d or 'end' not in d:
            return {'title':title,'text':tr(language,f'Erfolgreicher Pass: {a} → {b}.',f'Completed pass: {a} → {b}.',f'Přesná přihrávka: {a} → {b}.')}
        length=dist(d['origin'],d['end']);progress=(d['end'][0]-d['origin'][0])*d['direction']
        text=tr(language,f'{a} → {b}: erfolgreicher Pass über {length:.1f} m. Raumgewinn zum Tor: {progress:+.1f} m.',f'{a} → {b}: completed pass over {length:.1f} m. Progress towards goal: {progress:+.1f} m.',f'{a} → {b}: přesná přihrávka na {length:.1f} m. Postup k brance: {progress:+.1f} m.')
    elif kind=='pass_incomplete':text=tr(language,'Der vorgesehene Empfänger kontrollierte den Pass nicht; der Ball ist frei.','The intended receiver did not control the pass; the ball is loose.','Adresát přihrávku nezpracoval; míč je volný.')
    elif kind=='shot':
        length=d.get('distance_m');pressure=d.get('pressure_count')
        if length is None or pressure is None:
            return {'title':title,'text':tr(language,f'{a} schießt aufs Tor.',f'{a} takes a shot.',f'{a} střílí na branku.')}
        text=tr(language,f'{a} schießt aus {length:.1f} m. Gegner im Umkreis von 5 m: {pressure}.',f'{a} shoots from {length:.1f} m. Opponents within 5 m: {pressure}.',f'{a} střílí ze vzdálenosti {length:.1f} m. Soupeři do 5 m: {pressure}.')
    elif kind=='goal':
        score=':'.join(map(str,event['score']))
        text=tr(language,f'{a} trifft. Der Spielstand ist {score}.',f'{a} scores. The score is {score}.',f'{a} skóruje. Skóre je {score}.')
    elif kind in ('tackle','interception'):
        text=tr(language,f'{b} ' + ('erobert den Ball im Zweikampf.' if kind=='tackle' else 'fängt den Pass ab.'),f'{b} '+('wins the ball in a tackle.' if kind=='tackle' else 'intercepts the pass.'),f'{b} '+('odebírá soupeři míč.' if kind=='tackle' else 'zachycuje přihrávku.'))
    elif kind=='save':text=tr(language,f'{b} hält den Schuss und nimmt den Ball auf.',f'{b} saves the shot and takes possession.',f'{b} chytá střelu a získává míč.')
    elif kind=='shot_blocked':text=tr(language,f'{b} blockt den Schuss und gewinnt den Ball.',f'{b} blocks the shot and wins the ball.',f'{b} blokuje střelu a získává míč.')
    elif kind=='ball_recovered':text=tr(language,f'{b} erreicht den freien Ball zuerst.',f'{b} reaches the loose ball first.',f'{b} se jako první dostává k volnému míči.')
    elif kind=='pressure':
        counts=d['counts'];text=tr(language,f'Gegner im Umkreis von 5 m um den Ball: {counts[0]}:{counts[1]}.',f'Opponents within 5 m of the ball: {counts[0]}:{counts[1]}.',f'Soupeři do 5 m od míče: {counts[0]}:{counts[1]}.')
    elif kind=='possession_change':
        old=team_name(d['from_team'],language)
        text=tr(language,f'Ballbesitz: {old} → {team}.',f'Possession: {old} → {team}.',f'Držení míče: {old} → {team}.')
    else:
        texts={
         'kickoff':('Das Spiel beginnt mit dem Anstoß am Mittelpunkt.','Play starts from the centre spot.','Hra začíná rozehrávkou ze středu hřiště.'),
         'goal_kick':('Der Ball überquerte die Torauslinie; es gibt Abstoß.','The ball crossed the end line; a goal kick is awarded.','Míč přešel brankovou čáru; následuje kop od branky.'),
         'corner':('Die verteidigende Mannschaft berührte den Ball zuletzt; es gibt Eckstoß.','The defending team touched the ball last; a corner is awarded.','Míč naposledy tečoval bránící tým; následuje roh.'),
         'throw_in':('Der Ball überquerte die Seitenlinie; es gibt Einwurf.','The ball crossed the touchline; a throw-in is awarded.','Míč přešel postranní čáru; následuje aut.'),
         'restart_taken':('Der Ball ist wieder im Spiel.','The ball is back in play.','Míč je znovu ve hře.'),
         'second_half':('Die zweite Halbzeit beginnt; die Mannschaften haben die Seiten gewechselt.','The second half begins; the teams have changed ends.','Začíná druhý poločas; týmy si vyměnily strany.'),
         'full_time':('Das Spiel ist beendet; die Endstatistik ist verfügbar.','The match is over; final statistics are available.','Zápas skončil; jsou dostupné konečné statistiky.')}
        text=tr(language,*texts.get(kind,('Spielereignis.','Match event.','Událost zápasu.')))
    return {'title':title,'text':text}


def story(packet,language,audience='analyst'):
    if language in ('fr','it','es','pt'):
        from story_languages import native_story
        return native_story(packet,language,audience)
    if audience not in ('fan','analyst','player'):raise ValueError('Unsupported audience')
    f=packet['facts'];w=f['window'];fan=audience=='fan'
    score=':'.join(map(str,f.get('score',[0,0])))
    if packet['kind']=='trend':
        sub=f.get('context_change');a=f.get('comparison',{}).get('current');b=f.get('comparison',{}).get('previous')
        title=tr(language,'Veränderung des Drucks','Pressure change','Změna presinku') if sub=='pressure' else tr(language,'Veränderung des Rhythmus','Rhythm change','Změna tempa') if sub else tr(language,'Aktivität vor dem Tor','Activity in front of goal','Aktivita před brankou')
        if a and b:
            keys=['pressure_seconds'] if sub=='pressure' else ['passes','attacks','losses']
            labels={k:tr(language,*v) for k,v in {'pressure_seconds':('Druck, s','Pressure, s','Tlak, s'),'passes':('Begonnene Pässe','Pass starts','Zahájené přihrávky'),'attacks':('Angriffe','Attacks','Útoky'),'losses':('Ballverluste','Possession losses','Ztráty míče')}.items()}
            detail='; '.join(team_name(t,language)+': '+', '.join(f'{labels[k]} {b[k][t]} → {a[k][t]}' for k in keys) for t in (0,1))+'.'
            brief=tr(language,'Der Druck um den Ball hat sich verändert.','Pressure around the ball has changed.','Změnil se tlak v okolí míče.') if sub=='pressure' else tr(language,'Der Rhythmus von Pässen, Angriffen und Ballverlusten hat sich verändert.','The rhythm of passes, attacks and possession losses has changed.','Změnilo se tempo přihrávek, útoků a ztrát míče.')
        else:
            detail=tr(language,f"Schüsse: {w['previous_shots'][0]}:{w['previous_shots'][1]} → {w['shots'][0]}:{w['shots'][1]}.",f"Shots: {w['previous_shots'][0]}:{w['previous_shots'][1]} → {w['shots'][0]}:{w['shots'][1]}.",f"Střely: {w['previous_shots'][0]}:{w['previous_shots'][1]} → {w['shots'][0]}:{w['shots'][1]}.")
            brief=tr(language,'Die Aktivität vor dem Tor hat sich verändert.','Activity in front of goal has changed.','Změnila se aktivita před brankou.')
        why=tr(language,'Der Schluss beruht auf einem Vergleich benachbarter Spielabschnitte.','The conclusion comes from a comparison of adjacent periods of play.','Závěr vychází z porovnání sousedních úseků hry.')
        change=tr(language,'Die Ursache der Veränderung ist nicht belegt.','The cause of the change has not been established.','Příčina změny nebyla určena.')
        if not fan:change+=tr(language,f" Zeitraum {w['start']:.1f}–{w['end']:.1f} s.",f" Interval {w['start']:.1f}–{w['end']:.1f} s.",f" Úsek {w['start']:.1f}–{w['end']:.1f} s.")
        return {'title':title,'what':brief if fan else detail,'why':why,'change':change}
    shot=next((e for e in packet['evidence'] if e['kind']=='shot'),None)
    scorer=next((e for e in packet['evidence'] if e['kind']=='goal'),None)
    actor=(shot or scorer or packet['evidence'][0]).get('actors',[])
    name=identity(actor[0]) if actor else team_name(packet['team'],language)
    outcome=f.get('outcome');is_goal=outcome=='goal'
    title=tr(language,f'Tor · {name}',f'Goal · {name}',f'Gól · {name}') if is_goal else tr(language,f'Schuss · {name}',f'Shot · {name}',f'Střela · {name}')
    outcomes={
     'goal':('Der Ball ist im Tor.','The ball is in the net.','Míč je v síti.'),
     'save':('Der Torwart hielt den Schuss und nahm den Ball auf.','The goalkeeper saved the shot and took possession.','Brankář chytil střelu a získal míč.'),
     'shot_blocked':('Ein Verteidiger blockte den Schuss und gewann den Ball.','A defender blocked the shot and won the ball.','Obránce zablokoval střelu a získal míč.'),
     'goal_kick':('Der Ball ging ins Aus; es gab Abstoß.','The ball went out; a goal kick was awarded.','Míč přešel brankovou čáru; následoval kop od branky.'),
     'second_half':('Die Halbzeitpause unterbrach die Szene.','Half-time interrupted the episode.','Epizodu přerušil konec poločasu.'),
     'full_time':('Der Schlusspfiff unterbrach die Szene.','Full-time interrupted the episode.','Epizodu přerušil konec zápasu.')}
    outcome_text=tr(language,*outcomes.get(outcome,('Der Ausgang des Schusses steht noch aus.','The shot outcome is still pending.','Výsledek střely zatím není znám.')))
    what=(tr(language,f'{name} schoss aufs Tor.',f'{name} took a shot.',f'{name} vystřelil na branku.') if fan or not shot else event_display(shot,language)['text'])+' '+outcome_text
    passes=f.get('passes_in_attack',0)
    de_form='erfolgreichen Pass' if passes==1 else 'erfolgreiche Pässe'
    cs_form='přesná přihrávka' if passes==1 else 'přesné přihrávky' if passes in (2,3,4) else 'přesných přihrávek'
    en_form='pass' if passes==1 else 'passes'
    why=tr(language,f'Vor dem Schuss spielte die Mannschaft {passes} {de_form}.',f'The team completed {passes} {en_form} before the shot.',f'Před střelou: {passes} {cs_form}.')
    if f.get('counterattack') and shot:
        regain=next((e for e in packet['evidence'] if e['kind'] in ('interception','tackle')),None)
        if regain:
            elapsed=shot['time']-regain['time']
            why=tr(language,f'Nach dem Ballgewinn folgte {elapsed:.1f} s später ein Schuss.',f'The ball recovery was followed by a shot {elapsed:.1f} s later.',f'Po zisku míče následovala střela za {elapsed:.1f} s.')+('' if fan else ' '+why)
    change=tr(language,f'Der Spielstand ist {score}.',f'The score is {score}.',f'Skóre je {score}.')
    if not fan:
        change+=tr(language,f" Von {w['start']:.1f}–{w['end']:.1f} s: Schüsse {w['shots'][0]}:{w['shots'][1]}, Ballbesitz {w['possession'][0]}%:{w['possession'][1]}%.",f" During {w['start']:.1f}–{w['end']:.1f} s: shots {w['shots'][0]}:{w['shots'][1]}, possession {w['possession'][0]}%:{w['possession'][1]}%.",f" V úseku {w['start']:.1f}–{w['end']:.1f} s: střely {w['shots'][0]}:{w['shots'][1]}, držení míče {w['possession'][0]}%:{w['possession'][1]}%.")
        if w['end']>=120:
            change+=tr(language,f" Schüsse im vorherigen Zeitraum: {w['previous_shots'][0]}:{w['previous_shots'][1]}.",f" Shots in the previous period: {w['previous_shots'][0]}:{w['previous_shots'][1]}.",f" Střely v předchozím úseku: {w['previous_shots'][0]}:{w['previous_shots'][1]}.")
    return {'title':title,'what':what,'why':why,'change':change}


def caption(packet,language):
    if language in ('fr','it','es','pt'):
        from story_languages import native_story, COPY
        p=native_story(packet,language,'fan')
        return [p['title'], COPY[language]['passes'].format(count=packet['facts'].get('passes_in_attack',0))][:2]
    f=packet['facts']
    if packet['kind']=='trend':
        sub=f.get('context_change');a=f.get('comparison',{}).get('current');b=f.get('comparison',{}).get('previous')
        title=tr(language,'Veränderung des Drucks','Pressure change','Změna presinku') if sub=='pressure' else tr(language,'Veränderung des Rhythmus','Rhythm change','Změna tempa')
        if a and b:
            key='pressure_seconds' if sub=='pressure' else 'passes';label=tr(language,'Druck, s','Pressure, s','Tlak, s') if sub=='pressure' else tr(language,'Begonnene Pässe','Pass starts','Přihrávky')
            return [title,f"{label}: {b[key][0]}:{b[key][1]} → {a[key][0]}:{a[key][1]}"]
        w=f['window'];return [tr(language,'Aktivität vor dem Tor','Activity in front of goal','Aktivita před brankou'),tr(language,'Schüsse','Shots','Střely')+f": {w['previous_shots'][0]}:{w['previous_shots'][1]} → {w['shots'][0]}:{w['shots'][1]}"]
    shot=next((e for e in packet.get('evidence',[]) if e['kind']=='shot'),None)
    name=identity(shot['actors'][0]) if shot and shot['actors'] else team_name(packet['team'],language)
    label=tr(language,*{'goal':('Tor','Goal','Gól'),'save':('Schuss gehalten','Shot saved','Chycená střela'),'shot_blocked':('Schuss geblockt','Shot blocked','Zablokovaná střela'),'goal_kick':('Abstoß','Goal kick','Kop od branky'),'second_half':('Halbzeit','Half-time','Konec poločasu'),'full_time':('Spielende','Full-time','Konec zápasu')}.get(f.get('outcome'),('Schuss · offen','Shot · pending','Střela · čekáme')))
    score=':'.join(map(str,f['score']))
    return [f'{label} · {name}',tr(language,'Erfolgreiche Pässe','Completed passes','Přesné přihrávky')+f": {f['passes_in_attack']} · {score}"]


def personal(packet,team,player,contribution,language):
    focus=named(player) if player else team_name(team,language) if team is not None else tr(language,'Gesamtes Spiel','Whole match','Celý zápas')
    if language in ('fr','it','es','pt'):
        from story_languages import native_personal, contribution as count_contribution
        detail=native_personal(packet,language,team,player,contribution or count_contribution(packet,player))
        reason=tr(language,'Ihr Spieler war beteiligt','Your player was involved','Zapojil se váš hráč') if player else tr(language,'Mannschaftsüberblick','Team overview','Přehled týmu')
        return focus,detail,reason
    if player:
        values=contribution.get('counts',{}) if contribution else {}
        keys=('passes_made','passes_received','shots','saves','regains')
        labels=tr(language,('erfolgreiche Pässe','Ballannahmen','Schüsse','Paraden','Ballgewinne'),('completed passes','receipts','shots','saves','recoveries'),('přesné přihrávky','příjmy','střely','zákroky','zisky míče'))
        detail=', '.join(f'{label}: {values.get(key,0)}' for key,label in zip(keys,labels) if values.get(key,0))
        if detail:return focus,detail,tr(language,'Ihr Spieler war beteiligt','Your player was involved','Zapojil se váš hráč')
        if contribution and contribution.get('evidence_ids'):return focus,tr(language,'Der Spieler erscheint in den Quellen, hat aber keine gezählte Aktion in dieser Folge.','The player appears in the sources but has no counted action in this sequence.','Hráč je uveden ve zdrojích, ale v této sérii nemá započítanou akci.'),tr(language,'In Quellen genannt','Mentioned in sources','Uveden ve zdrojích')
        return focus,tr(language,'Für diesen Spieler ist keine Beteiligung an der Szene erfasst.','The player has no recorded involvement in this episode.','Účast hráče v epizodě není doložena.'),tr(language,'Spielkontext','Match context','Kontext zápasu')
    return focus,tr(language,'Szene der gewählten Mannschaft.','Episode of the selected team.','Epizoda vybraného týmu.') if team==packet['team'] else tr(language,'Gemeinsame Spielfakten.','Shared match facts.','Společná fakta o zápase.'),tr(language,'Mannschaftsüberblick','Team overview','Přehled týmu')


def localized_path(packet,language):
    result={'attack_path':deepcopy(packet.get('attack_path',[]))}
    labels=tr(language,['Angriff beginnt','Erfolgreiche Pässe','Schuss','Ausgang'],['Attack starts','Completed passes','Shot','Outcome'],['Začátek útoku','Přesné přihrávky','Střela','Výsledek'])
    for i,stage in enumerate(result.get('attack_path',[])):
        event=next((e for e in packet['evidence'] if e['id']==stage['event_ids'][-1]),None);kind=event['kind'] if event else ''
        stage['label']=labels[0 if i==0 else 1 if kind=='pass_completed' else 2 if kind=='shot' else 3]
    return result['attack_path']


def translated_packet(packet,language,audience='analyst'):
    result=deepcopy(packet);result.update(story(packet,language,audience))
    result['language']=language;result['audience']=audience
    for event in result['evidence']:
        event['source_title']=event.get('source_title',event['title']);event['source_text']=event.get('source_text',event['text'])
        event.update(event_display(event,language))
    result['attack_path']=localized_path(packet,language)
                                                                            
    interpretation=result.get('interpretation')
    if interpretation and interpretation.get('language','en')!=language:
        result['interpretation']=None;result['interpretation_available_in']=interpretation.get('language','en')
    return result


def pipeline_display(snapshot, language):
                                                                                     
    if language in ('fr','it','es','pt'):
        return translate_tree(snapshot,language)
    if language == 'en':
        return snapshot
    result = deepcopy(snapshot)
    cs = language == 'cs'
    for receipt in result['receipts']:
        progress = receipt['progress_m']
        receipt['label'] = ('Postup k brance' if cs else 'Raumgewinn') if progress >= 1 else (
            ('Přihrávka zpět' if cs else 'Rückpass') if progress <= -1 else
            ('Příčná přihrávka' if cs else 'Querpass'))
        receipt['explanation'] = (
            f"{team_name(receipt['team'], language)}: #{receipt['sender']} → #{receipt['receiver']}, "
            f"{receipt['distance_m']:.1f} m. " +
            ('Podélný postup' if cs else 'Raumgewinn in Längsrichtung') + f" {progress:+.1f} m. " +
            ('Přesné přihrávky v tomto držení: ' if cs else 'Erfolgreiche Pässe in diesem Ballbesitz: ') +
            str(receipt['possession_passes']) + '.')
        for event in receipt['source_events']:
            event.update(event_display(event, language))
    return result
