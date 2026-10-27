                                                                                  

from dataclasses import replace

from simulation import MODEL_VERSION


SCHEMA_VERSION = 'eh-intelligence-provenance-1'
TRACE_WINDOW = 24


def _approved_trace(trace, moment):
                                                                                      
    if trace.get('status') != 'verified' or not isinstance(moment.interpretation, dict):
        return False
    stages = trace.get('stages', [])
    if (not isinstance(stages, list) or not 3 <= len(stages) <= 8
            or any(not isinstance(item, dict) for item in stages)):
        return False
    analysis = [item for item in stages if item.get('role') == 'analysis']
    writing = [item for item in stages if item.get('role') == 'writing']
    checks = [item for item in stages if item.get('role') == 'fact_checking']
    peers = [item for item in stages if item.get('role') == 'broadcast_a2a']
    if not analysis or not writing or not checks:
        return False
    selected = analysis[-1].get('evidence_ids')
    cited = moment.interpretation.get('evidence_ids')
    return (analysis[-1].get('status') == 'complete'
            and isinstance(selected, list) and bool(selected)
            and all(type(key) is int and key in moment.evidence_ids for key in selected)
            and isinstance(cited, list) and bool(cited)
            and all(type(key) is int and key in selected for key in cited)
            and writing[-1].get('status') == 'complete'
            and writing[-1].get('evidence_ids') == cited
            and checks[-1].get('status') == 'approved'
            and checks[-1].get('issue_count') == 0
            and checks[-1].get('attempt') == writing[-1].get('attempt')
            and stages.index(analysis[-1]) < stages.index(writing[-1]) < stages.index(checks[-1])
            and all(moment.interpretation.get(key) for key in ('what', 'why', 'change'))
            and (not peers or peers[-1].get('status') == 'approved'))


def build_provenance(session):
                                                                                     

                                                                              
                                                                           
                                                                          
       
    narrator = session.narrator
    moments = session.insights.moments
    counts = {'verified': 0,
              'pending': sum(item.ai_status == 'pending' for item in moments.values()),
              'fallback': sum(item.ai_status == 'fallback' for item in moments.values())}
    proof = None
    latest = None
    verified = set()
    fingerprints = {}
    traces = narrator.trace()[-TRACE_WINDOW:] if narrator is not None else []
    for trace in traces:
        if trace.get('run_key') != session.run_key:
            continue
        moment = moments.get(trace.get('episode_id'))
        if moment is None:
            continue
        if moment.id not in fingerprints:
            current = session.insights.fact_fingerprint(moment)
                                                                             
                                                                            
            source = (session.insights.fact_fingerprint(replace(moment, revision=moment.revision - 1))
                      if moment.source == 'foundry' and moment.ai_status == 'verified'
                      and moment.revision > 1 else current)
            fingerprints[moment.id] = (current, source)
        current, source = fingerprints[moment.id]
        if trace.get('fact_fingerprint') != source:
            continue
        applied = (moment.source == 'foundry' and moment.ai_status == 'verified'
                   and moment.complete and _approved_trace(trace, moment))
        if applied:
            verified.add(moment.id)
            proof = {'episode_id': moment.id, 'revision': moment.revision,
                     'fact_fingerprint': current, 'source_fact_fingerprint': source}
        state = ('verified' if applied else 'fallback' if trace.get('status') == 'fallback'
                 or moment.ai_status == 'fallback' else 'pending' if trace.get('status') == 'running'
                 or moment.ai_status == 'pending' else 'unconfirmed')
        latest = {'episode_id': moment.id, 'status': state, 'fact_fingerprint': current}
    counts['verified'] = len(verified)
    if narrator is None:
        status = 'local_factual'
    elif latest and latest['status'] == 'fallback':
        status = 'fallback'
    elif proof is not None:
        status = 'verified'
    elif counts['fallback'] and not counts['pending']:
        status = 'fallback'
    else:
        status = 'configured'
    return {'schema_version': SCHEMA_VERSION, 'run_key': session.run_key,
            'data': {'origin': 'synthetic', 'model_version': MODEL_VERSION,
                     'match_id': session.match.match_id, 'seed': session.match.settings.seed,
                     'scenario': session.match.settings.scenario},
            'narrative': {'provider': 'foundry' if narrator is not None else 'local',
                          'status': status, 'counts': counts, 'latest': latest, 'proof': proof,
                          'trace_window': TRACE_WINDOW,
                          'verified_count_scope': 'current_run_retained_traces'}}
