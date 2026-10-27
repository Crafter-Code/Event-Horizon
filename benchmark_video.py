                                                                                         
import argparse
import json
import time
from pathlib import Path

from camera import SyntheticCamera
from simulation import Match,GeneratorSettings


def run(seed=42,seconds=5400):
    match=Match(GeneratorSettings(seed));camera=SyntheticCamera();started=time.monotonic()
    while match.clock<seconds and not match.finished:
        match.advance();camera.advance(match)
    result=camera.snapshot(False)
    return {'seed':seed,'match_seconds':match.clock,'source_events':len(match.events),
            'source_hash':match.event_digest.hexdigest(),'score':match.score,
            'elapsed_wall_s':round(time.monotonic()-started,2),
            'evaluation':result['evaluation'],'recognized_events':result['event_count']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--seconds',type=float,default=5400)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not 0<args.seconds<=5400:parser.error('--seconds must be in (0,5400]')
    try:GeneratorSettings(args.seed)
    except ValueError as error:parser.error(str(error))
    output=json.dumps(run(args.seed,args.seconds),ensure_ascii=False,indent=2)
    if args.output:args.output.write_text(output+'\n')
    else:print(output)
