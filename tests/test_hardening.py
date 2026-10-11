"""Generic adversarial cases; no benchmark identifiers in production behavior."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_extractor import fixture
from hardening import prepare_scientific
from manifest import build_manifest
from quality import qa, issues
from sources import selected_points, comparison_fingerprint


def graphical():
    d = fixture();d['derivations'] = []
    c = d['curves'][0]
    c.update(uwc_basis='volumetric', raw_variable='volumetric_unfrozen_water_content',
             extraction_method='pdf_vector', plotted_uwc_axis_span=.4, plotted_uwc_axis_unit='cubic_meter_per_cubic_meter')
    from test_extractor import blank
    c['digitization'] = blank('digitization', coordinate_system='pdf_points', x_axis_scale='linear', y_axis_scale='linear',
        x_axis_orientation='normal', y_axis_orientation='normal', x_calibration_points=3, y_calibration_points=3,
        x_calibration_residual_px=.1, y_calibration_residual_px=.1, axis_confidence='high',
        calibration_artifact='.internal/calibration.json', benchmark_status='pending')
    d['uwc_points'][0].update(uwc_original_value=.2, uwc_original_unit='cubic_meter_per_cubic_meter',
        uwc_original_unit_reported='m³/m³', uwc_original_basis='volumetric', uwc_preferred_value=.2,
        uwc_preferred_value_source='figure_digitized', uwc_derivation_id=None, extraction_method='pdf_vector',
        value_source='figure_digitized', temperature_value_source='figure_digitized')
    return d


def numerical(d, value=.2, kind='numerical_label', role='anchors_only', name='numbers'):
    c = d['curves'][0]
    return dict(dataset_id=name, sample_id=c['sample_id'], condition_id=c['condition_id'], branch=c['branch'],
        cycle_number=c['cycle_number'], method=c['method'], curve_data_type=c['curve_data_type'], data_origin=c['data_origin'],
        raw_variable='volumetric_unfrozen_water_content', uwc_basis='volumetric', variable_definition_verified=True,
        source_kind=kind, coverage_role=role, evidence_ids=['ev_1'], source_locator='Source numerical observation',
        observations=[dict(temperature=-2, temperature_unit='degree_celsius', value=value, unit='cubic_meter_per_cubic_meter',
                           temperature_reported='-2', value_reported=str(value))])


def run(d, root='.'):
    # Fixture regressions use recorded evidence only, never reopen local papers.
    with patch('sources.targeted_search', return_value=([], [], [])):
        return qa(prepare_scientific(d, root))


class ManifestAndRecoveryTests(unittest.TestCase):
    def test_expected_inventory_does_not_depend_on_extracted_curves(self):
        d=fixture();a=copy.deepcopy(build_manifest(d));d['curves']=[];d['uwc_points']=[]
        self.assertEqual(build_manifest(d),a)

    def test_recover_full_numerical_series_for_arbitrary_identifiers(self):
        d=graphical();d['numerical_datasets']=[numerical(d,role='full_series',kind='structured_data')]
        d['curves']=[];d['uwc_points']=[]
        result=run(d)
        self.assertEqual(result['coverage']['coverage_percentage'],100)
        self.assertEqual(result['recovery_attempts'][0]['status'],'recovered')
        self.assertTrue(result['paper']['database_ready'])
        self.assertEqual(issues(result),[])

    def test_three_anchors_do_not_impersonate_a_full_missing_curve(self):
        d=graphical();d['numerical_datasets']=[numerical(d)];d['curves']=[];d['uwc_points']=[]
        result=run(d)
        self.assertEqual(result['coverage']['extracted_curve_count'],0)
        self.assertFalse(result['paper']['database_ready'])

    def test_recovery_does_not_repeat_unchanged_failed_attempt(self):
        d=graphical();d['curves']=[];d['uwc_points']=[]
        result=run(d);again=run(result)
        self.assertEqual(again['recovery_attempts'],result['recovery_attempts'])
        self.assertEqual(len(again['recovery_attempts']),1)

    def test_wrong_cycle_dataset_cannot_recover_a_curve(self):
        d=graphical();source=numerical(d,role='full_series');source['cycle_number']=99
        d['numerical_datasets']=[source];d['curves']=[];d['uwc_points']=[]
        with self.assertRaisesRegex(ValueError,'cycle'):run(d)

    def test_equal_priority_disagreement_blocks_automatic_recovery(self):
        d=graphical();d['numerical_datasets']=[numerical(d,.2,role='full_series'),numerical(d,.3,role='full_series',name='second')]
        d['curves']=[];d['uwc_points']=[]
        result=run(d)
        self.assertEqual(result['recovery_attempts'][0]['status'],'ambiguous')
        self.assertEqual(result['coverage']['extracted_curve_count'],0)

    def test_bound_csv_is_read_and_hash_change_is_not_trusted(self):
        d=graphical();source=numerical(d,role='full_series',kind='structured_data');source['observations']=[]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw.csv';path.write_text('-2,0.25\n',encoding='utf8')
            source['table_binding']=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),sheet=None,
                row_start=1,row_end=1,temperature_column=1,value_column=2,temperature_unit='degree_celsius',unit='cubic_meter_per_cubic_meter')
            d['numerical_datasets']=[source];d['curves']=[];d['uwc_points']=[]
            result=run(d,tmp);self.assertEqual(result['uwc_points'][0]['uwc_original_value'],.25)
            path.write_text('-2,0.35\n',encoding='utf8')
            result=run(d,tmp);self.assertFalse(result['paper']['database_ready']);self.assertTrue(result['source_failures'])

    def test_point_gap_prevents_database_ready_despite_full_curve_coverage(self):
        d=graphical();manifest=build_manifest(d)
        manifest[0]['expected_point_information'].update(count=2,temperatures_celsius=[-2,-3],information_type='reported_observations',evidence_ids=['ev_1'])
        result=run(d)
        self.assertEqual(result['coverage']['coverage_percentage'],100)
        self.assertEqual(result['point_coverage']['unexplained_gap_count'],1)
        self.assertFalse(result['paper']['database_ready'])

    def test_evidence_backed_source_gap_is_reported_separately(self):
        d=graphical();info=build_manifest(d)[0]['expected_point_information']
        info.update(count=2,temperatures_celsius=[-2,-3],information_type='reported_targets',evidence_ids=['ev_1'],
            source_points_verified=True,gap_resolution='not_reported_in_source',resolution_evidence_ids=['ev_1'],explanation='Only one plotted observation is present in the verified source.')
        result=run(d)
        self.assertEqual(result['point_coverage']['protocol_difference_count'],1)
        self.assertEqual(result['point_coverage']['unexplained_gap_count'],0)
        self.assertTrue(result['paper']['database_ready'])

    def test_exclusion_cannot_hide_missing_curve_without_explicit_source_statement(self):
        d=graphical();m=build_manifest(d)[0];m['measurement_status']='explicitly_not_measured'
        with self.assertRaisesRegex(ValueError,'explicit verified source statement'):run(d)


class AnchorAndReadinessTests(unittest.TestCase):
    def test_exact_anchor_selected_and_entire_original_graph_preserved(self):
        d=graphical();original=copy.deepcopy(d['uwc_points']);d['numerical_datasets']=[numerical(d,.202)]
        result=run(d)
        self.assertEqual(result['uwc_points'],original)
        self.assertEqual(selected_points(result)[0]['uwc_preferred_value'],.202)
        self.assertEqual(result['anchor_summary']['checked_count'],1)
        self.assertTrue(result['paper']['database_ready']);self.assertEqual(issues(result),[])

    def test_large_anchor_conflict_cannot_be_acknowledged_into_readiness(self):
        d=graphical();d['numerical_datasets']=[numerical(d,.23)]
        result=run(d)
        self.assertEqual(result['anchor_summary']['strong_warning_count'],1)
        self.assertFalse(result['paper']['database_ready'])
        for r in result['review_queue']:r.update(status='resolved',resolution_notes='Acknowledged')
        self.assertFalse(run(result)['paper']['database_ready'])

    def test_explicit_source_resolution_requires_neighbor_check_and_evidence(self):
        d=graphical();d['numerical_datasets']=[numerical(d,.23)]
        result=run(d)
        result['anchor_resolutions']=[dict(check_id=result['anchor_checks'][0]['check_id'],neighbor_points_checked=True,
            resolution='verified_source_choice',evidence_ids=['ev_1'],explanation='Source values and neighboring graphical points were rechecked; exact source selected.',
            comparison_fingerprint=comparison_fingerprint(result['anchor_checks'][0], result['uwc_points'][0], result['reference_points'][0]))]
        self.assertTrue(run(result)['paper']['database_ready'])

    def test_thresholds_are_configurable_and_axis_span_has_units(self):
        d=graphical();d['numerical_datasets']=[numerical(d,.205)]
        self.assertEqual(run(d)['anchor_summary']['warning_count'],1)
        d['qa_settings']=dict(volumetric_warning_threshold=.006,normalized_warning_threshold=.02)
        self.assertEqual(run(d)['anchor_summary']['warning_count'],0)
        d['curves'][0].pop('plotted_uwc_axis_unit')
        with self.assertRaisesRegex(ValueError,'explicit unit'):run(d)

    def test_table_priority_over_label_without_averaging(self):
        d=graphical();d['numerical_datasets']=[numerical(d,.202),numerical(d,.201,kind='table',name='tabular')]
        result=run(d);self.assertEqual(selected_points(result)[0]['uwc_preferred_value'],.201)

    def test_equal_priority_conflicting_anchors_are_not_selected(self):
        d=graphical();d['numerical_datasets']=[numerical(d,.201),numerical(d,.202,name='other')]
        result=run(d)
        self.assertEqual(result['observation_selections'],[])
        self.assertFalse(result['paper']['database_ready'])

    def test_freezing_anchor_never_matches_thawing_or_fitted_curve(self):
        for field,value in [('branch','thawing'),('curve_data_type','fitted_curve')]:
            d=graphical();source=numerical(d,.21);source[field]=value;d['numerical_datasets']=[source]
            result=run(d);self.assertEqual(result['observation_selections'],[])
            self.assertFalse(result['paper']['database_ready'])

    def test_wrong_variable_never_matches_by_magnitude(self):
        d=graphical();source=numerical(d,.2);source.update(raw_variable='unfrozen_water_saturation',uwc_basis='unfrozen_water_saturation')
        d['numerical_datasets']=[source]
        result=run(d);self.assertEqual(result['anchor_checks'][0]['status'],'incompatible_variable')
        self.assertFalse(result['paper']['database_ready'])

    def test_two_graphical_points_at_same_temperature_are_ambiguous(self):
        d=graphical();d['uwc_points'].append(dict(d['uwc_points'][0],point_id='extra',point_index=2))
        d['numerical_datasets']=[numerical(d)]
        result=run(d);self.assertEqual(result['anchor_checks'][0]['status'],'ambiguous')
        self.assertFalse(result['paper']['database_ready'])

    def test_unknown_variable_and_incomplete_metadata_passes_do_not_become_ready(self):
        d=graphical();d['curves'][0]['variable_definition_verified']=False
        self.assertFalse(run(d)['paper']['database_ready'])
        d=graphical();d['source_inspection']['property_pass_completed']=False
        result=run(d);self.assertFalse(result['paper']['database_ready'])
        self.assertEqual(result['qa_gates']['minimum_metadata_completeness'],'not_checked')

    def test_reexport_is_idempotent_and_does_not_grow_reference_points(self):
        d=graphical();d['numerical_datasets']=[numerical(d,.202)]
        result=run(d);again=run(result)
        for key in ('reference_points','observation_selections','anchor_checks','uwc_points','derivations','qa_gates'):
            self.assertEqual(result[key],again[key],key)


if __name__=='__main__':unittest.main()
