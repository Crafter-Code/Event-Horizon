                                                                   

                                                                           
                                                                              
                                                                               
   
import argparse
import asyncio
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import time

from app import MatchSession
from cloud_contract import encode
from demonstration_store import DemoWriter,DemoReader,summary_key
from display_adapter import DisplayAdapter
from delivery import MaterialStream,overlay
from foundry_narrative import FoundryNarrator
from language_contract import language_proof
from match_report import MatchReport
from simulation import GeneratorSettings
from camera import SyntheticCamera
from roster import player_name
from simulation import Match


def checksum(value):return sha256(encode(value)).hexdigest()


def fingerprints(session):
    return {'events':session.confirmed_hash,'metrics':checksum(session.confirmed_frame),
            'facts':checksum({key:m.facts for key,m in session.insights.moments.items()}),
            'summary':session.reports.build(session.pipeline,0,session.pipeline.clock,True,None,'en')['fact_fingerprint']}


class ResponseAgent:
    def __init__(self,result=None,error=None):self.result,self.error=result,error
    async def run(self,_):
        if self.error:raise self.error
        return json.dumps(self.result,ensure_ascii=False)


def ai_failure_audit(session):
    moment=next((m for m in session.insights.moments.values() if m.complete and session.insights.verified(m)),None)
    if moment is None:return {'status':'not_exercised','cases':[]}
    baseline=fingerprints(session);cases=[];original=session.narrator
    packet=session.insights.moment_data(moment)
    good={k:packet[k] for k in ('what','why','change','evidence_ids')}
    for stage,error in (('analysis_timeout',TimeoutError()),('writer_unavailable',ConnectionError()),('verifier_unavailable',ConnectionError())):
        analyst=ResponseAgent({'evidence_ids':packet['evidence_ids']},error if stage=='analysis_timeout' else None)
        writer=ResponseAgent(good,error if stage=='writer_unavailable' else None)
        verifier=ResponseAgent({'approved':True,'unsupported_claims':[]},error if stage=='verifier_unavailable' else None)
        session.narrator=FoundryNarrator(analyst,writer,verifier)
        key=(session.run_id,moment.id,moment.revision)
        accepted=asyncio.run(session.process_narrative_job(key,packet))
        stable=fingerprints(session)==baseline
        cases.append({'id':stage,'injected':True,'handled':accepted,'metrics_and_facts_preserved':stable,
                      'factual_summary_available':bool(session.reports.build(session.pipeline,0,session.pipeline.clock,True,None,'en')['text']),
                      'fallback':moment.ai_status=='fallback'})
    for code,draft,verdict in (
        ('unsupported_number',{**good,'what':'Invented score 999:999.'},{'approved':True,'unsupported_claims':[]}),
        ('verification_rejected',good,{'approved':False,'unsupported_claims':['Unsupported interpretation']})):
        session.narrator=FoundryNarrator(ResponseAgent({'evidence_ids':packet['evidence_ids']}),ResponseAgent(draft),ResponseAgent(verdict))
        accepted=asyncio.run(session.process_narrative_job((session.run_id,moment.id,moment.revision),packet))
        cases.append({'id':code,'injected':True,'handled':accepted,'metrics_and_facts_preserved':fingerprints(session)==baseline,
                      'factual_summary_available':True,'fallback':moment.ai_status=='fallback'})
    session.narrator=original
    passed=all(c['handled'] and c['metrics_and_facts_preserved'] and c['factual_summary_available'] and c['fallback'] for c in cases)
    return {'status':'passed' if passed else 'failed','cases':cases,
            'scope':'injected SDK-agent errors through production exception handling; not a live cloud outage'}


def replay_audit(session,seconds,progress):
    mirror=MatchSession(session.match.settings,wall_clock=lambda:0)
    mirror.pump(seconds)
    values={'event_bytes':session.pipeline.events==mirror.pipeline.events,
            'event_digest':session.confirmed_hash==mirror.confirmed_hash,
            'confirmed_metrics':session.confirmed_frame==mirror.confirmed_frame,
            'context':session.pipeline.context.window()==mirror.pipeline.context.window(),
            'episode_facts':{k:m.facts for k,m in session.insights.moments.items()}=={k:m.facts for k,m in mirror.insights.moments.items()}}
    progress('repeatability',1)
    return {'status':'passed' if all(values.values()) else 'failed','checks':values,
            'event_sha256':mirror.confirmed_hash,'metric_sha256':checksum(mirror.confirmed_frame)}


def overlay_audit(session):
                                                                          

                                                                               
                                                                             
       
    stream=MaterialStream();count=0;failed=[];adapter=DisplayAdapter();last_clock=0
    for record in session.materials.history:
        if record['available_at']>=5400:continue
        card=stream.render(record,audience='analyst',language='en')
        cue=overlay(card,session.match.match_id,'acceptance')
        feed={'match_id':session.match.match_id,'run_key':'acceptance','viewer_key':'en-analyst','overlays':[cue]}
        gate=DisplayAdapter()
        before=gate.update(feed,max(0,cue['show_at']-.001))
        shown=gate.update(feed,cue['show_at'])
        removed=gate.update(feed,cue['remove_at'])
        correct=((cue['show_at']==0 or not before) and (cue['show_at']==0 or any(c['action']=='show' for c in shown)) and not gate.visible
                 and any(c['action']=='remove' for c in removed)
                 and cue['source_event_ids']==record['evidence_ids']
                 and all(session.pipeline.events[n-1]['time']<=cue['show_at'] for n in cue['source_event_ids']))
        if not correct:failed.append({'material_id':record['material_id'],'revision':record['revision']})
        last_clock=max(last_clock,cue['show_at'])
        adapter.update(feed,last_clock);count+=1
    changed={'match_id':session.match.match_id,'run_key':'different-run','viewer_key':'cs-player','overlays':[]}
    adapter.update(changed,0)
    return {'status':'passed' if not failed and not adapter.visible else 'failed','checked_revisions':count,
            'failed':failed,'timebase':'match_clock seconds; half-open show_at <= t < remove_at',
            'scope':'adapter schedule and source availability; browser paint is checked separately'}


def language_audit(session):
    failed=[];comparisons=0;verified=0;evidence=[]
    for moment in session.insights.moments.values():
        packet=session.insights.moment_data(moment)
        verified+=packet['verified']
        if not packet['verified']:evidence.append({'id':moment.id,'checks':packet['checks']})
        for audience in ('fan','analyst','player'):
            proof=language_proof(packet,audience,'full-match-acceptance',session.match.match_id)
            comparisons+=1
            if proof['parity']['status']!='passed':failed.append({'episode':moment.id,'audience':audience})
    return {'status':'passed' if not failed and not evidence else 'failed','episode_count':len(session.insights.moments),
            'verified_episodes':verified,'renditions':comparisons*3,'failed':failed,'evidence_failures':evidence,
            'scope':'protected source facts, IDs, numbers, names and template outputs; not automated fluency assessment'}


def summaries_audit(session,full):
    reports=MatchReport();summaries={};failed=[];baseline=None;profiles=0
                                                                        
    players=[None]+[{'team':t,'number':n} for t in (0,1) for n in range(1,12)]
    for player in players:
        for team in (None,0,1):
            references={}
            for audience in ('fan','analyst','player'):
                for language in ('en','cs','de'):
                    report=reports.build(session.pipeline,0,session.pipeline.clock,full,player,language,audience,team)
                    key=summary_key(language,audience,team,None if player is None else f"{player['team']}:{player['number']}")
                    summaries[key]=report;profiles+=1
                    if baseline is None:baseline=report['fact_fingerprint']
                    if report['fact_fingerprint']!=baseline:failed.append(key+':facts')
                    if any(not all(1<=n<=session.confirmed_count for n in e['evidence_ids']) for e in report['episodes']):failed.append(key+':sources')
                    if player and report['player']['player']['name']!=player_name(player['team'],player['number']):failed.append(key+':identity')
                    ids=[e['id'] for e in report['episodes']]
                    if 'ids' in references and ids!=references['ids']:failed.append(key+':selection')
                    references['ids']=ids
                                                                      
            fan=summaries[summary_key('en','fan',team,None if player is None else f"{player['team']}:{player['number']}")]
            analyst=summaries[summary_key('en','analyst',team,None if player is None else f"{player['team']}:{player['number']}")]
            if fan['text']==analyst['text']:failed.append(f'{team}:{player}:depth')
    return {'status':'passed' if not failed else 'failed','profiles':profiles,'failed':failed,'fact_fingerprint':baseline},summaries


def run(output,seed=42,scenario='open_play',seconds=5400,progress=None):
    if type(seconds) not in (int,float) or not 0<seconds<=5400 or abs(seconds*20-round(seconds*20))>1e-6:raise ValueError('Invalid duration')
    target=Path(output)
    if target.exists():raise ValueError('Output already exists; use a new path')
    target.parent.mkdir(parents=True,exist_ok=True)
    progress=progress or (lambda *_:None)
    started=time.monotonic();session=MatchSession(GeneratorSettings(seed,scenario),wall_clock=lambda:0,vision_enabled=True)
    temporary=target.with_suffix('.building.sqlite3')
    if temporary.exists():raise ValueError('A build already exists')
    writer=DemoWriter(temporary,session);writer.capture(session)
    frame_samples=[]
    try:
        for tick in range(1,round(seconds*20)+1):
            session.pump(tick*.05)
            if session.pipeline.last_error:raise ValueError(session.pipeline.last_error)
            writer.capture(session)
            if tick%1200==0:
                progress('match',round(session.match.clock/seconds,4))
                frame_samples.append({'tick':tick,'sha256':sha256(session.camera.png).hexdigest()})
                                                                                  
        session.camera.evaluation.finalize()
        repeatability=replay_audit(session,seconds,progress)
        languages=language_audit(session);progress('languages',1)
        summary_check,summaries=summaries_audit(session,seconds==5400);progress('summaries',1)
        overlays=overlay_audit(session);progress('overlays',1)
        ai=ai_failure_audit(session);progress('ai_failure',1)
        evaluation=session.camera.evaluation.snapshot()
        supplementary=[]
        if seconds==5400:
            for clip_scenario,clip_seconds in (('high_press',20),('counterattack',12)):
                clip=Match(GeneratorSettings(seed,clip_scenario));camera=SyntheticCamera()
                camera.advance(clip)
                for _ in range(int(clip_seconds*20)):clip.advance();camera.advance(clip)
                camera.evaluation.finalize()
                supplementary.append({'scenario':clip_scenario,'seconds':clip_seconds,
                    'event_sha256':clip.event_digest.hexdigest(),'evaluation':camera.evaluation.snapshot()})
        progress('video_finalized',1)
        counter=Counter(e['kind'] for e in session.pipeline.events)
        report={'schema':'eh-full-match-acceptance-1','complete_match':seconds==5400 and session.match.finished,
                'match_seconds':session.match.clock,'settings':session.match.settings.as_dict(),
                'event_count':session.confirmed_count,'event_sha256':session.confirmed_hash,
                'score':session.confirmed_frame['score'],'event_kinds':dict(sorted(counter.items())),
                'generator':session.generator_checks.snapshot(session.match.clock),
                'repeatability':repeatability,'narratives':languages,'summaries':summary_check,
                'synchronized_graphics':overlays,'ai_failure':ai,
                'video':{'status':'measured','evaluation':evaluation,'recognized_events':len(session.camera.recognizer.events),
                         'all_truth_settled':evaluation['pending_truth']==0 and evaluation['pending_predictions']==0,
                         'unexercised_classes':[kind for kind,s in evaluation['event_scores'].items() if s['tp']+s['fn']==0],
                         'frame_samples':frame_samples,'supplementary_clips':supplementary,'camera_fps':20,'scope':'fixed synthetic RGB8 camera only'},
                'execution':{'elapsed_wall_s':round(time.monotonic()-started,2),'cloud_inference':False,'azure_deployment':False}}
        checks=[repeatability,languages,summary_check,overlays]
        status=all(c['status']=='passed' for c in checks) and ai['status'] in ('passed','not_exercised') and report['video']['all_truth_settled']
        report['status']='passed' if status and report['complete_match'] else 'partial' if status else 'failed'
        writer.finalize(session,report,summaries)
                                                                                  
        reader=DemoReader(temporary)
        for sample in frame_samples:
            import base64
            png=base64.b64decode(reader.state(sample['tick']*.05)['frame_png'])
            if sha256(png).hexdigest()!=sample['sha256']:raise ValueError('Exported camera frame differs')
        temporary.replace(target)
        progress('complete',1)
        return report
    except BaseException:
        try:writer.close()
        except Exception:pass
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--report',type=Path)
    parser.add_argument('--seed',type=int,default=42);parser.add_argument('--scenario',default='open_play');parser.add_argument('--seconds',type=float,default=5400)
    args=parser.parse_args()
    def progress(stage,value):print(json.dumps({'stage':stage,'progress':value}),flush=True)
    try:result=run(args.output,args.seed,args.scenario,args.seconds,progress)
    except (ValueError,OSError) as error:parser.error(str(error))
    if args.report:args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'seconds':result['match_seconds'],'events':result['event_count'],'score':result['score']},ensure_ascii=False),flush=True)
    raise SystemExit(1 if result['status']=='failed' else 0)
