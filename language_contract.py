                                                                                 

                                                                                
                                                                           
   
from copy import deepcopy
from collections import Counter
import re
from hashlib import sha256
import json
from urllib.parse import urlencode

from locales import story, caption, identity
from simulation import TEAMS

                                                                      
LANGUAGES=('en','cs','de')


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def narrative_view(packet,language,audience,run_key,match_id):
    prose=story(packet,language,audience)
    names=[{'team':a['team'],'number':a['number'],'name':identity(a)} for a in packet['actors']]
    sources=[{'event_id':e['id'],'time':e['time'],'href':'/event?'+urlencode({'run_key':run_key,'id':e['id']})} for e in packet['evidence']]
    protected={'episode_id':packet['id'],'revision':packet['revision'],'time':packet['time'],
               'match_id':match_id,'run_key':run_key,'facts':deepcopy(packet['facts']),
               'teams':[{'id':t,'name':name} for t,name in enumerate(TEAMS)],
               'names':names,'sources':sources,'evidence_ids':packet['evidence_ids'][:]}
    return {'language':language,'audience':audience,**prose,'caption':'\n'.join(caption(packet,language)),
            'protected':protected,'facts_sha256':digest(protected)}


def parity(views):
    if not views:return {'status':'failed','checks':[]}
    reference=views[0]['protected']
    keys=('episode_id','revision','time','match_id','run_key','facts','teams','names','sources','evidence_ids')
    checks=[{'key':key,'passed':all(v['protected'].get(key)==reference[key] for v in views)} for key in keys]
    checks.append({'key':'fingerprint','passed':all(v['facts_sha256']==digest(v['protected']) for v in views)})
    copy_text=lambda v:' '.join(v[k] for k in ('title','what','why','change','caption'))
    number_tokens=lambda v:Counter(re.findall(r'[-+]?\d+(?:\.\d+)?',copy_text(v)))
    checks.append({'key':'copy_numbers','passed':all(number_tokens(v)==number_tokens(views[0]) for v in views)})
    visible_names=lambda v:{p['name'] for p in reference['names'] if p['name'] in copy_text(v)}
    checks.append({'key':'copy_names','passed':all(visible_names(v)==visible_names(views[0]) for v in views)})
    checks.append({'key':'languages','passed':len(views)==len(LANGUAGES) and {v['language'] for v in views}==set(LANGUAGES)})
    return {'status':'passed' if all(c['passed'] for c in checks) else 'failed','checks':checks}


def language_proof(packet,audience,run_key,match_id):
    views=[narrative_view(packet,language,audience,run_key,match_id) for language in ('en','cs','de')]
    return {'schema_version':'eh-language-proof-1','views':views,'parity':parity(views)}
