                                                                                 

from content import clock
from locales import event_display, story


SCHEMA_VERSION = 'eh-journey-1'


def build(session, episode=None, team=None, player=None, language='en'):
                                                                                
    insights = session.insights
    moments = list(insights.moments.values())
    if episode is not None and episode not in insights.moments:
        raise KeyError(episode)
    moment = insights.moments.get(episode) if episode else (moments[-1] if moments else None)
    index = [{'id': item.id, 'time': item.time, 'title': item.title,
              'revision': item.revision, 'complete': item.complete}
             for item in moments[-24:]]
    if moment and all(item['id'] != moment.id for item in index):
        index.insert(0, {'id': moment.id, 'time': moment.time, 'title': moment.title,
                         'revision': moment.revision, 'complete': moment.complete})
    result = {'schema_version': SCHEMA_VERSION, 'run_key': session.run_key,
              'clock': session.confirmed_frame['clock'], 'event_count': session.confirmed_count,
              'insight_revision': insights.revision, 'editorial_revision': session.desk.revision,
              'language': language, 'episodes': index, 'selected': None}
    if not moment:
        return result

    packet = insights.moment_data(moment)
    contribution = insights.player_contribution(moment, player) if player else None
    materials = session.content.render(packet, team, player, contribution, language, 'fan')
    desk = session.desk.state(moment, insights, language)
    on_air = (desk['status'] == 'selected' and session.desk.active_id == moment.id
              and session.desk.active_language == language)
    verified = packet['verified']
    ready = materials['ready']
    evidence = packet['evidence']
                                                                               
    picks = {0, len(evidence) - 1} if evidence else set()
    picks.update(i for i, event in enumerate(evidence) if event['kind'] in
                 ('shot', 'goal', 'save', 'shot_blocked', 'goal_kick'))
    picks.update(i for i, event in enumerate(evidence) if event['kind'] == 'pass_completed')
    positions = sorted(picks)
    if len(positions) > 12:
        positions = sorted(set(positions[:4] + positions[-8:]))
    elif len(evidence) > len(positions):
        positions = sorted(set(positions) | {
            round(i * (len(evidence) - 1) / 11) for i in range(12)
        })
        if len(positions) > 12:
            positions = positions[:6] + positions[-6:]
    sources = [{'id': evidence[i]['id'], 'time': evidence[i]['time'],
                'kind': evidence[i]['kind'], **event_display(evidence[i], language)}
               for i in positions]
    checks = [{'key': item['key'], 'passed': item['passed']} for item in packet['checks']]
    formats = materials['formats']
    narrative = story(packet, language, 'fan')
    result['selected'] = {
        'id': moment.id, 'revision': moment.revision, 'time': moment.time,
        'clock': clock(moment.time), 'kind': moment.kind, 'complete': moment.complete,
        'verified': verified, 'fact_fingerprint': packet['fact_fingerprint'],
        'evidence_ids': moment.evidence_ids[:], 'sources': sources,
        'sources_shown': len(sources), 'source_count': len(evidence), 'checks': checks,
        'story': narrative,
        'agent': {'status': moment.ai_status, 'source': moment.source,
                  'interpretation': moment.interpretation if moment.ai_status == 'verified' and language == 'en' else None},
        'metrics': formats['studio']['metrics'],
        'stream': {key: formats['stream'][key] for key in ('focus', 'personal', 'reason')},
        'studio': {'lead': formats['studio']['lead'],
                   'talking_points': formats['studio']['talking_points'],
                   'boundary': formats['studio']['boundary']},
        'broadcast': {'status': 'on_air' if on_air else desk['status'],
                      'text': desk['copy'] if on_air else None,
                      'receipt': desk['receipt'] if on_air else None,
                      'max_chars': formats['broadcast']['max_chars']},
        'stages': {'source': bool(evidence), 'metrics': verified,
                   'story': ready, 'reviewed': desk['status'] in ('checked', 'selected'),
                   'on_air': on_air},
    }
    return result
