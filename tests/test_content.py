                                                                                  

from copy import deepcopy
import unittest

from app import MatchSession
from content import CAPTION_LIMIT, ContentService, LanguagePack, MetricDefinition
from editorial import EditorialDesk
from simulation import GeneratorSettings


def episode():
    live = MatchSession(GeneratorSettings(2), wall_clock=lambda: 0)
    live.pump(50)
    moment = next(iter(live.insights.moments.values()))
    return live, moment, live.insights.moment_data(moment)


class ContentTests(unittest.TestCase):
    def test_one_episode_has_three_distinct_formats_and_one_set_of_facts(self):
        live, moment, packet = episode()
        contribution = live.insights.player_contribution(moment, {'team': 0, 'number': 10})
        result = live.content.render(packet, 0, {'team': 0, 'number': 10}, contribution)
        studio, caption, stream = (result['formats'][key] for key in ('studio', 'broadcast', 'stream'))
        self.assertEqual(result['facts'], moment.facts)
        self.assertEqual(result['evidence_ids'], moment.evidence_ids)
        self.assertEqual(result['fact_fingerprint'], packet['fact_fingerprint'])
        self.assertTrue(result['ready'])
        self.assertEqual(studio['sources'], packet['evidence'])
        self.assertEqual(studio['metrics'], stream['metrics'])
        self.assertEqual(studio['metrics'][0]['value'], 13)
        self.assertGreater(len(studio['lead'] + ' '.join(studio['talking_points'])), len(caption['text']))
        self.assertIn('shot saved', caption['text'].lower())
        self.assertIn('completed passes: 4', stream['personal'])
        self.assertIn('shots: 1', stream['personal'])

    def test_absent_player_is_never_given_invented_contribution(self):
        live, moment, packet = episode()
        player = {'team': 1, 'number': 11}
        contribution = live.insights.player_contribution(moment, player)
        self.assertEqual(contribution['evidence_ids'], [])
        material = live.content.render(packet, player=player, contribution=contribution)['formats']['stream']
        self.assertIn('no recorded involvement', material['personal'])
        self.assertEqual(material['reason'], 'Match context')

    def test_source_mention_without_counted_action_has_a_meaningful_card(self):
        live, _, _ = episode()
        live.pump(190)
        moment = list(live.insights.moments.values())[-1]
        player = {'team': 0, 'number': 10}
        contribution = live.insights.player_contribution(moment, player)
        self.assertTrue(contribution['evidence_ids'])
        self.assertEqual(sum(contribution['counts'].values()), 0)
        stream = live.content.render(live.insights.moment_data(moment), player=player,
                                     contribution=contribution)['formats']['stream']
        self.assertIn('no recorded ball actions', stream['personal'])
        self.assertNotIn('— .', stream['personal'])
        self.assertEqual(stream['reason'], 'Mentioned in sources')

    def test_overview_appears_live_and_resolves_in_place_without_future_facts(self):
        live = MatchSession(GeneratorSettings(2), wall_clock=lambda: 0)
        self.assertEqual(live.snapshot()['overview']['entries'], [])
        live.pump(48.9)
        pending = live.snapshot()['overview']['entries']
        self.assertEqual(len(pending), 1)
        self.assertFalse(pending[0]['complete'])
        live.pump(50)
        completed = live.snapshot()['overview']['entries']
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]['id'], pending[0]['id'])
        self.assertTrue(completed[0]['complete'])
        self.assertGreater(completed[0]['revision'], pending[0]['revision'])
        for key in completed[0]['evidence_ids']:
            self.assertLessEqual(live.insights.events[key]['time'], live.match.clock)

    def test_overview_is_chronological_and_does_not_hide_opponents(self):
        live, _, _ = episode()
        live.pump(300)
        normal = live.snapshot()
        focused = live.snapshot(team=1, player={'team': 1, 'number': 10})
        entries = normal['overview']['entries']
        self.assertGreater(len(entries), 1)
        self.assertEqual(entries, focused['overview']['entries'])
        self.assertEqual([entry['time'] for entry in entries], sorted(entry['time'] for entry in entries))
        self.assertEqual(len({entry['id'] for entry in entries}), len(entries))

    def test_periodic_window_updates_do_not_resend_unchanged_overview(self):
        live, _, _ = episode()
        first = live.snapshot()
        live.pump(51)
        next_frame = live.snapshot(run_id=live.run_id, overview_revision=first['overview_revision'])
        self.assertNotIn('overview', next_frame)
        self.assertEqual(next_frame['overview_revision'], first['overview_revision'])

    def test_metric_can_be_registered_without_changing_pipeline_or_formats(self):
        live, _, packet = episode()
        before = deepcopy(live.match.events)
        live.content.metrics.register('source_count', MetricDefinition(
            'source_count', 'count', lambda data: {'value': len(data['evidence']), 'evidence_ids': data['evidence_ids'][:]}))
        live.content.languages.get('en').metric_labels['source_count'] = 'Source events'
        rendered = live.content.render(packet)['formats']
        for channel in ('studio', 'stream'):
            metric = next(row for row in rendered[channel]['metrics'] if row['key'] == 'source_count')
            self.assertEqual(metric['value'], len(packet['evidence']))
        self.assertEqual(live.match.events, before)

    def test_new_language_requires_complete_renderers_and_preserves_facts(self):
        live, _, packet = episode()
        original = live.content.languages.get('en')
        language = LanguagePack('test', {'boundary': 'Observed facts only'},
            {key: 'Test '+key for key in original.metric_labels},
            lambda data: {'title': 'Test title', 'what': 'Test event', 'why': 'Test importance', 'change': 'Test change'},
            lambda data: ['Test caption', f"Passes: {data['facts']['passes_in_attack']}"],
            lambda *args: ('Test focus', 'Test contribution', 'Test reason'))
        live.content.languages.register('test', language)
        result = live.content.render(packet, language='test')
        self.assertEqual(result['language'], 'test')
        self.assertEqual(result['facts'], packet['facts'])
        self.assertEqual(result['evidence_ids'], packet['evidence_ids'])
        self.assertEqual(result['formats']['studio']['lead'], 'Test event')
        self.assertIn('13', result['formats']['broadcast']['text'])
        with self.assertRaises(ValueError): live.content.render(packet, language='unavailable')

    def test_display_adapter_cannot_mutate_other_formats_or_sources(self):
        live, _, packet = episode()
        before = deepcopy(packet)
        def extra_format(context):
            context.packet['facts']['passes_in_attack'] = 999
            return {'text': context.story['what'], 'id': context.packet['id']}
        live.content.formats.register('presenter_notes', extra_format)
        rendered = live.content.render(packet)
        self.assertIn('presenter_notes', rendered['formats'])
        self.assertEqual(rendered['facts']['passes_in_attack'], 13)
        self.assertIn('13', rendered['formats']['broadcast']['text'])
        self.assertEqual(packet, before)

    def test_short_caption_contract_applies_to_human_review_too(self):
        live, moment, _ = episode()
        desk = EditorialDesk()
        for text in ('x' * (CAPTION_LIMIT + 1), 'First\nSecond\nThird'):
            with self.assertRaises(ValueError): desk.act(live.insights, moment.id, moment.revision, 'review', text)
        self.assertEqual(desk.records, {})
        caption = desk.state(moment, live.insights)['copy']
        self.assertLessEqual(len(caption), CAPTION_LIMIT)
        desk.act(live.insights, moment.id, moment.revision, 'review', caption)
        desk.act(live.insights, moment.id, moment.revision, 'select', caption)
        self.assertEqual(desk.snapshot(live.insights)['active']['editorial']['copy'], caption)

    def test_editor_and_fan_receive_the_same_source_version(self):
        live, _, _ = episode()
        state = live.snapshot(team=0, player={'team': 0, 'number': 10}, view='editor')
        fan = state['insights']['moments'][0]['materials']
        editor = state['editorial']['items'][0]['materials']
        self.assertEqual(fan, editor)

    def test_registered_names_cannot_silently_replace_existing_extensions(self):
        service = ContentService()
        with self.assertRaises(ValueError): service.formats.register('studio', lambda data: {})
        with self.assertRaises(ValueError): service.languages.register('', None)

    def test_all_actual_match_captions_fit_and_have_only_received_sources(self):
        live = MatchSession(GeneratorSettings(42), wall_clock=lambda: 0)
        live.pump(5400)
        digest = live.match.event_digest.hexdigest()
        kinds = set()
        for moment in live.insights.moments.values():
            packet = live.insights.moment_data(moment)
            material = live.content.render(packet)
            caption = material['formats']['broadcast']
            self.assertLessEqual(len(caption['text']), CAPTION_LIMIT)
            self.assertLessEqual(len(caption['lines']), 2)
            self.assertEqual(material['fact_fingerprint'], live.insights.fact_fingerprint(moment))
            self.assertTrue(all(live.insights.events[key]['time'] <= live.match.clock for key in material['evidence_ids']))
            kinds.add(moment.kind)
        self.assertIn('goal', kinds)
        self.assertIn('chance', kinds)
        self.assertEqual(digest, live.match.event_digest.hexdigest())


if __name__ == '__main__':
    unittest.main()
