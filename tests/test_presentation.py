                                                                                      
from copy import deepcopy
import json
import math
import unittest

from app import MatchSession
from delivery import MaterialStream, metric_selection
from display_adapter import DisplayAdapter
from periods import period_view
from simulation import GeneratorSettings
from telemetry import PresentationTiming


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live=MatchSession(GeneratorSettings(2),wall_clock=lambda:0)
        cls.live.pump(300)

    def test_fan_and_analyst_share_period_conclusion_facts_and_identity(self):
        fan=self.live.material_feed(audience='fan',team=0)['period']
        analyst=self.live.material_feed(audience='analyst',team=0)['period']
        for key in ('material_id','time','facts','fact_fingerprint','evidence_ids'):
            self.assertEqual(fan[key],analyst[key],key)
        self.assertEqual(fan['periods'][0]['headline'],analyst['periods'][0]['headline'])
        self.assertEqual(fan['metrics'],[])
        rows={r['key']:r for r in analyst['periods'][0]['rows']}
        self.assertTrue({'attacks','shots','possession','passes'}<=rows.keys())
        for key in ('attacks','shots','possession','passes'):
            self.assertEqual(rows[key]['current'],analyst['facts']['current'][key][0])
            self.assertEqual(rows[key]['delta'],analyst['facts']['current'][key][0]-analyst['facts']['previous'][key][0])

    def test_simultaneous_perspectives_keep_one_source_and_selected_metrics(self):
        packet=self.live.material_feed(audience='fan',team=0,metrics=['shots'])['period']
        pair=packet['perspectives'][0]
        self.assertEqual(pair['fact_fingerprint'],packet['fact_fingerprint'])
        self.assertEqual(pair['evidence_ids'],packet['evidence_ids'])
        self.assertEqual(pair['fan']['headline'],pair['analyst']['headline'])
        self.assertEqual(pair['fan']['conclusion'],pair['analyst']['conclusion'])
        self.assertEqual(pair['fan']['headline'],packet['periods'][0]['headline'])
        self.assertEqual({row['key'] for row in pair['analyst']['rows']},{'shots','close_shots'})
        self.assertNotIn('rows',pair['fan'])
        self.assertNotIn('facts',pair)

    def test_strong_fan_claim_requires_more_attacks_shots_and_close_shots(self):
        window=deepcopy(self.live.pipeline.context.periods[-1]);window['comparable']=True
        for bucket in ('current','previous'):
            for key in ('attacks','shots','close_shots'):window[bucket][key]=[0,0]
        window['current']['attacks'][0]=3;window['previous']['attacks'][0]=1
        window['current']['shots'][0]=2;window['previous']['shots'][0]=1
        self.assertEqual(period_view(window,0)['conclusion'],'attacking')
        window['current']['close_shots'][0]=1
        fan=period_view(window,0);analyst=period_view(window,0,audience='analyst')
        self.assertEqual(fan['conclusion'],'closer');self.assertIn('came closer to goal',fan['headline'])
        self.assertEqual(fan['headline'],analyst['headline'])
        window['current']['attacks'][0]=1
        self.assertNotEqual(period_view(window,0)['conclusion'],'closer')

    def test_completed_period_is_immutable_while_live_state_advances(self):
        live=MatchSession(GeneratorSettings(2),wall_clock=lambda:0);live.pump(120)
        first=live.material_feed()['period'];live.pump(125)
        self.assertEqual(live.material_feed()['period'],first)
        self.assertGreater(live.material_feed()['live_changes'][0]['facts']['current']['end'],first['time'])

    def test_attack_counts_reconstruct_independently_from_numbered_ball_actions(self):
        team=None;counted=False;attacks=[]
        for event in self.live.pipeline.events:
            kind,side=event['kind'],event['team']
            if kind in {'kickoff','restart_taken','interception','tackle','ball_recovered','save','shot_blocked','possession_change'}:
                if side!=team or kind in {'kickoff','restart_taken'}:counted=False
                team=side
            if kind in {'goal','goal_kick','corner','throw_in','second_half','full_time'}:team=None;counted=False
            if kind in {'pass_started','pass_completed','interception','tackle','ball_recovered','shot'}:
                if side!=team:team=side;counted=False
                attacking_right=(side==0)==(event['period']==1)
                local_x=event['ball'][0] if attacking_right else 105-event['ball'][0]
                if local_x>=70 and not counted:attacks.append(event);counted=True
        self.assertEqual([e['id'] for e in attacks],[a['event_id'] for a in self.live.pipeline.context.attacks])
        for window in self.live.pipeline.context.periods:
            for side in (0,1):
                expected=sum(e['team']==side and window['current']['start']<e['time']<=window['current']['end'] for e in attacks)
                self.assertEqual(window['current']['attacks'][side],expected)

    def test_favourite_team_gets_priority_without_changing_facts(self):
        first=self.live.material_feed(team=0)['cards'];second=self.live.material_feed(team=1)['cards']
        self.assertEqual(first[0]['team'],0);self.assertEqual(second[0]['team'],1)
        raw={r['material_id']:r for r in self.live.materials.latest.values()}
        for card in first+second:self.assertEqual(card['facts'],raw[card['material_id']]['facts'])

    def test_player_focus_priority_and_key_moment_involvement(self):
        player={'team':0,'number':10};data=self.live.material_feed(audience='player',player=player)
        self.assertEqual(data['focus']['player'],player)
        self.assertIn(player,data['cards'][0]['actors'])
        self.assertTrue(data['focus_moments'])
        for moment in data['focus_moments']:
            self.assertIn(player,self.live.materials.latest[moment['material_id']]['actors'])
        self.assertEqual(data['focus']['statistics']['tackles'],sum(e['kind']=='tackle' and e['actors'][-1]==player for e in self.live.pipeline.events))

    def test_player_movement_is_continuous_and_bounded_by_physical_speed(self):
        live=MatchSession(wall_clock=lambda:0);live.pump(1)
        first=live.material_feed(player={'team':0,'number':10})['focus']
        live.pump(2);second=live.material_feed(player={'team':0,'number':10})['focus']
        a,b=first['movement'],second['movement']
        self.assertGreater(b['distance_m'],a['distance_m'])
        self.assertLessEqual(b['distance_m']-a['distance_m'],6.3)
        self.assertLessEqual(b['speed_mps'],6.21)
        self.assertTrue(all(x['time']<=2 for x in b['path']))
        self.assertGreaterEqual(len(b['path']),3)

    def test_selected_metrics_remove_unwanted_screen_and_overlay_statistics(self):
        data=self.live.material_feed(audience='analyst',metrics=['shots'])
        self.assertEqual([r['key'] for r in data['statistics']],['shots'])
        self.assertTrue(all(r['key']=='shots' or r['key']=='close_shots' for r in data['period']['metrics']))
        empty=self.live.material_feed(metrics=[])
        self.assertEqual(empty['statistics'],[])
        self.assertNotIn('statistics',[o['layer'] for o in empty['overlays']])
        self.assertIn('statistics',empty['disabled_layers'])
        with self.assertRaises(ValueError):metric_selection(['secret'])
        with self.assertRaises(ValueError):metric_selection(['shots','shots'])

    def test_json_records_round_trip_with_time_meaning_and_source_evidence(self):
        data=json.loads(json.dumps(self.live.material_feed(limit=1000),ensure_ascii=False))
        for record in data['records']:
            self.assertTrue(record['event']);self.assertTrue(record['significance'])
            self.assertEqual(record['run_key'],self.live.run_key)
            self.assertEqual(record['match_id'],self.live.match.match_id)
            self.assertTrue(all(1<=n<=self.live.confirmed_count for n in record['evidence_ids']))
            self.assertLessEqual(record['time'],record['available_at'])
            self.assertEqual(len(record['fact_fingerprint']),64)

    def test_json_cursor_is_incremental_and_has_no_future_material(self):
        one=self.live.material_feed(limit=3);two=self.live.material_feed(after=one['cursor'],limit=3)
        self.assertTrue(one['has_more']);self.assertEqual(two['records'][0]['sequence'],one['cursor']+1)
        self.assertTrue(all(r['available_at']<=self.live.confirmed_frame['clock'] for r in two['records']))
        self.assertEqual(self.live.material_feed(after=two['latest_cursor'])['records'],[])

    def test_each_overlay_has_an_explicit_match_episode_schedule_and_payload(self):
        feed=self.live.material_feed(audience='analyst',metrics=['shots','passes'])
        for cue in feed['overlays']:
            self.assertTrue(cue['episode_id']);self.assertTrue(cue['material_id'])
            self.assertEqual(cue['timebase'],{'kind':'match_clock','unit':'seconds','origin':0})
            self.assertLessEqual(cue['show_at'],feed['playback_clock']);self.assertGreater(cue['remove_at'],feed['playback_clock'])
            self.assertEqual((cue['match_id'],cue['run_key']),(feed['match_id'],feed['run_key']))
            self.assertTrue({'event','significance','evidence'}<=cue['text'].keys())

    def test_adapter_shows_updates_removes_and_does_not_duplicate_commands(self):
        feed=self.live.material_feed();adapter=DisplayAdapter()
        commands=adapter.update(json.loads(json.dumps(feed)))
        self.assertIn('show',[c['action'] for c in commands])
        self.assertEqual(adapter.update(feed),[])
        future=max(c['remove_at'] for c in feed['overlays'])+.1
        commands=adapter.update(feed,future)
        self.assertTrue(all(c['action']=='remove' for c in commands));self.assertFalse(adapter.visible)

    def test_adapter_rejects_wrong_match_before_mutating_display(self):
        feed=self.live.material_feed();adapter=DisplayAdapter();adapter.update(feed)
        before=deepcopy(adapter.visible);bad=deepcopy(feed);bad['overlays'][0]['run_key']='other'
        with self.assertRaises(ValueError):adapter.update(bad)
        self.assertEqual(adapter.visible,before)

    def test_adapter_removes_layers_after_preference_change_and_seek(self):
        adapter=DisplayAdapter();adapter.update(self.live.material_feed())
        commands=adapter.update(self.live.material_feed(metrics=[]))
        self.assertIn('remove',[c['action'] for c in commands]);self.assertNotIn('statistics',adapter.visible)
        early=self.live.material_feed(at=1)
        adapter.update(early,1)
        self.assertTrue(all(c['show_at']<=1<c['remove_at'] for c in adapter.visible.values()))

    def test_replay_does_not_show_shot_outcome_before_it_was_known(self):
        shot=next(e for e in self.live.pipeline.events if e['kind']=='shot')
        moment=self.live.insights.moments[f"moment-{shot['id']}"]
        records=[r for r in self.live.materials.history if r['material_id']==moment.id]
        pending,resolved=records[0],records[-1]
        self.assertNotIn('outcome',pending['facts']);self.assertIn('outcome',resolved['facts'])
        self.assertGreater(resolved['available_at'],pending['available_at'])
        before=self.live.material_feed(at=shot['time'])
        relevant=[o for o in before['overlays'] if o['material_id']==moment.id]
        self.assertTrue(relevant);self.assertEqual(relevant[0]['revision'],pending['revision'])
        after=self.live.material_feed(at=resolved['available_at'])
        relevant=[o for o in after['overlays'] if o['material_id']==moment.id]
        adapter=DisplayAdapter();adapter.update(after)
        self.assertEqual(adapter.visible['narrative']['revision'],resolved['revision'])
        self.assertNotIn('statistics',[o['layer'] for o in before['overlays']])
        self.assertTrue(all(r['available_at']<=shot['time'] for r in before['records']+before['cards']))
        self.assertIsNone(before['focus']);self.assertEqual(before['live_changes'],[])

    def test_reading_feed_does_not_claim_actual_screen_display(self):
        live=MatchSession(wall_clock=lambda:0);live.pump(10)
        live.material_feed();live.snapshot();live.material_feed()
        self.assertEqual(live.timing.summary()['sample_count'],0)

    def test_display_latency_is_a_monotonic_upper_bound_including_ack_trip(self):
        clock=[1.0];timing=PresentationTiming(clock=lambda:clock[0])
        timing.produced(7,1.0,1.02)
        record={'material_id':'event-7','revision':1,'trigger_event_id':7}
        token=timing.offer(record);clock[0]=1.15
        payload={**{k:token[k] for k in ('token','material_id','revision','event_id')},'visible':True,'render_ms':32,'request_ms':44}
        self.assertTrue(timing.acknowledge(payload));self.assertFalse(timing.acknowledge(payload))
        summary=timing.summary();self.assertEqual(summary['sample_count'],1)
        self.assertAlmostEqual(summary['latest']['event_to_display_ack_ms'],150)
        self.assertAlmostEqual(summary['latest']['processing_ms'],20)
        self.assertEqual(summary['measurement'],'event_to_display_ack_upper_bound')

    def test_display_receipt_checks_source_visibility_timings_and_age(self):
        clock=[1.];timing=PresentationTiming(clock=lambda:clock[0]);timing.produced(1,1.,1.)
        token=timing.offer({'material_id':'event-1','revision':1,'trigger_event_id':1})
        valid={**{k:token[k] for k in ('token','material_id','revision','event_id')},'visible':True,'render_ms':20,'request_ms':30}
        for field,value in [('event_id',2),('visible',False),('render_ms',float('nan')),('request_ms',-1)]:
            with self.assertRaises(ValueError):timing.acknowledge({**valid,field:value})
        clock[0]=12;self.assertIsNone(timing.offer({'material_id':'event-1','revision':1,'trigger_event_id':1}))
        clock[0]=32
        with self.assertRaises(ValueError):timing.acknowledge(valid)

    def test_broadcast_channel_requires_review_and_uses_the_checked_copy(self):
        live=MatchSession(GeneratorSettings(2),wall_clock=lambda:0);live.pump(50)
        moment=next(iter(live.insights.moments.values()))
        self.assertIsNone(live.material_feed(channel='broadcast')['active_overlay'])
        copy='Editor-reviewed copy'
        live.desk.act(live.insights,moment.id,moment.revision,'review',copy)
        live.desk.act(live.insights,moment.id,moment.revision,'select',copy)
        feed=live.material_feed(channel='broadcast');cue=feed['active_overlay']
        self.assertEqual(cue['text']['significance'],copy);self.assertTrue(cue['editorial_receipt'])
        self.assertEqual(cue['show_at'],live.insights.clock)
        self.assertIsNone(live.material_feed(channel='broadcast',language='de')['active_overlay'])

    def test_all_languages_use_the_same_material_facts_and_no_invented_player_actions(self):
        player={'team':1,'number':11}
        for language in ('en','cs','de'):
            data=self.live.material_feed(language=language,player=player,limit=1000)
            for record in data['records']:
                canonical=self.live.materials.history[record['sequence']-1]
                self.assertEqual(record['facts'],canonical['facts'])
                self.assertEqual(record['fact_fingerprint'],canonical['fact_fingerprint'])
                if record['kind']=='moment' and player not in canonical['actors']:
                    self.assertFalse(any(word in record.get('personal','') for word in ('passes: 1','střely: 1','shots: 1')))


class CompactDeliveryTests(unittest.TestCase):
    def test_compact_poll_keeps_scene_frames_once_and_reuses_them(self):
        live=MatchSession(GeneratorSettings(2),wall_clock=lambda:0);live.pump(50)
        full=live.snapshot();compact=live.snapshot(compact=True)
        exp=compact['experience'];self.assertTrue(all('frame' in e for e in exp['selected']['evidence']))
        self.assertTrue(all('frame' not in e for e in compact['events']))
        live.pump(50.1)
        update=live.snapshot(run_id=live.run_id,after=compact['event_count'],compact=True,scene_revision=exp['scene_revision'])
        self.assertTrue(update['experience']['scene_unchanged'])
        self.assertIsNone(update['experience']['selected'])
        self.assertTrue(all('frame' in e for e in full['events']))
        self.assertEqual(live.pipeline.events[0],full['events'][0])
        self.assertLess(len(json.dumps(update)),len(json.dumps(full)))

    def test_replay_never_reuses_scene_from_a_previous_run(self):
        live=MatchSession(GeneratorSettings(2),wall_clock=lambda:0);live.pump(50)
        first=live.snapshot(compact=True);live.restart();live.pump(50)
        second=live.snapshot(run_id=live.run_id,compact=True,scene_revision=first['experience']['scene_revision'])
        self.assertFalse(second['experience']['scene_unchanged']);self.assertIsNotNone(second['experience']['selected'])

    def test_personalized_episode_cards_put_priority_before_chronology(self):
        live=MatchSession(GeneratorSettings(2),wall_clock=lambda:0);live.pump(300)
        player={'team':0,'number':10};cards=live.insights.view(0,player)['moments']
        rank=lambda card:(int(player in card['actors'])*2+int(card['team']==0),card['time'])
        self.assertEqual(cards,sorted(cards,key=rank,reverse=True))
        self.assertTrue(any(card['team']==1 for card in cards))

if __name__=='__main__':unittest.main()
