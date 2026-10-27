                                                                           
from copy import deepcopy
from pathlib import Path
import unittest

from rhythm_lens import build
from demonstration_store import DemoReader


def window():
    before={'start':0,'end':60,'losses':[1,2],'passes':[7,8],
            'shots':[1,0],'pressure_seconds':[10.,20.],'evidence_ids':[1,2,3]}
    now={'start':60,'end':120,'losses':[3,2],'passes':[10,7],
         'shots':[1,2],'pressure_seconds':[20.,5.],'evidence_ids':[4,5,6]}
    return {'previous':before,'current':now,'comparable':True}


class RhythmLensTests(unittest.TestCase):
    def test_observed_changes_keep_pressure_separate_from_event_counts(self):
        lens=build(window());rows={r['key']:r for r in lens['rows']}
        self.assertEqual(rows['turnovers']['current'],5)
        self.assertEqual(rows['pass_starts']['current'],17)
        self.assertEqual(rows['pressure_blue']['current'],20)
        self.assertEqual(rows['pressure_red']['current'],5)
        self.assertEqual(rows['pressure_blue']['unit'],'seconds')
        self.assertEqual(rows['shots']['delta'],2)
        self.assertNotIn('control_score',lens)
        self.assertNotIn('ai_interpretation',lens)

    def test_partial_comparison_is_not_presented_as_a_complete_minute(self):
        w=window();w['comparable']=False
        self.assertEqual(build(w)['status'],'collecting')
        self.assertTrue(all(r['previous'] is None and r['delta'] is None for r in build(w)['rows']))
        w['comparable']=True;w['previous']['start']=1
        with self.assertRaises(ValueError):build(w)

    def test_source_fingerprint_covers_previous_context_without_mutation(self):
        w=window();old=deepcopy(w);first=build(w)
        self.assertEqual(w,old)
        w['previous']['pressure_seconds'][1]=21
        self.assertNotEqual(first['source_fingerprint'],build(w)['source_fingerprint'])
        w=deepcopy(old);w['previous']['evidence_ids'].append(7)
        self.assertNotEqual(first['source_fingerprint'],build(w)['source_fingerprint'])

    def test_bounded_examples_retain_full_source_count_and_digest(self):
        w=window();w['current']['evidence_ids']=list(range(4,204))
        lens=build(w)
        self.assertEqual(lens['source_count'],203)
        self.assertEqual(len(lens['source_event_ids']),12)
        self.assertEqual(lens['source_event_ids'][-1],203)

    def test_invalid_proximity_time_counts_sources_and_overlapping_windows_fail(self):
        for field,value in (('pressure_seconds',[61,0]),('losses',[float('nan'),0]),
                            ('passes',[1.5,0]),('evidence_ids',[True])):
            w=window();w['current'][field]=value
            with self.assertRaises(ValueError):build(w)
        w=window();w['previous']['end']=61
        with self.assertRaises(ValueError):build(w)

    def test_archive_uses_only_periods_available_at_the_replay_clock(self):
        path=Path(__file__).resolve().parents[1]/'data/full-match.sqlite3'
        stat=path.stat();reader=DemoReader(path)
        early=reader.state(59.95)
        self.assertIsNone(early['rhythm'])
        self.assertEqual(reader.state(119.95)['rhythm']['status'],'collecting')
        later=reader.state(120)['rhythm']
        self.assertEqual(later['status'],'ready')
        self.assertEqual(later['windows']['current'],{'start':60,'end':120})
        self.assertEqual(later['windows']['previous'],{'start':0,'end':60})
        self.assertLessEqual(reader.state(179.95)['rhythm']['clock'],179.95)
        self.assertEqual(path.stat().st_mtime_ns,stat.st_mtime_ns)


if __name__=='__main__':unittest.main()
