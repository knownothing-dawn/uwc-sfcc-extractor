"""RC3 generic curve-isolation, completeness and display-binding regressions."""
import copy
import unittest

from test_extractor import blank
from test_final_hardening import dense_trace
from test_hardening import graphical, run
from design import factor_caption, factor_value, test_condition_table
from manifest import build_manifest
from trace_processing import process_continuous_traces


def point_from(template, curve_id, index, x, y):
    point=copy.deepcopy(template)
    point.update(point_id=f'{curve_id}_{index}',curve_id=curve_id,point_index=index,trace_order=index,
        temperature_celsius=x,temperature_original_value=x,uwc_original_value=y,uwc_preferred_value=y)
    return point


def two_curves(y1, y2, count=101):
    data=dense_trace(3); template=data['uwc_points'][0]
    first=data['curves'][0]; first['curve_id']='c_1'
    second=copy.deepcopy(first);second['curve_id']='c_2';second['legend_label']='second'
    data['curves']=[first,second];data['uwc_points']=[];data['raw_trace_points']=[]
    for curve_id,fn in [('c_1',y1),('c_2',y2)]:
        for i in range(count):
            x=i/(count-1)
            data['uwc_points'].append(point_from(template,curve_id,i+1,x,fn(x)))
    return data


class CurveIsolationTests(unittest.TestCase):
    def test_independent_curves_have_no_contamination_warning(self):
        data=two_curves(lambda x:.1+.1*x,lambda x:.35+.05*x)
        process_continuous_traces(data)
        for curve in data['curves']:
            stats=curve['trace_processing']
            self.assertEqual(stats['curve_isolation_status'],'pass')
            self.assertNotIn('shared_path_contamination_warning',stats['warnings'])

    def test_one_legitimate_crossing_is_not_shared_path(self):
        data=two_curves(lambda x:.1+.2*x,lambda x:.3-.2*x)
        process_continuous_traces(data)
        for curve in data['curves']:
            stats=curve['trace_processing']
            self.assertEqual(stats['shared_segment_fraction'],0)
            self.assertNotIn('shared_path_contamination_warning',stats['warnings'])

    def test_long_identical_segment_is_flagged_and_excluded(self):
        data=two_curves(lambda x:.1+.1*x,lambda x:.1+.1*x if x<=.6 else .28+.03*x)
        process_continuous_traces(data)
        for curve in data['curves']:
            stats=curve['trace_processing']
            self.assertIn('shared_path_contamination_warning',stats['warnings'])
            self.assertGreater(stats['excluded_contaminated_point_count'],40)
            self.assertEqual(stats['curve_isolation_status'],'partial')

    def test_foreign_parallel_excursion_is_excluded(self):
        data=dense_trace(201);curve=data['curves'][0];template=data['uwc_points'][0]
        foreign=[point_from(template,'c_1',len(data['uwc_points'])+i+1,-20+20*i/49,.55+.03*i/49) for i in range(50)]
        data['uwc_points'].extend(foreign)
        for i,p in enumerate(data['uwc_points'],1):p['point_index']=p['trace_order']=i
        process_continuous_traces(data);stats=curve['trace_processing']
        self.assertGreaterEqual(stats['excluded_contaminated_point_count'],50)
        self.assertIn('multimodal_path_candidate_warning',stats['warnings'])
        self.assertEqual(stats['curve_isolation_status'],'partial')

    def test_ambiguous_overlap_is_unresolved_without_reconstruction(self):
        data=two_curves(lambda x:.1+.1*x,lambda x:.1+.1*x if .2<=x<=.8 else .3+.02*x)
        process_continuous_traces(data)
        self.assertTrue(all(c['trace_processing']['unresolved_segment_count'] for c in data['curves']))
        self.assertTrue(all(c['trace_processing']['status']!='pass' for c in data['curves']))

    def test_clean_curve_scientific_result_is_unchanged(self):
        data=dense_trace();process_continuous_traces(data)
        stats=data['curves'][0]['trace_processing']
        self.assertEqual((stats['raw_point_count'],stats['centerline_point_count'],stats['exported_point_count']),(402,201,26))
        self.assertEqual(stats['curve_isolation_status'],'pass')


class CompletenessAndDisplayTests(unittest.TestCase):
    def test_continuous_geometry_reduction_is_not_missing_observations(self):
        data=dense_trace();info=build_manifest(data)[0]['expected_point_information']
        info.clear();info.update(
            protocol_expected=dict(count=None,temperatures_celsius=[],evidence_ids=[]),
            reported_expected=dict(count=None,temperatures_celsius=[],evidence_ids=[]),
            source_observable=dict(count=400,temperatures_celsius=[],completeness='complete',evidence_ids=['ev_1']))
        result=run(data)
        self.assertLess(len(result['uwc_points']),50)
        self.assertEqual(result['point_coverage']['unexplained_gap_count'],0)
        self.assertFalse(any(r['issue_type']=='missing_point_or_not_reported' for r in result['review_queue']))

    def test_discrete_reported_missing_marker_remains_critical(self):
        data=graphical();manifest=build_manifest(data)[0]
        info=manifest['expected_point_information'];info.clear();info.update(
            protocol_expected=dict(count=None,temperatures_celsius=[],evidence_ids=[]),
            reported_expected=dict(count=2,temperatures_celsius=[-2,-3],evidence_ids=['ev_1']),
            source_observable=dict(count=None,temperatures_celsius=[],completeness='unknown',evidence_ids=[]))
        result=run(data)
        self.assertEqual(result['point_coverage']['unexplained_gap_count'],1)
        self.assertTrue(any(r['issue_type']=='missing_point_or_not_reported' for r in result['review_queue']))

    def test_reported_value_unit_binding_is_atomic(self):
        data=graphical();data['soil_properties'].append(blank('property',property_id='theta_1',sample_id='s_1',condition_id='cond_1',
            property='initial_volumetric_water_content',property_reported='Initial volumetric water content',
            value=.1562,value_reported='15.62',unit='cubic_meter_per_cubic_meter',unit_reported='%',
            original_value=15.62,original_unit='percent',definition_reported='Wv',definition_status='explicit',
            value_source='reported',derivation_id=None,mineral_name_reported=None,mineral_name_normalized=None,
            confidence='high',evidence_ids=['ev_1']))
        caption=factor_caption('initial_volumetric_water_content',*factor_value(data,'cond_1','initial_volumetric_water_content'))
        self.assertEqual(caption,'Wv = 15.62%')
        self.assertNotIn('15.62 m³/m³',caption)

    def test_normalized_condition_precision_preserves_four_decimals(self):
        data=graphical();data['soil_properties'].append(blank('property',property_id='theta_1',sample_id='s_1',condition_id='cond_1',
            property='initial_volumetric_water_content',property_reported='Initial volumetric water content',
            value=.2,value_reported='0.2000',unit='cubic_meter_per_cubic_meter',unit_reported='m³/m³',
            original_value=.2,original_unit='cubic_meter_per_cubic_meter',definition_reported='theta',definition_status='explicit',
            value_source='reported',derivation_id=None,mineral_name_reported=None,mineral_name_normalized=None,
            reported_precision=4,confidence='high',evidence_ids=['ev_1']))
        headers,rows=test_condition_table(data)
        column=headers.index('Initial θ (m³/m³)')
        self.assertEqual(rows[0][column],'0.2000')


if __name__=='__main__':
    unittest.main()
