                                                                                     
import argparse
import json
from pathlib import Path

from language_contract import language_proof
from pipeline import MatchPipeline
from simulation import Match, GeneratorSettings


def run(seed=42,scenario='open_play',seconds=5400):
    if type(seconds) not in (float,int) or not 0<seconds<=5400 or abs(seconds*20-round(seconds*20))>1e-6:
        raise ValueError('Duration must be a multiple of 0.05 s in (0, 5400]')
    match=Match(GeneratorSettings(seed,scenario));pipeline=MatchPipeline(match)
    while match.clock<seconds:
        stopped=bool(match.restart);period=match.period;match.advance()
        pipeline.advance(match,not stopped and not match.finished and match.period==period)
    episodes=[];failed=[]
    for moment in pipeline.insights.moments.values():
        packet=pipeline.insights.moment_data(moment);results={}
        for audience in ('fan','analyst','player'):
            proof=language_proof(packet,audience,'reproducible-audit',match.match_id)
            results[audience]=proof['parity']
            if proof['parity']['status']!='passed':failed.append({'episode':moment.id,'audience':audience})
        episodes.append({'id':moment.id,'kind':moment.kind,'time':moment.time,'source_ids':moment.evidence_ids[:],'audiences':results})
    return {'schema_version':'eh-language-audit-1','scope':'template rendition and protected-data parity; not an automated fluency rating',
            'settings':match.settings.as_dict(),'match_seconds':match.clock,'event_count':len(match.events),
            'event_sha256':match.event_digest.hexdigest(),'languages':['en','cs','de'],
            'episode_count':len(episodes),'renditions':len(episodes)*9,'failed':failed,'episodes':episodes,
            'status':'failed' if failed else 'passed'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=42);parser.add_argument('--scenario',default='open_play')
    parser.add_argument('--seconds',type=float,default=5400);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:result=run(args.seed,args.scenario,args.seconds)
    except ValueError as error:parser.error(str(error))
    encoded=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(encoded)
    else:print(encoded)
    raise SystemExit(1 if result['failed'] else 0)
