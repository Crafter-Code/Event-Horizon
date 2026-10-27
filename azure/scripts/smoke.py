                                                                                   
import argparse
import json
import time
from urllib.request import urlopen
from urllib.parse import urlsplit, urlencode
from urllib.error import HTTPError


def get(url):
    with urlopen(url,timeout=10) as response:return json.load(response)


def smoke(base, interval=2, expect_foundry=False):
    parts=urlsplit(base)
    if parts.scheme not in ('https','http') or parts.query or parts.fragment:raise ValueError('Invalid base URL')
    get(base+'/health/live');get(base+'/health/ready')
    journey=get(base+'/journey/state')
    if journey.get('schema_version')!='eh-journey-1' or 'episodes' not in journey or 'selected' not in journey:
        raise ValueError('Live source-to-screen journey unavailable')
    first=get(base+'/operations')
    time.sleep(interval)
    second=get(base+'/operations')
    if second['confirmed_tick']<=first['confirmed_tick']:raise ValueError('Confirmed match did not advance')
    if second['delivery']!='ok':raise ValueError('Ingress is retrying')
    if expect_foundry and second['narrative_provider']!='foundry':
        raise ValueError('Foundry did not initialize; application is using factual fallback')
    replay=get(base+'/replay-lab/state')
    if replay.get('schema_version')!='eh-replay-proof-1' or replay.get('status') not in ('idle','running','passed','stopped'):
        raise ValueError('Replay verification unavailable or failed')
    manifest=get(base+'/demo/manifest')
    if not manifest['report']['complete_match'] or manifest['report']['status']!='passed':
        raise ValueError('Complete verified demo match is missing')
    fingerprints=set()
    for language in ('en','cs','de'):
        for audience in ('fan','analyst','player'):
            query=urlencode({'at':5400,'language':language,'audience':audience,'player':'0:10','run_key':manifest['run_key']})
            state=get(base+'/demo/state?'+query)
            if (not state['finished'] or state['score']!=manifest['report']['score']
                    or state['language']!=language or state['audience']!=audience or not state['summary']):
                raise ValueError('Demo replay or personalized summary is inconsistent')
            fingerprints.add(state['summary']['fact_fingerprint'])
    if len(fingerprints)!=1:raise ValueError('Modes or languages changed demo facts')
    episode=next((e for e in manifest['episodes'] if e['kind']=='goal'),None)
    if episode is None:raise ValueError('Media rehearsal has no goal episode')
    scene=get(base+'/studio/scene?'+urlencode({'at':episode['available_at'],
              'episode':episode['id'],'run_key':manifest['run_key']}))
    if scene['status']!='ready' or scene['integrity']['status']!='passed':
        raise ValueError('Media rehearsal failed source checks')
    if {s['fact_fingerprint'] for s in scene['layouts'].values()}!={scene['card']['fact_fingerprint']}:
        raise ValueError('Media layouts disagree on facts')
    before=get(base+'/studio/scene?'+urlencode({'at':episode['time'],
               'episode':episode['id'],'run_key':manifest['run_key']}))
    if before['card'] is not None:raise ValueError('Media rehearsal revealed a future outcome')
    try:get(base+'/editor')
    except HTTPError as error:
        status=error.code;error.close()
        if status!=401:raise ValueError('Editor access check failed')
    else:raise ValueError('Editor controls are not protected')
    return {'advanced_ticks':second['confirmed_tick']-first['confirmed_tick'],
            'ingress':second['ingress'],'narrative_provider':second['narrative_provider'],
            'telemetry_export':second['telemetry']['export'],
            'demo_profiles':9,'demo_fact_fingerprint':next(iter(fingerprints)),'editor_protected':True,
            'replay_lab_status':replay['status'],'replay_lab_scope':'Read-only route availability; no verification run started',
            'media_layouts':3,'media_fact_fingerprint':scene['card']['fact_fingerprint'],
            'media_no_future_outcome':True,
            'journey_contract':journey['schema_version'],
            'scope':'HTTP pipeline and full replay; actual cloud model output and Monitor delivery require separate evidence'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('--expect-foundry',action='store_true');args=p.parse_args()
    print(json.dumps(smoke(args.url.rstrip('/'),expect_foundry=args.expect_foundry),indent=2))
