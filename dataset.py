                                                                                   

                                                                           
                                                                             
                                                        
   
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_STORED

from camera import SyntheticCamera
from generator_checks import GeneratorChecks
from pipeline import MatchPipeline
from roster import named_metadata
from simulation import GeneratorSettings, Match
from raster import CALIBRATION


def encoded(value):
    return (json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()


def duration_ticks(seconds,limit=5400):
    if type(seconds) not in (int,float) or not 0<seconds<=limit or abs(seconds*20-round(seconds*20))>1e-6:
        raise ValueError('Duration must be a multiple of 0.05 seconds in (0, '+str(limit)+']')
    return round(seconds*20)


def info(name):
    item=ZipInfo(name,date_time=(1980,1,1,0,0,0));item.compress_type=ZIP_STORED
    item.create_system=3;item.external_attr=0o100644<<16
    return item


def preview(frame_count):
    return ('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Event Horizon · synthetic video</title><style>body{background:#0c1422;color:#edf4ff;font:16px system-ui;max-width:850px;margin:30px auto;padding:16px}img{width:100%;border-radius:12px}input{width:100%}button{padding:10px;margin-right:15px}p{line-height:1.6;color:#b6c9df}</style>
<h1>Event Horizon · synthetic video</h1><p>20 frames/s · fixed calibrated camera · synthetic teams. Ground truth and independent predictions are separate JSONL files. Frame 1 is time 0.</p>
<img id="frame" alt="Synthetic football camera frame" src="frames/000001.png"><input id="seek" type="range" min="1" max="'''+str(frame_count)+'''" value="1" step="1" aria-label="Video frame"><button id="play">Play / pause</button><output id="clock">0.00 s</output>
<script>let n=1,timer=null;const seek=document.getElementById('seek');function show(){seek.value=n;document.getElementById('frame').src='frames/'+String(n).padStart(6,'0')+'.png';document.getElementById('clock').textContent=((n-1)/20).toFixed(2)+' s';}seek.oninput=()=>{n=Number(seek.value);show();};document.getElementById('play').onclick=()=>{if(timer){clearInterval(timer);timer=null;}else timer=setInterval(()=>{n=n>=Number(seek.max)?1:n+1;show();},50);};</script></html>''').encode()


def export_dataset(target, settings=None, seconds=15):
    ticks=duration_ticks(seconds)
    match=Match(settings);pipeline=MatchPipeline(match);checks=GeneratorChecks(match);camera=SyntheticCamera()
    files={};count=0;comparisons={}
    with ZipFile(target,'w',compression=ZIP_STORED,allowZip64=True) as archive, tempfile.SpooledTemporaryFile(max_size=1024*1024) as annotations:
        def put(name,data):
            archive.writestr(info(name),data);files[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        put('metadata.json',encoded(named_metadata(match.metadata())))
        put('scenario.json',encoded(match.scenario))
        for tick in range(ticks+1):
            if tick:
                stopped=bool(match.restart);period=match.period;match.advance()
                checks.validate(match);pipeline.validate_next(match)
                pipeline.advance(match,not stopped and not match.finished and period==match.period)
            camera.advance(match)
            if camera.error:raise ValueError('Camera recognition failed: '+camera.error)
            for item in camera.evaluation.examples:
                key=('truth',item['truth_id']) if 'truth_id' in item else ('prediction',item['prediction_id'])
                comparisons[key]=deepcopy(item)
            count+=1;put(f'frames/{count:06d}.png',camera.png)
            annotations.write(encoded({'frame_id':count,'tick':match.tick,'time_s':round(match.clock,2),
                'period':match.period,'in_play':not bool(match.restart) and not match.finished,
                'players':[{'team':p.team,'number':p.number,'x':round(p.x,6),'y':round(p.y,6)} for p in match.players],
                'ball':[round(v,6) for v in match.ball],'owner':None if match.owner is None else f'{match.players[match.owner].team}:{match.players[match.owner].number}',
                'possession_team':match.possession_team,'score':match.score[:]}))
        annotations.seek(0);digest=hashlib.sha256();size=0
        with archive.open(info('annotations.jsonl'),'w') as out:
            while data:=annotations.read(1024*1024):out.write(data);digest.update(data);size+=len(data)
        files['annotations.jsonl']={'sha256':digest.hexdigest(),'bytes':size}
        put('events.jsonl',b''.join(encoded(e) for e in match.events))
        put('predictions.jsonl',b''.join(encoded(e) for e in camera.recognizer.events))
        put('validation.json',encoded(checks.snapshot(match.clock)))
        put('recognition.json',encoded(camera.evaluation.snapshot()))
        put('recognition_matches.jsonl',b''.join(encoded(v) for v in comparisons.values()))
        expected=checks.expectations.snapshot(match.clock)
        for test in expected['expectations']:
            evidence=test['evidence']
            test['recognition']=comparisons.get(('truth',evidence['event_id']),{'status':'pending'}) if evidence else {'status':'no_source_event'}
        put('scenario_results.json',encoded(expected))
        episodes=[pipeline.insights.moment_data(m) for m in pipeline.insights.moments.values()]
        put('episodes.json',encoded(episodes))
        put('preview.html',preview(count))
        manifest={'schema_version':'eh-dataset-1','match_id':match.match_id,'settings':match.settings.as_dict(),
                  'scenario_id':match.settings.scenario,'duration_s':match.clock,'fps':20,'frame_count':count,
                  'event_count':len(match.events),'event_hash':match.event_digest.hexdigest(),
                  'calibration':deepcopy(CALIBRATION),'files':files,
                  'labels_used_as_model_input':False,'video_format':'lossless_png_sequence',
                  'expectations':checks.expectations.snapshot(match.clock)}
        archive.writestr(info('manifest.json'),encoded(manifest))
    return manifest


def verify_dataset(path):
    with ZipFile(path) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        if len(archive.namelist())!=len(set(archive.namelist())):raise ValueError('Duplicate archive paths')
        if set(archive.namelist())!=set(manifest['files'])|{'manifest.json'}:raise ValueError('Archive file list mismatch')
        for name,expected in manifest['files'].items():
            digest=hashlib.sha256();size=0
            with archive.open(name) as data:
                while block:=data.read(1024*1024):digest.update(block);size+=len(block)
            if expected!={'sha256':digest.hexdigest(),'bytes':size}:raise ValueError('Checksum mismatch: '+name)
        if hashlib.sha256(archive.read('events.jsonl')).hexdigest()!=manifest['event_hash']:raise ValueError('Event digest mismatch')
        return {'verified':True,'files':len(manifest['files']),'match_id':manifest['match_id'],'frames':manifest['frame_count']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=42);parser.add_argument('--scenario',default='open_play')
    parser.add_argument('--seconds',type=float,default=15);parser.add_argument('--output',type=Path)
    parser.add_argument('--verify',type=Path)
    args=parser.parse_args()
    try:
        if args.verify:print(json.dumps(verify_dataset(args.verify)));raise SystemExit()
        if not args.output:parser.error('--output is required for export')
        duration_ticks(args.seconds);settings=GeneratorSettings(args.seed,args.scenario)
                                                                                   
        with args.output.open('xb') as out:
            try:manifest=export_dataset(out,settings,args.seconds)
            except BaseException:out.close();args.output.unlink(missing_ok=True);raise
        print(json.dumps({'output':str(args.output),'frames':manifest['frame_count'],'events':manifest['event_count'],'expectations':manifest['expectations']['status']}))
    except (ValueError,OSError) as error:parser.error(str(error))
