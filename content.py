from global_localization import translate_tree
"""One evidence packet, distinct audience formats, replaceable extension points.

No generator decisions or network calls belong here. Metrics consume the same
versioned source packet as the story. English, German and Czech are shipped;
a new language must supply complete story, caption and personal-text renderers.
"""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Callable

from simulation import TEAMS
import locales


CAPTION_LIMIT = 140
SCHEMA_VERSION = 'eh-material-1'


def clock(seconds):
    return f'{int(seconds // 60):02}:{int(seconds % 60):02}'


def english_caption(packet):
    return locales.caption(packet, 'en')


def caption_text(moment, language="en", packet=None):
                                                                               
    packet = packet or {'facts': moment.facts, 'kind': moment.kind, 'team': moment.team}
    text = '\n'.join(english_caption(packet) if language=='en' else locales.caption(packet,language))
    if len(text) > CAPTION_LIMIT:
        raise ValueError('Generated caption exceeds its format contract')
    return text


def english_personal(packet, team, player, contribution):
    if player is not None:
        focus = locales.named(player)
        if contribution and contribution['evidence_ids']:
            values = contribution['counts']
            roles = [('passes_made', 'completed passes'), ('passes_received', 'receipts'),
                     ('shots', 'shots'), ('saves', 'saves'), ('regains', 'recoveries')]
            detail = ', '.join(f'{label}: {values[key]}' for key, label in roles if values[key])
            if detail:
                return focus, f'Contribution to the episode: {detail}.', 'Your player was involved'
            return (focus, 'The player appears in the episode sources, but has no recorded ball actions in this sequence.', 'Mentioned in sources')
        return focus, 'The selected player has no recorded involvement in this episode.', 'Match context'
    if team is not None:
        return TEAMS[team], ('An episode involving your team.' if packet['team'] == team else
                            'An opponent episode: context for your team.'), 'Your team is selected'
    return 'Whole match', 'A general overview without team or player preferences.', 'General perspective'


@dataclass(frozen=True)
class LanguagePack:
    code: str
    labels: dict
    metric_labels: dict
    story: Callable
    caption: Callable
    personal: Callable


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    unit: str
    calculate: Callable


class Registry:
                                                                                    

    def __init__(self):
        self.items = {}

    def register(self, key, value):
        if not isinstance(key, str) or not key or key in self.items:
            raise ValueError('Extension key is empty or already registered')
        self.items[key] = value

    def get(self, key):
        if key not in self.items:
            raise ValueError(f'Unknown extension: {key}')
        return self.items[key]


def pass_metric(packet):
    if packet['kind'] == 'trend':
        return None
    ids = [event['id'] for event in packet['evidence'] if event['kind'] == 'pass_completed']
    return {'value': len(ids), 'evidence_ids': ids}


def duration_metric(packet):
    evidence = packet['evidence']
    shot = next((event for event in evidence if event['kind'] == 'shot'), None)
    if shot is None or not evidence:
        return None
    return {'value': round(shot['time'] - evidence[0]['time'], 1),
            'evidence_ids': [evidence[0]['id'], shot['id']]}


def shots_metric(packet):
    window = packet['facts']['window']
    return {'value': window['shots'][:], 'evidence_ids': window['evidence_ids'][:],
            'interval': [window['start'], window['end']]}


@dataclass(frozen=True)
class DeliveryContext:
    packet: dict
    language: LanguagePack
    story: dict
    metrics: list
    focus: str
    personal: str
    reason: str
    analyst_story: dict


def studio_format(context):
    packet, story = context.packet, context.analyst_story
    return {'title': story['title'], 'lead': story['what'],
            'talking_points': [story['why'], story['change']],
            'metrics': deepcopy(context.metrics), 'participants': deepcopy(packet['actors']),
            'attack_path': deepcopy(packet['attack_path']), 'sources': deepcopy(packet['evidence']),
            'boundary': context.language.labels['boundary']}


def broadcast_format(context):
    lines = context.language.caption(deepcopy(context.packet))
    if not isinstance(lines, list) or not 1 <= len(lines) <= 2 or any(
            not isinstance(line, str) or not line.strip() or '\n' in line for line in lines):
        raise ValueError('A caption needs one or two non-empty lines')
    text = '\n'.join(lines)
    if len(text) > CAPTION_LIMIT:
        raise ValueError('Caption exceeds the short format limit')
    return {'lines': lines, 'text': text, 'max_chars': CAPTION_LIMIT,
            'editorial_required': True}


def stream_format(context):
    return {'title': context.story['title'], 'summary': context.story['what'],
            'meaning': context.story['why'], 'focus': context.focus,
            'personal': context.personal, 'reason': context.reason,
            'metrics': deepcopy(context.metrics)}


class ContentService:
    def __init__(self):
        self.metrics, self.languages, self.formats = Registry(), Registry(), Registry()
        self.languages.register('en', LanguagePack(
            'en', {'boundary': 'Observed events and calculations. The tactical cause is not established.'},
            {'attack_passes': 'Completed passes in attack', 'to_shot_seconds': 'From the start of the sequence to the shot',
             'window_shots': 'Shots in interval'},
            lambda packet: {key: packet[key] for key in ('title', 'what', 'why', 'change')},
            english_caption, english_personal))
        for code in ('de','cs'):
            self.languages.register(code, LanguagePack(code,
                {'boundary': 'Beobachtete Fakten; die taktische Ursache ist nicht belegt.' if code=='de' else 'Pozorovaná fakta; taktická příčina není určena.'},
                dict(zip(('attack_passes','to_shot_seconds','window_shots'),
                         ('Erfolgreiche Pässe im Angriff','Von Beginn der Folge bis zum Schuss','Schüsse im Zeitraum') if code=='de' else
                         ('Přesné přihrávky v útoku','Od začátku série ke střele','Střely v úseku'))),
                lambda p,c=code: locales.story(p,c), lambda p,c=code: locales.caption(p,c),
                lambda p,t,a,v,c=code: locales.personal(p,t,a,v,c)))
        for code in ('fr','it','es','pt'):
            english=self.languages.get('en')
            self.languages.register(code, LanguagePack(code,
                translate_tree(english.labels,code), translate_tree(english.metric_labels,code),
                lambda p,c=code: locales.story(p,c), lambda p,c=code: locales.caption(p,c),
                lambda p,t,a,v,c=code: locales.personal(p,t,a,v,c)))
        for metric in (MetricDefinition('attack_passes', 'count', pass_metric),
                       MetricDefinition('to_shot_seconds', 'seconds', duration_metric),
                       MetricDefinition('window_shots', 'score_pair', shots_metric)):
            self.metrics.register(metric.key, metric)
        for key, renderer in (('studio', studio_format), ('broadcast', broadcast_format),
                              ('stream', stream_format)):
            self.formats.register(key, renderer)
        self._overview_key = None
        self._overview = None

    def render(self, packet, team=None, player=None, contribution=None, language='en', audience='analyst'):
                                                                             
                                                                         
        packet = deepcopy(packet)
        locale = self.languages.get(language)
        story = locales.story(packet, language, 'fan') if language in locales.LANGUAGES else locale.story(deepcopy(packet))
        analyst_story = locales.story(packet, language, 'analyst') if language in locales.LANGUAGES else deepcopy(story)
        if language in locales.LANGUAGES:
            packet['attack_path'] = locales.localized_path(packet, language)
            for event in packet['evidence']:
                if 'source_title' in event: event['title'] = event.pop('source_title')
                if 'source_text' in event: event['text'] = event.pop('source_text')
        if set(story) != {'title', 'what', 'why', 'change'} or any(
                not isinstance(value, str) or not value.strip() for value in story.values()):
            raise ValueError('Language pack must render the complete story')
        metrics = []
        for key, definition in self.metrics.items.items():
            calculated = definition.calculate(deepcopy(packet))
            if calculated is not None:
                if key not in locale.metric_labels:
                    raise ValueError(f'Missing metric label in {language}: {key}')
                metrics.append({'key': key, 'label': locale.metric_labels[key],
                                'unit': definition.unit, **calculated})
        focus, personal, reason = locale.personal(deepcopy(packet), team, player, deepcopy(contribution))
        context = DeliveryContext(packet, locale, story, metrics, focus, personal, reason, analyst_story)
        return {'schema_version': SCHEMA_VERSION, 'moment_id': packet['id'],
                'revision': packet['revision'], 'fact_fingerprint': packet['fact_fingerprint'],
                'time': packet['time'], 'language': language,
                'ready': bool(packet['complete'] and packet['verified']),
                'evidence_ids': packet['evidence_ids'][:], 'facts': deepcopy(packet['facts']),
                'formats': {key: renderer(deepcopy(context)) for key, renderer in self.formats.items.items()}}

    def overview(self, insights):
                                                                          
        key = (id(insights), tuple((moment.id, moment.revision,
                                   insights.fact_fingerprint(moment)) for moment in insights.moments.values()))
        if key != self._overview_key:
            entries = []
            for moment in sorted(insights.moments.values(), key=lambda item: item.time):
                entries.append({'id': moment.id, 'revision': moment.revision, 'time': moment.time,
                                'title': moment.title, 'what': moment.what, 'why': moment.why,
                                'change': moment.change, 'complete': moment.complete,
                                'verified': insights.verified(moment),
                                'evidence_ids': moment.evidence_ids[:]})
            revision = hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
            self._overview_key = key
            self._overview = {'revision': revision, 'entries': entries, 'total': len(entries)}
        return deepcopy(self._overview)
