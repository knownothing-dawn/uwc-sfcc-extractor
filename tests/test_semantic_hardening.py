"""Semantic boundaries, using only small synthetic inputs and recorded failures."""
import copy
import json
from pathlib import Path
import unittest
from test_hardening import graphical, numerical, run
from manifest import build_manifest
from quality import issues
from semantics import point_set
from presentation import curve_blocks
from reporting import markdown_report

FIXTURES=Path(__file__).parent/'fixtures'
def read(name):return json.loads((FIXTURES/name).read_text(encoding='utf8'))

def point_info(d,protocol=None,reported=None,observable=None,complete='unknown'):
    m=build_manifest(d)[0]
    m['expected_point_information']=dict(
        protocol_expected=point_set(len(protocol),protocol,['ev_1']) if protocol is not None else point_set(),
        reported_expected=point_set(len(reported),reported,['ev_1']) if reported is not None else point_set(),
        source_observable=dict(point_set(observable,evidence_ids=['ev_1']),completeness=complete))
    return m['expected_point_information']

class PointExpectationTests(unittest.TestCase):
    def test_protocol_only_is_information_and_does_not_grant_source_completeness(self):
        d=graphical();point_info(d,protocol=[-2,-3],observable=1)
        result=run(d)
        self.assertEqual(result['point_coverage']['protocol_difference_count'],1)
        self.assertEqual(result['point_coverage']['unexplained_gap_count'],0)
        self.assertFalse(result['paper']['database_ready'])
        self.assertEqual(result['qa_gates']['point_source_completeness'],'not_checked')
        self.assertEqual(result['paper']['review_status'],'usable_with_review')
        self.assertFalse(any(r['issue_type']=='missing_point_or_not_reported' for r in result['review_queue']))

    def test_complete_observed_source_can_differ_from_protocol(self):
        d=graphical();point_info(d,protocol=[-2,-3],observable=1,complete='complete')
        result=run(d)
        self.assertTrue(result['paper']['database_ready'])
        self.assertEqual(len(result['uwc_points']),1)

    def test_reported_observation_gap_still_blocks_even_with_source_gap_note(self):
        d=graphical();info=point_info(d,reported=[-2,-3],observable=1,complete='complete')
        info.update(gap_resolution='not_reported_in_source',explanation='Only one is visible.',resolution_evidence_ids=['ev_1'])
        result=run(d)
        self.assertEqual(result['point_coverage']['unexplained_gap_count'],1)
        self.assertFalse(result['paper']['database_ready'])
        self.assertEqual(result['paper']['review_status'],'partial')

    def test_explicit_output_promise_can_make_protocol_a_hard_denominator(self):
        d=graphical();info=point_info(d,protocol=[-2,-3],observable=1,complete='complete')
        quote='Every protocol observation is shown in this series.'
        d['evidence'][0]['quoted_evidence']=quote
        info.update(protocol_applies_to_output=True,protocol_output_evidence_ids=['ev_1'],protocol_output_statement_reported=quote)
        self.assertEqual(run(d)['point_coverage']['unexplained_gap_count'],1)

    def test_output_promise_requires_verbatim_verified_evidence(self):
        d=graphical();point_info(d,protocol=[-2,-3])['protocol_applies_to_output']=True
        with self.assertRaisesRegex(ValueError,'output-series statement'):run(d)

    def test_known_observable_point_cannot_be_silently_dropped(self):
        d=graphical();point_info(d,observable=2,complete='complete')
        result=run(d)
        self.assertEqual(result['point_coverage']['observable_missing_count'],1)
        self.assertFalse(result['paper']['database_ready'])

    def test_partial_source_does_not_pass_from_equal_counts(self):
        d=graphical();point_info(d,reported=[-2],observable=1,complete='partial')
        result=run(d)
        self.assertFalse(result['paper']['database_ready'])
        self.assertEqual(result['paper']['review_status'],'partial')

    def test_full_numerical_rows_establish_hard_point_denominator(self):
        d=graphical();point_info(d,protocol=[-2,-3])
        source=numerical(d,kind='table',role='full_series')
        source['observations'].append(dict(source['observations'][0],temperature=-3))
        d['numerical_datasets']=[source]
        result=run(d)
        self.assertEqual(result['point_coverage']['reported_expected_point_count'],2)
        self.assertEqual(result['point_coverage']['unexplained_gap_count'],1)

    def test_sparse_anchors_do_not_create_full_point_denominator(self):
        d=graphical();point_info(d,protocol=[-2,-3],observable=1,complete='complete')
        d['numerical_datasets']=[numerical(d)]
        result=run(d)
        self.assertEqual(result['point_coverage']['reported_expected_point_count'],0)
        self.assertEqual(result['anchor_summary']['checked_count'],1)

    def test_other_method_or_variable_rows_do_not_establish_this_series_denominator(self):
        for mismatch in ('method', 'variable'):
            d=graphical();point_info(d,protocol=[-2,-3])
            source=numerical(d,kind='table',role='full_series')
            if mismatch=='method':source['method']='differential_scanning_calorimetry'
            else:source.update(uwc_basis='unfrozen_water_saturation',raw_variable='unfrozen_water_saturation')
            d['numerical_datasets']=[source]
            result=run(d)
            self.assertEqual(result['point_coverage']['reported_expected_point_count'],0)
            self.assertFalse(result['paper']['database_ready'])

    def test_bad_point_evidence_and_counts_are_rejected(self):
        for invalid in ('evidence','count'):
            d=graphical();info=point_info(d,reported=[-2,-3])
            if invalid=='evidence':info['reported_expected']['evidence_ids']=[]
            else:info['reported_expected']['count']=1
            with self.assertRaises(ValueError):run(d)

class IndependentMeaningTests(unittest.TestCase):
    def continuous(self):
        d=graphical();c=d['curves'][0]
        c.update(curve_data_type='unknown',data_semantics='measured',representation='continuous_measured_trace',extraction_method='raster_curve')
        d['uwc_points'][0].update(curve_data_type='unknown',extraction_method='raster_curve')
        d['evidence'][0]['expected_series'][0].update(curve_data_type='unknown',data_semantics='measured',representation='continuous_measured_trace')
        return d

    def test_continuous_experiment_is_measured_without_becoming_a_fit(self):
        result=run(self.continuous())
        self.assertTrue(result['paper']['database_ready'])
        self.assertEqual(result['coverage']['expected_curve_count'],1)
        self.assertIn('Measured',curve_blocks(result)[0]['subtitle'])
        self.assertEqual(issues(result),[])

    def test_shape_cannot_change_scientific_meaning(self):
        for sem,rep in [('fitted','continuous_measured_trace'),('measured','continuous_model_curve')]:
            d=self.continuous();d['curves'][0].update(data_semantics=sem,representation=rep)
            with self.assertRaises(ValueError):run(d)

    def test_legacy_classification_cannot_silently_conflict_with_new_semantics(self):
        d=graphical();d['curves'][0]['data_semantics']='predicted'
        with self.assertRaisesRegex(ValueError,'legacy'):run(d)

    def test_graph_and_table_can_describe_the_same_measured_series(self):
        d=graphical();d['curves'][0].update(data_semantics='measured',representation='discrete_markers')
        source=numerical(d,.202,kind='table');source.update(data_semantics='measured',representation='tabulated_points')
        d['numerical_datasets']=[source]
        result=run(d)
        self.assertEqual(result['anchor_summary']['selected_count'],1)
        self.assertEqual(result['coverage']['extracted_curve_count'],1)

    def test_new_derived_semantics_do_not_require_a_fake_legacy_fit(self):
        d=self.continuous()
        for row in d['curves']+d['evidence'][0]['expected_series']:
            row.update(data_semantics='derived',representation='continuous_model_curve')
        result=run(d)
        self.assertEqual(result['curves'][0]['curve_data_type'],'unknown')
        self.assertEqual(result['curves'][0]['data_semantics'],'derived')

class AvailabilityAndUsabilityTests(unittest.TestCase):
    def unavailable(self,target='direct_target_quantity',availability='reported_but_not_numerically_available'):
        d=graphical();m=build_manifest(d)[0]
        m.update(target_quantity_status=target,availability_status=availability,availability_evidence_ids=['ev_1'],
            availability_explanation='Recorded source inspection establishes availability for this condition.')
        d['curves']=[];d['uwc_points']=[]
        return d

    def test_proxy_is_documented_but_never_expected_as_numeric_uwc(self):
        result=run(self.unavailable('proxy_signal_only','not_applicable'))
        self.assertEqual(result['coverage']['design_dataset_count'],1)
        self.assertEqual(result['coverage']['expected_curve_count'],0)
        self.assertEqual(result['coverage']['missing_conditions'],[])
        self.assertEqual(result['recovery_attempts'],[])
        self.assertFalse(any(r['severity']=='critical' for r in result['review_queue']))
        self.assertEqual(result['paper']['review_status'],'insufficient')
        self.assertFalse(result['paper']['database_ready'])

    def test_unavailable_target_is_not_an_extraction_failure_or_importable(self):
        result=run(self.unavailable())
        self.assertEqual(result['coverage']['expected_curve_count'],0)
        self.assertEqual(len(result['coverage']['unavailable_target_dataset_ids']),1)
        self.assertFalse(any(r['severity']=='critical' for r in result['review_queue']))
        self.assertFalse(result['paper']['database_ready'])

    def test_availability_label_alone_cannot_hide_missing_curve(self):
        d=self.unavailable();d['expected_datasets'][0]['availability_evidence_ids']=[]
        with self.assertRaisesRegex(ValueError,'verified evidence'):run(d)

    def test_partially_available_stays_in_denominator_and_blocks_import(self):
        d=graphical();m=build_manifest(d)[0];m['availability_status']='partially_available'
        result=run(d)
        self.assertEqual(result['coverage']['expected_curve_count'],1)
        self.assertFalse(result['paper']['database_ready'])
        self.assertEqual(result['paper']['review_status'],'partial')

    def test_user_facing_review_state_cannot_override_autonomous_gates(self):
        d=graphical();d['paper']['review_status']='database_ready'
        d['numerical_datasets']=[numerical(d,.23)]
        result=run(d)
        self.assertFalse(result['paper']['database_ready'])
        self.assertEqual(result['paper']['review_status'],'usable_with_review')
        self.assertIn('Human review usability: usable_with_review',markdown_report(result))

    def test_legacy_approval_is_preserved_without_granting_import(self):
        d=graphical();d['paper']['review_status']='approved';d['numerical_datasets']=[numerical(d,.23)]
        result=run(d)
        self.assertEqual(result['paper']['legacy_review_status'],'approved')
        self.assertFalse(result['paper']['database_ready'])

@unittest.skipUnless(
    (FIXTURES/'failures').exists(),
    'Private recorded-paper fixtures are not distributed in the public repository.',
)
class RecordedFailureTests(unittest.TestCase):
    def test_huang_protocol_discrepancies_are_information_not_sixteen_critical_gaps(self):
        before=read('failures/huang2023.json');d=run(before)
        self.assertEqual(d['uwc_points'],before['uwc_points'])
        self.assertEqual(d['point_coverage']['protocol_expected_point_count'],160)
        self.assertEqual(d['point_coverage']['protocol_difference_count'],56)
        self.assertEqual(d['point_coverage']['unexplained_gap_count'],0)
        self.assertFalse(any(r['severity']=='critical' for r in d['review_queue']))
        self.assertFalse(d['paper']['database_ready'])

    def test_watanabe_unknown_denominator_stays_unknown(self):
        d=run(read('failures/watanabe2016.json'))
        self.assertEqual(d['point_coverage']['reported_expected_point_count'],0)
        self.assertEqual(d['point_coverage']['source_observable_point_count'],80)
        self.assertEqual(d['point_coverage']['not_checked_curve_count'],7)
        self.assertEqual(d['paper']['review_status'],'usable_with_review')
        self.assertFalse(d['paper']['database_ready'])

    def test_kozlowski_continuous_measured_classification_is_representable(self):
        source=read('failures/kozlowski2013.json');d=run(source)
        traces=[c for c in d['curves'] if c['representation']=='continuous_measured_trace']
        self.assertEqual(len(traces),5)
        self.assertTrue(all(c['data_semantics']=='measured' for c in traces))
        self.assertFalse(any(r['issue_type']=='curve_identity_uncertain' for r in d['review_queue']))
        self.assertEqual(d['uwc_points'],source['uwc_points'])
        self.assertFalse(d['paper']['database_ready'])

    def test_xiao_proxy_exclusion_does_not_discard_design_or_manufacture_uwc(self):
        source=read('failures/xiao2017.json');d=run(source)
        self.assertEqual((d['coverage']['design_dataset_count'],d['coverage']['expected_curve_count'],d['coverage']['extracted_curve_count']),(12,6,6))
        self.assertEqual(len(d['coverage']['proxy_dataset_ids']),6)
        self.assertEqual(d['uwc_points'],source['uwc_points'])
        self.assertTrue(d['paper']['database_ready'])
        self.assertTrue(all(v=='pass' for v in d['qa_gates'].values()))

    def test_luo_unavailable_target_keeps_design_and_strict_import_block(self):
        source=read('failures/luo_availability.json');d=run(source)
        self.assertEqual((d['coverage']['design_dataset_count'],d['coverage']['expected_curve_count'],d['coverage']['extracted_curve_count']),(19,18,18))
        self.assertEqual(d['coverage']['missing_conditions'],[])
        self.assertFalse(any(r['severity']=='critical' for r in d['review_queue']))
        self.assertFalse(d['paper']['database_ready'])
        self.assertEqual(d['paper']['review_status'],'partial')
        self.assertEqual(d['uwc_points'],source['uwc_points'])

if __name__=='__main__':unittest.main()
