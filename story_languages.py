                                                                           

                                                                                
                                                                           
   
from copy import deepcopy
import math

from locales import story, caption, personal
from language_contract import digest
from roster import player_name


LANGUAGES = ('en', 'cs', 'de', 'fr', 'it', 'es', 'pt')
NAMES = {'en':'English','cs':'Čeština','de':'Deutsch','fr':'Français',
         'it':'Italiano','es':'Español','pt':'Português'}
COPY = {
 'fr': {
  'teams':['Bleus','Rouges'], 'goal':'But', 'shot':'Tir', 'pressure':'Évolution de la pression', 'rhythm':'Évolution du rythme',
  'shot_short':'{name} a tenté un tir.', 'shot_detail':'{name} tire à {distance:.1f} m du but. Adversaires à moins de 5 m : {pressure}.',
  'outcomes':{'goal':'Le ballon est au fond des filets.','save':'Le gardien arrête le tir et prend possession du ballon.',
   'shot_blocked':'Un défenseur bloque le tir et récupère le ballon.','goal_kick':'Le ballon sort ; un six mètres est accordé.',
   'second_half':'La pause interrompt la séquence.','full_time':'Le coup de sifflet final interrompt la séquence.'},
  'pending':'Le résultat du tir est encore en attente.', 'passes':'Passes réussies avant le tir : {count}.',
  'fast':'Après la récupération, le tir suit {seconds:.1f} s plus tard.', 'score':'Le score est de {score}.',
  'window':'Entre {start:.1f} et {end:.1f} s : tirs {shots}; possession {possession}.',
  'previous':'Tirs dans la période précédente : {shots}.',
  'pressure_brief':'La pression autour du ballon a changé.', 'rhythm_brief':'Le rythme des passes, des attaques et des pertes de balle a changé.',
  'pattern_brief':'L’activité devant le but a changé.', 'basis':'Cette observation compare deux périodes de jeu voisines.',
  'cause':'La cause tactique du changement n’est pas établie.',
  'labels':{'pressure_seconds':'pression, s','passes':'passes commencées','attacks':'attaques','losses':'pertes de balle'},
  'interval':'Période observée : {start:.1f}–{end:.1f} s.',
  'counts':['passes réussies','passes reçues','tirs','arrêts','récupérations'],
  'no_player':'Aucune participation de ce joueur n’est enregistrée dans cette séquence.',
  'mentioned':'Ce joueur figure dans les sources, sans action comptabilisée dans cette séquence.',
  'team_focus':'Équipe suivie : {team}. Les faits du match restent les mêmes.', 'whole':'Les mêmes faits du match pour tous les publics.',
  'recap_title':'Résumé du match', 'recap':'{blue} : {bg} buts, {bp}/{ba} passes réussies, {bs} tirs. {red} : {rg} buts, {rp}/{ra} passes réussies, {rs} tirs.',
  'recap_fan':'Score final : {score}. Tirs : {bs}:{rs}.',
  'player_recap':'{name} : passes réussies {passes}/{attempts}, tirs {shots}, tacles {tackles}.',
  'checkpoint':'{time} · {team} marque. Score : {score}.',
 },
 'it': {
  'teams':['Blu','Rossi'], 'goal':'Gol', 'shot':'Tiro', 'pressure':'Variazione della pressione', 'rhythm':'Variazione del ritmo',
  'shot_short':'{name} ha effettuato un tiro.', 'shot_detail':'{name} tira da {distance:.1f} m. Avversari entro 5 m: {pressure}.',
  'outcomes':{'goal':'Il pallone è in rete.','save':'Il portiere para il tiro e prende possesso del pallone.',
   'shot_blocked':'Un difensore blocca il tiro e recupera il pallone.','goal_kick':'Il pallone esce; viene assegnata una rimessa dal fondo.',
   'second_half':'L’intervallo interrompe la sequenza.','full_time':'Il fischio finale interrompe la sequenza.'},
  'pending':'L’esito del tiro è ancora in attesa.', 'passes':'Passaggi completati prima del tiro: {count}.',
  'fast':'Dopo il recupero del pallone, il tiro arriva {seconds:.1f} s più tardi.', 'score':'Il punteggio è {score}.',
  'window':'Tra {start:.1f} e {end:.1f} s: tiri {shots}; possesso {possession}.',
  'previous':'Tiri nel periodo precedente: {shots}.',
  'pressure_brief':'La pressione intorno al pallone è cambiata.', 'rhythm_brief':'Il ritmo di passaggi, attacchi e perdite di possesso è cambiato.',
  'pattern_brief':'L’attività davanti alla porta è cambiata.', 'basis':'L’osservazione confronta due periodi di gioco adiacenti.',
  'cause':'La causa tattica del cambiamento non è accertata.',
  'labels':{'pressure_seconds':'pressione, s','passes':'passaggi iniziati','attacks':'attacchi','losses':'perdite di possesso'},
  'interval':'Periodo osservato: {start:.1f}–{end:.1f} s.',
  'counts':['passaggi completati','passaggi ricevuti','tiri','parate','recuperi'],
  'no_player':'Non risulta alcun coinvolgimento di questo giocatore nella sequenza.',
  'mentioned':'Il giocatore compare nelle fonti, senza un’azione conteggiata in questa sequenza.',
  'team_focus':'Squadra seguita: {team}. I fatti della partita restano gli stessi.', 'whole':'Gli stessi fatti della partita per tutti i pubblici.',
  'recap_title':'Riepilogo della partita', 'recap':'{blue}: {bg} gol, {bp}/{ba} passaggi completati, {bs} tiri. {red}: {rg} gol, {rp}/{ra} passaggi completati, {rs} tiri.',
  'recap_fan':'Risultato finale: {score}. Tiri: {bs}:{rs}.',
  'player_recap':'{name}: passaggi completati {passes}/{attempts}, tiri {shots}, contrasti vinti {tackles}.',
  'checkpoint':'{time} · {team} segna. Punteggio: {score}.',
 },
 'es': {
  'teams':['Azules','Rojos'], 'goal':'Gol', 'shot':'Disparo', 'pressure':'Cambio de presión', 'rhythm':'Cambio de ritmo',
  'shot_short':'{name} realizó un disparo.', 'shot_detail':'{name} dispara desde {distance:.1f} m. Rivales a menos de 5 m: {pressure}.',
  'outcomes':{'goal':'El balón está en la red.','save':'El portero detiene el disparo y se hace con el balón.',
   'shot_blocked':'Un defensor bloquea el disparo y recupera el balón.','goal_kick':'El balón sale; se concede un saque de meta.',
   'second_half':'El descanso interrumpe la secuencia.','full_time':'El pitido final interrumpe la secuencia.'},
  'pending':'El resultado del disparo sigue pendiente.', 'passes':'Pases completados antes del disparo: {count}.',
  'fast':'Tras la recuperación, el disparo llega {seconds:.1f} s después.', 'score':'El marcador es {score}.',
  'window':'Entre {start:.1f} y {end:.1f} s: disparos {shots}; posesión {possession}.',
  'previous':'Disparos en el periodo anterior: {shots}.',
  'pressure_brief':'La presión alrededor del balón ha cambiado.', 'rhythm_brief':'Ha cambiado el ritmo de pases, ataques y pérdidas de posesión.',
  'pattern_brief':'Ha cambiado la actividad frente a la portería.', 'basis':'La observación compara dos periodos de juego consecutivos.',
  'cause':'No se ha establecido la causa táctica del cambio.',
  'labels':{'pressure_seconds':'presión, s','passes':'pases iniciados','attacks':'ataques','losses':'pérdidas de posesión'},
  'interval':'Periodo observado: {start:.1f}–{end:.1f} s.',
  'counts':['pases completados','pases recibidos','disparos','paradas','recuperaciones'],
  'no_player':'No se ha registrado participación de este jugador en la secuencia.',
  'mentioned':'El jugador aparece en las fuentes, sin una acción contabilizada en esta secuencia.',
  'team_focus':'Equipo seguido: {team}. Los hechos del partido se mantienen.', 'whole':'Los mismos hechos del partido para todos los públicos.',
  'recap_title':'Resumen del partido', 'recap':'{blue}: {bg} goles, {bp}/{ba} pases completados, {bs} disparos. {red}: {rg} goles, {rp}/{ra} pases completados, {rs} disparos.',
  'recap_fan':'Marcador final: {score}. Disparos: {bs}:{rs}.',
  'player_recap':'{name}: pases completados {passes}/{attempts}, disparos {shots}, entradas ganadas {tackles}.',
  'checkpoint':'{time} · {team} marca. Marcador: {score}.',
 },
 'pt': {
  'teams':['Azuis','Vermelhos'], 'goal':'Golo', 'shot':'Remate', 'pressure':'Mudança de pressão', 'rhythm':'Mudança de ritmo',
  'shot_short':'{name} fez um remate.', 'shot_detail':'{name} remata a {distance:.1f} m. Adversários a menos de 5 m: {pressure}.',
  'outcomes':{'goal':'A bola está na baliza.','save':'O guarda-redes defende o remate e fica com a bola.',
   'shot_blocked':'Um defesa bloqueia o remate e recupera a bola.','goal_kick':'A bola sai; é assinalado um pontapé de baliza.',
   'second_half':'O intervalo interrompe a sequência.','full_time':'O apito final interrompe a sequência.'},
  'pending':'O resultado do remate ainda está pendente.', 'passes':'Passes completos antes do remate: {count}.',
  'fast':'Após a recuperação, o remate surge {seconds:.1f} s depois.', 'score':'O resultado é {score}.',
  'window':'Entre {start:.1f} e {end:.1f} s: remates {shots}; posse {possession}.',
  'previous':'Remates no período anterior: {shots}.',
  'pressure_brief':'A pressão à volta da bola mudou.', 'rhythm_brief':'O ritmo de passes, ataques e perdas de posse mudou.',
  'pattern_brief':'A atividade diante da baliza mudou.', 'basis':'A observação compara dois períodos de jogo consecutivos.',
  'cause':'A causa tática da mudança não está demonstrada.',
  'labels':{'pressure_seconds':'pressão, s','passes':'passes iniciados','attacks':'ataques','losses':'perdas de posse'},
  'interval':'Período observado: {start:.1f}–{end:.1f} s.',
  'counts':['passes completos','passes recebidos','remates','defesas','recuperações'],
  'no_player':'Não foi registada participação deste jogador na sequência.',
  'mentioned':'O jogador aparece nas fontes, sem uma ação contabilizada nesta sequência.',
  'team_focus':'Equipa seguida: {team}. Os factos do jogo mantêm-se.', 'whole':'Os mesmos factos do jogo para todos os públicos.',
  'recap_title':'Resumo do jogo', 'recap':'{blue}: {bg} golos, {bp}/{ba} passes completos, {bs} remates. {red}: {rg} golos, {rp}/{ra} passes completos, {rs} remates.',
  'recap_fan':'Resultado final: {score}. Remates: {bs}:{rs}.',
  'player_recap':'{name}: passes completos {passes}/{attempts}, remates {shots}, desarmes {tackles}.',
  'checkpoint':'{time} · {team} marca. Resultado: {score}.',
 },
}


def contribution(packet, player):
    counts = dict.fromkeys(('passes_made','passes_received','shots','saves','regains'),0)
    ids=[]
    for event in packet['evidence']:
        actors=event.get('actors',[])
        if player not in actors:continue
        ids.append(event['id']);kind=event['kind']
        if kind=='pass_completed':
            counts['passes_made']+=actors[0]==player
            counts['passes_received']+=len(actors)>1 and actors[1]==player
        counts['shots']+=kind=='shot' and actors[0]==player
        counts['saves']+=kind=='save' and actors[-1]==player
        counts['regains']+=kind in ('tackle','interception','ball_recovered') and actors[-1]==player
    return {'counts':counts,'evidence_ids':ids}


def native_personal(packet, language, team, player, involvement):
    l=COPY[language]
    if player:
        name=f"{player_name(player['team'],player['number'])} (#{player['number']})"
        values=zip(l['counts'],involvement['counts'].values())
        detail=', '.join(f'{label}: {count}' for label,count in values if count)
        return f'{name}: '+(detail or l['mentioned'] if involvement['evidence_ids'] else l['no_player'])
    return l['team_focus'].format(team=l['teams'][team]) if team is not None else l['whole']


def native_story(packet, language, audience):
    l=COPY[language];f=packet['facts'];w=f['window'];fan=audience=='fan'
    if packet['kind']=='trend':
        subtype=f.get('context_change');a=f.get('comparison',{}).get('current');b=f.get('comparison',{}).get('previous')
        title=l['pressure'] if subtype=='pressure' else l['rhythm']
        brief=l['pressure_brief'] if subtype=='pressure' else l['rhythm_brief'] if subtype else l['pattern_brief']
        detail=brief
        if a and b:
            keys=['pressure_seconds'] if subtype=='pressure' else ['passes','attacks','losses']
            detail='; '.join(l['teams'][t]+': '+', '.join(f"{l['labels'][key]} {b[key][t]} → {a[key][t]}" for key in keys) for t in (0,1))+'.'
        elif 'previous_shots' in w:
            detail=l['previous'].format(shots=':'.join(map(str,w['previous_shots'])))+' '+l['window'].format(start=w['start'],end=w['end'],shots=':'.join(map(str,w['shots'])),possession=f"{w['possession'][0]}%:{w['possession'][1]}%")
        return {'title':title,'what':brief if fan else detail,'why':l['basis'],
                'change':l['cause']+('' if fan else ' '+l['interval'].format(start=w['start'],end=w['end']))}
    shot=next((e for e in packet['evidence'] if e['kind']=='shot'),None)
    goal=next((e for e in packet['evidence'] if e['kind']=='goal'),None)
    event=shot or goal or packet['evidence'][0];actors=event.get('actors',[])
    name=player_name(actors[0]['team'],actors[0]['number']) if actors else l['teams'][packet['team']]
    outcome=f.get('outcome');title=f"{l['goal'] if outcome=='goal' else l['shot']} · {name}"
    details=shot.get('details',{}) if shot else {}
    what=l['shot_detail'].format(name=name,distance=details['distance_m'],pressure=details['pressure_count']) if not fan and 'distance_m' in details and 'pressure_count' in details else l['shot_short'].format(name=name)
    what+=' '+l['outcomes'].get(outcome,l['pending'])
    why=l['passes'].format(count=f.get('passes_in_attack',0))
    regain=next((e for e in packet['evidence'] if e['kind'] in ('interception','tackle')),None)
    if f.get('counterattack') and shot and regain:
        why=l['fast'].format(seconds=shot['time']-regain['time'])+('' if fan else ' '+why)
    change=l['score'].format(score=':'.join(map(str,f.get('score',[0,0]))))
    if not fan:
        change+=' '+l['window'].format(start=w['start'],end=w['end'],shots=':'.join(map(str,w['shots'])),possession=f"{w['possession'][0]}%:{w['possession'][1]}%")
        if w['end']>=120:change+=' '+l['previous'].format(shots=':'.join(map(str,w['previous_shots'])))
    return {'title':title,'what':what,'why':why,'change':change}


def recap(summary, language, audience):
    if summary is None:return None
    facts=summary['facts']
    if facts['end']!=5400 or not facts['complete']:raise ValueError('Recap requires full time')
    source_ids=sorted({key for e in summary['episodes'] for key in e['evidence_ids']}|
                      set(summary.get('story_arc',{}).get('source_event_ids',[])))
    if language not in COPY:
        return {'title':summary['title'],'text':summary['text'],'fact_fingerprint':summary['fact_fingerprint'],
                'source_event_ids':source_ids}
    l=COPY[language];goals=facts['goals'];passes=facts['passes'];attempts=facts['attempts'];shots=facts['shots']
    text=l['recap_fan'].format(score=f'{goals[0]}:{goals[1]}',bs=shots[0],rs=shots[1]) if audience=='fan' else l['recap'].format(
        blue=l['teams'][0],red=l['teams'][1],bg=goals[0],rg=goals[1],bp=passes[0],rp=passes[1],ba=attempts[0],ra=attempts[1],bs=shots[0],rs=shots[1])
    if summary.get('player'):
        p=summary['player'];s=p['statistics']
        text+=' '+l['player_recap'].format(name=p['player']['name'],passes=s['passes'],attempts=s['attempts'],shots=s['shots'],tackles=s['tackles'])
    points=[]
    for point in summary.get('story_arc',{}).get('checkpoints',[]):
        if point['kind'] in ('opening_goal','equalizer','lead_restored','takes_lead','extends_lead','reduces_deficit'):
                                                                                
            points.append({'event_id':point['event_id'],'time':point['time'],'score':point['score'][:]})
    return {'title':l['recap_title'],'text':text,'goals':points,
            'fact_fingerprint':summary['fact_fingerprint'],
            'source_event_ids':source_ids}


def render(packet, language='en', audience='fan', team=None, player=None, clock=0, summary=None):
    if language not in LANGUAGES or audience not in ('fan','analyst','player'):
        raise ValueError('Unsupported explanation language or audience')
    if type(clock) not in (int,float) or not math.isfinite(clock) or not 0<=clock<=5400:
        raise ValueError('Invalid story clock')
    result={'schema_version':'eh-story-language-1','language':language,'audience':audience,'clock':clock,
            'provenance':{'kind':'authored_factual_templates','model_generated':False},
            'status':'waiting','episode':None,'recap':recap(summary,language,audience) if summary and clock>=5400 else None}
    if packet is None:return result
    if not packet.get('verified'):
        return {**result,'status':'held'}
    if packet['time']>clock or any(e['time']>clock for e in packet['evidence']):
        raise ValueError('Future evidence is unavailable')
    involvement=contribution(packet,player) if player else None
    if language in COPY:
        prose=native_story(packet,language,audience)
        personal_text=native_personal(packet,language,team,player,involvement)
        caption_text=prose['title']+'\n'+COPY[language]['passes'].format(count=packet['facts'].get('passes_in_attack',0)) if packet['kind']!='trend' else prose['title']
    else:
        prose=story(packet,language,audience)
        focus,detail,_=personal(packet,team,player,involvement,language)
        personal_text=focus+' · '+detail
        caption_text='\n'.join(caption(packet,language))
    protected={'id':packet['id'],'revision':packet['revision'],'time':packet['time'],
               'facts':deepcopy(packet['facts']),'evidence_ids':packet['evidence_ids'][:],
               'actors':deepcopy(packet['actors'])}
    result.update(status='ready',episode={**prose,'caption':caption_text,'personal':personal_text,
        'id':packet['id'],'revision':packet['revision'],'time':packet['time'],'complete':packet['complete'],
        'fact_fingerprint':packet['fact_fingerprint'],'source_event_ids':packet['evidence_ids'][:],
        'protected':protected,'protected_sha256':digest(protected)})
    return result
