                                                                           

                                                                
                                                                              
                                                                                
                                                                                 
   
from copy import deepcopy
import argparse
import json
import math
import time
from urllib.parse import urlencode
from urllib.request import urlopen


class DisplayAdapter:
    def __init__(self):
        self.identity=None
        self.visible={}

    def update(self, feed, playback_time=None):
        now=feed['playback_clock'] if playback_time is None else playback_time
        if type(now) not in (int,float) or not math.isfinite(now) or now<0:
            raise ValueError('Invalid media clock')
        identity=(feed['match_id'],feed['run_key'],feed['viewer_key'])
        candidates={}
                                                                    
        for cue in feed['overlays']:
            if cue['schema_version']!='eh-overlay-1' or (cue['match_id'],cue['run_key'])!=identity[:2]:
                raise ValueError('Overlay belongs to another match or schema')
            start,end=cue['show_at'],cue['remove_at']
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end)) or not 0<=start<end:
                raise ValueError('Invalid overlay schedule')
            if cue['timebase']!={'kind':'match_clock','unit':'seconds','origin':0}:
                raise ValueError('Unsupported timebase')
            if start<=now<end and cue['layer'] not in feed.get('disabled_layers',[]):
                old=candidates.get(cue['layer'])
                rank=lambda c:(c.get('priority',0),c['show_at'],c['revision'])
                if old is None or rank(cue)>rank(old):candidates[cue['layer']]=cue
        commands=[]
        if identity!=self.identity:
            for layer,cue in self.visible.items():commands.append({'action':'remove','layer':layer,'overlay_id':cue['overlay_id'],'at':now,'reason':'match_or_preferences_changed'})
            self.visible={};self.identity=identity
        for layer,cue in self.visible.items():
            if layer not in candidates:commands.append({'action':'remove','layer':layer,'overlay_id':cue['overlay_id'],'at':now,'reason':'expired_or_disabled'})
        for layer,cue in candidates.items():
            old=self.visible.get(layer)
            if old is None or old['overlay_id']!=cue['overlay_id']:
                if old:commands.append({'action':'remove','layer':layer,'overlay_id':old['overlay_id'],'at':now,'reason':'replaced'})
                commands.append({'action':'show','layer':layer,'at':now,'overlay':deepcopy(cue)})
            elif old!=cue:commands.append({'action':'update','layer':layer,'at':now,'overlay':deepcopy(cue)})
        self.visible=deepcopy(candidates)
        return commands


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--delay-seconds',type=float,default=0)
    parser.add_argument('--language',choices=('en','cs','de','fr','it','es','pt'),default='en')
    parser.add_argument('--audience',choices=('fan','analyst','player'),default='fan')
    parser.add_argument('--channel',choices=('viewer','broadcast'),default='viewer')
    parser.add_argument('--team',choices=('all','0','1'),default='all')
    parser.add_argument('--player',default='none')
    args=parser.parse_args()
    if not math.isfinite(args.delay_seconds) or not 0<=args.delay_seconds<=5400:parser.error('Invalid delay')
    adapter=DisplayAdapter()
    query={'language':args.language,'audience':args.audience,'team':args.team,'player':args.player,'channel':args.channel,'limit':1}
    last_feed=None;media=0
    def emit(commands):
        for command in commands:print(json.dumps(command,ensure_ascii=False),flush=True)
    try:
        while True:
            try:
                with urlopen(args.base_url.rstrip('/')+'/materials?'+urlencode(query),timeout=3) as response:feed=json.load(response)
                media=max(0,feed['match_clock']-args.delay_seconds)
                if args.delay_seconds:
                    with urlopen(args.base_url.rstrip('/')+'/materials?'+urlencode({**query,'at':media}),timeout=3) as response:feed=json.load(response)
                emit(adapter.update(feed,media));last_feed=feed
            except (OSError,ValueError,KeyError,TypeError):
                if last_feed:emit(adapter.update({**last_feed,'overlays':[]},media))
                time.sleep(.4)
            time.sleep(.1)
    except KeyboardInterrupt:pass
    finally:
        if last_feed:emit(adapter.update({**last_feed,'overlays':[]},media))


if __name__=='__main__':main()
