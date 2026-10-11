"""Targeted RC tests for topology, ownership, fidelity and release separation."""
import copy
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from benchmark import curve_geometry_metrics
from branch_tracking import joint_track_candidate_graph
from numerical_qa import topology_reverse_jumps
from release_check import update_test_count_text
from trace_processing import path_centerline


def node(cid, x, y, order, component, shared=False):
    return dict(candidate_id=cid, x=x, y=y, path_order=order,
                component_id=component, marker_identity=component,
                confirmed_shared=shared)


class TraceTopologyTests(unittest.TestCase):
    def test_a_near_vertical_multi_valued_x_not_collapsed(self):
        points=[node('a',0,.1,1,'f'),node('b',.0001,.3,2,'f'),node('c',0,.5,3,'f')]
        self.assertEqual(len(path_centerline(points,(0,1,0,1),.01)[0]),3)

    def test_b_arc_length_path_order_is_preserved(self):
        points=[node('c',0,.5,3,'f'),node('a',0,.1,1,'f'),node('b',.0001,.3,2,'f')]
        center,meta=path_centerline(points,(0,1,0,1),.01)
        self.assertEqual([p[0]['candidate_id'] for p in center],['a','b','c'])
        self.assertTrue(meta['near_vertical'])

    def test_k_near_vertical_reverse_jump_is_topology_artifact(self):
        rows=[dict(temperature_celsius=0,uwc_preferred_value=.1,path_position=1,near_vertical=True),
              dict(temperature_celsius=.0001,uwc_preferred_value=.4,path_position=2,near_vertical=True),
              dict(temperature_celsius=0,uwc_preferred_value=.2,path_position=3,near_vertical=True)]
        result=topology_reverse_jumps(rows,.003,.01)
        self.assertEqual(result['severe_count'],0)
        self.assertEqual(result['topology_artifact_count'],1)

    def test_l_genuine_reverse_jump_is_captured(self):
        rows=[dict(temperature_celsius=-2,uwc_preferred_value=.2,path_position=1,near_vertical=False),
              dict(temperature_celsius=-1,uwc_preferred_value=.15,path_position=2,near_vertical=False)]
        self.assertEqual(topology_reverse_jumps(rows,.003,.01)['severe_count'],1)


class JointOwnershipTests(unittest.TestCase):
    def specs(self):
        return {'freezing':{'start_id':'f0','end_id':'f2','seed_component':'f'},
                'thawing':{'start_id':'t0','end_id':'t2','seed_component':'t'}}

    def test_c_nonshared_candidate_has_one_owner(self):
        candidates=[node('f0',0,0,0,'f'),node('x',1,.1,1,'f'),node('f2',2,0,2,'f'),
                    node('t0',0,1,0,'t'),node('y',1,.9,1,'t'),node('t2',2,1,2,'t')]
        result=joint_track_candidate_graph(candidates,self.specs(),1.5)
        owners=result['candidate_assignments']
        self.assertTrue(all(len(v)==1 for k,v in owners.items() if k not in result['confirmed_shared_ids']))

    def test_d_confirmed_true_overlap_is_allowed(self):
        candidates=[node('f0',0,0,0,'f'),node('s',1,.5,1,'s',True),node('f2',2,0,2,'f'),
                    node('t0',0,1,0,'t'),node('t2',2,1,2,'t')]
        result=joint_track_candidate_graph(candidates,self.specs(),1.5)
        self.assertEqual(result['candidate_assignments']['s'],['freezing','thawing'])
        self.assertEqual(result['unresolved_candidate_ids'],[])

    def test_e_unconfirmed_shared_candidate_is_unresolved(self):
        candidates=[node('f0',0,0,0,'f'),node('s',1,.5,1,'s'),node('f2',2,0,2,'f'),
                    node('t0',0,1,0,'t'),node('t2',2,1,2,'t')]
        result=joint_track_candidate_graph(candidates,self.specs(),1.5)
        self.assertIn('s',result['unresolved_candidate_ids'])

    def test_f_joint_tracking_does_not_let_branches_steal_candidate(self):
        candidates=[node('f0',0,0,0,'f'),node('f1',1,.45,1,'f'),node('f2',2,0,2,'f'),
                    node('t0',0,1,0,'t'),node('t1',1,.55,1,'t'),node('t2',2,1,2,'t')]
        result=joint_track_candidate_graph(candidates,self.specs(),1.2)
        self.assertNotEqual(set(result['paths']['freezing']),set(result['paths']['thawing']))

    def test_g_true_crossing_is_not_identity_switch(self):
        candidates=[node('f0',0,0,0,'f'),node('f1',1,.5,1,'f'),node('f2',2,1,2,'f'),
                    node('t0',0,1,0,'t'),node('t1',1,.5,1,'t'),node('t2',2,0,2,'t')]
        result=joint_track_candidate_graph(candidates,self.specs(),1.2)
        self.assertEqual(result['true_crossing_count'],1)
        self.assertEqual(result['identity_switch_count'],0)

    def test_h_component_continuity_prevents_false_switch(self):
        candidates=[node('f0',0,0,0,'f'),node('f1',1,.6,1,'f'),node('f2',2,1,2,'f'),
                    node('t0',0,1,0,'t'),node('t1',1,.4,1,'t'),node('t2',2,0,2,'t')]
        result=joint_track_candidate_graph(candidates,self.specs(),1.3)
        self.assertEqual(result['identity_switch_count'],0)
        self.assertIn('f1',result['paths']['freezing'])

    def test_i_missing_evidence_preserves_unresolved_without_bridge(self):
        candidates=[node('f0',0,0,0,'f'),node('f2',2,0,2,'f'),node('t0',0,1,0,'t'),node('t2',2,1,2,'t')]
        result=joint_track_candidate_graph(candidates,self.specs(),.5)
        self.assertEqual(result['status'],'unresolved')
        self.assertFalse(result['bridged'])


class FidelityBenchmarkTests(unittest.TestCase):
    def test_j_bad_accepted_segment_cannot_pass_fidelity(self):
        points=[node('a',0,0,1,'f'),node('b',1,1,2,'f'),node('c',2,0,3,'f')]
        _,meta=path_centerline(points,(0,2,0,1),.01,raw_points=[(0,0),(1,0),(2,0)],fidelity_threshold=.01)
        self.assertIn(meta['status'],('failed','unresolved'))

    def test_m_geometry_metric_has_no_manual_dependency_in_production(self):
        automatic=np.array([[0,0],[.001,.5],[0,1]],float)
        reference=np.array([[0,0],[0,.5],[0,1]],float)
        metrics=curve_geometry_metrics(automatic,reference,(0,1,0,1))
        self.assertLess(metrics['symmetric_mean_normalized_distance'],.001)

    def test_n_geometry_metric_keeps_scalar_and_geometry_separate(self):
        automatic=np.array([[0,0],[.1,.5],[0,1]],float)
        reference=np.array([[0,0],[0,.5],[0,1]],float)
        metrics=curve_geometry_metrics(automatic,reference,(0,1,0,1))
        self.assertIn('symmetric_max_normalized_distance',metrics)
        self.assertNotIn('mae',metrics)

    def test_n_release_count_has_one_automated_source(self):
        text='![Tests](https://img.shields.io/badge/tests-165%20passed-brightgreen)\nRan 162 tests\n总计：165/165 通过'
        updated=update_test_count_text(text,180)
        self.assertIn('tests-180%20passed',updated)
        self.assertIn('Ran 180 tests',updated)
        self.assertIn('总计：180/180 通过',updated)


if __name__ == '__main__':
    unittest.main()
