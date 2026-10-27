                                                                                 
from copy import deepcopy
import unittest
from unittest.mock import patch

from reproducibility_lab import ReplayLab, ReplayProof, first_difference, verify
from simulation import GeneratorSettings


class ReplayLabTests(unittest.TestCase):
    def finish(self,run,now=400):
        for _ in range(10000):
            run.pump(now)
            if run.complete or run.error or run.first_mismatch:return run.snapshot()
        self.fail('Verification did not finish within its tick budget')

    def test_gradual_arrival_and_reads_never_advance_clock(self):
        run=ReplayProof(seconds=30,speed=1)
        run.pump(.39)
        data=run.snapshot()
        self.assertEqual(data['stream']['clock'],0)
        self.assertEqual(data['stream']['event_count'],1)
        self.assertEqual(data['reference']['clock'],.35)
        self.assertEqual(run.snapshot(),data)
        run.pump(2)
        for lane in ('reference','stream'):
            self.assertTrue(all(e['time']<=run.snapshot()[lane]['clock'] for e in run.snapshot()[lane]['recent_events']))
        self.assertGreater(sum(run.stream.pipeline.metrics.attempts),0)
        self.assertFalse(run.complete)

    def test_scheduler_jitter_and_budget_preserve_exact_events(self):
        regular=ReplayProof(GeneratorSettings(17),seconds=30)
        for tick in range(1,601):regular.pump(tick*.05)
        regular.pump(30.4)
        uneven=ReplayProof(GeneratorSettings(17),seconds=30)
        uneven.pump(90)
        self.assertEqual(uneven.reference.match.tick,40)
        self.assertEqual(uneven.stream.match.tick,40)
        self.assertEqual(self.finish(uneven)['status'],'passed')
        self.assertEqual(regular.reference.match.events,uneven.stream.match.events)
        self.assertEqual(regular.stream.summary()['event_sha256'],uneven.stream.summary()['event_sha256'])
        self.assertEqual(uneven.compared_events,len(uneven.reference.match.events))
        self.assertEqual(uneven.snapshot()['stream']['event_sha256'],uneven.stream.match.event_digest.hexdigest())

    def test_repeat_matches_previous_and_different_seed_does_not_claim_repeat(self):
        clock=[0.];lab=ReplayLab(clock=lambda:clock[0]);lab.start(42,30,8)
        clock[0]=10
        for _ in range(15):lab.pump()
        first=lab.receipt();lab.start(42,30,1)
        clock[0]=50
        for _ in range(15):lab.pump()
        second=lab.receipt()
        self.assertNotEqual(first['run_key'],second['run_key'])
        self.assertTrue(second['previous_run_match'])
        self.assertEqual(first['stream']['event_sha256'],second['stream']['event_sha256'])
        lab.start(43,30,8);clock[0]=60
        for _ in range(15):lab.pump()
        third=lab.receipt()
        self.assertIsNone(third['previous_run_match'])
        self.assertNotEqual(second['stream']['event_sha256'],third['stream']['event_sha256'])

    def test_changed_received_event_stops_at_first_affected_tick(self):
        run=ReplayProof(seconds=30)
        original=run.stream.match.advance
        def corrupted():
            count=len(run.stream.match.events);original()
            if len(run.stream.match.events)>count:run.stream.match.events[-1]['text']='Altered delivery text'
        with patch.object(run.stream.match,'advance',corrupted):result=self.finish(run)
        self.assertEqual(result['status'],'failed')
        self.assertIsNotNone(result['first_mismatch'])
        self.assertIn('text',result['first_mismatch']['difference']['field'])
        tick=run.stream.match.tick;run.pump(999)
        self.assertEqual(run.stream.match.tick,tick)
        with self.assertRaises(ValueError):run.receipt()

    def test_frame_and_projection_are_compared_even_without_events(self):
        run=ReplayProof(seconds=30)
        original=run.stream.witness
        def corrupted():
            data=original()
            if data['tick']>0:data['metrics_sha256']='changed'
            return data
        with patch.object(run.stream,'witness',corrupted):result=self.finish(run)
        self.assertEqual(result['first_mismatch']['tick'],1)
        self.assertEqual(result['first_mismatch']['difference']['field'],'$.metrics_sha256')

    def test_stop_and_single_run_limit(self):
        lab=ReplayLab(clock=lambda:0);s=lab.start(42,30,8)
        with self.assertRaises(RuntimeError):lab.start()
        with self.assertRaises(RuntimeError):lab.cancel('other')
        lab.cancel(s['run_key']);lab.pump()
        self.assertEqual(lab.snapshot()['status'],'stopped')
        with self.assertRaises(ValueError):lab.receipt()
        lab.start(42,30,8)
        self.assertEqual(lab.snapshot()['status'],'running')

    def test_malformed_settings_cannot_replace_current_run(self):
        lab=ReplayLab(clock=lambda:0)
        for seed,seconds,speed in [(True,30,8),(-1,30,8),(42,5400,8),(42,30,64),(42,30,True)]:
            with self.assertRaises(ValueError):lab.start(seed,seconds,speed)
            self.assertEqual(lab.snapshot()['status'],'idle')
        with self.assertRaises(ValueError):ReplayProof(seconds=0)
        with self.assertRaises(ValueError):ReplayProof().pump(float('nan'))
        with self.assertRaises(ValueError):ReplayProof().pump(1,max_ticks=0)

    def test_receipt_has_settings_source_identity_and_checkpoints(self):
        result=verify(42,120)
        self.assertEqual(result['status'],'passed')
        self.assertEqual([c['tick'] for c in result['checkpoints']],[0,1200,2400])
        self.assertEqual(result['identity']['settings']['seed'],42)
        self.assertEqual(len(result['identity']['implementation']['sha256']),64)
        self.assertGreater(result['stream']['timed_batches'],0)
        self.assertGreater(result['stream']['analysis_p95_ms'],0)
        self.assertEqual(first_difference({'a':[1,2]},{'a':[1,3]})['field'],'$.a[1]')


if __name__=='__main__':unittest.main()
