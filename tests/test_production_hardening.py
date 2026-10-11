"""Real-source regressions and failure gates. Fixtures are not blind validation."""
import copy
import json
from pathlib import Path
import unittest
import tempfile
import hashlib

from test_hardening import graphical, numerical, run
from sources import comparison_fingerprint, selected_points
from quality import issues, qa
from presentation import curve_blocks
from reporting import markdown_report

FIXTURES=Path(__file__).parent/'fixtures'
def read(name):return json.loads((FIXTURES/name).read_text(encoding='utf-8'))


class HardeningFailureTests(unittest.TestCase):
    def test_invalid_source_schema_is_rejected_before_any_output(self):
        from uwc import export
        d=graphical();d['curves'][0]['branch']='冻结'
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):export(d,root)
            self.assertEqual(list(Path(root).glob('*.xlsx')),[])
            self.assertEqual(list(Path(root).glob('*.md')),[])

    def test_cached_table_still_checks_every_binding_hash(self):
        d=graphical()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'source.csv';path.write_text('-2,0.2\n',encoding='utf-8')
            source=numerical(d,kind='structured_data')
            source['table_binding']=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),sheet=None,
                row_start=1,row_end=1,temperature_column=1,value_column=2,temperature_unit='degree_celsius',unit='cubic_meter_per_cubic_meter')
            second=copy.deepcopy(source);second['dataset_id']='second';second['table_binding']['sha256']='0'*64
            d['numerical_datasets']=[source,second]
            result=run(d,root)
            self.assertEqual(result['source_failures'][0]['dataset_id'],'second')
            self.assertFalse(result['paper']['database_ready'])

    def test_unverified_numerical_source_cannot_grant_readiness(self):
        d=graphical();d['numerical_datasets']=[numerical(d)]
        d['numerical_datasets'][0]['variable_definition_verified']=False
        self.assertFalse(run(d)['paper']['database_ready'])

    def test_changed_reference_invalidates_prior_source_resolution(self):
        d=graphical();d['numerical_datasets']=[numerical(d,.23)];d=run(d)
        d['anchor_resolutions']=[dict(check_id=d['anchor_checks'][0]['check_id'],neighbor_points_checked=True,
            resolution='verified_source_choice',evidence_ids=['ev_1'],explanation='Verified source and neighbors.',
            comparison_fingerprint=comparison_fingerprint(d['anchor_checks'][0],d['uwc_points'][0],d['reference_points'][0]))]
        self.assertTrue(run(d)['paper']['database_ready'])
        d['numerical_datasets'][0]['observations'][0]['value']=.24
        self.assertFalse(run(d)['paper']['database_ready'])

    def test_stored_error_cannot_be_edited_to_zero(self):
        d=graphical();d['numerical_datasets']=[numerical(d,.23)];d=run(d)
        d['anchor_checks'][0].update(absolute_error=0,status='within_tolerance')
        self.assertTrue(any('discrepancy' in e for e in issues(d)))

    def test_warming_matches_thawing_inventory(self):
        d=graphical();d['curves'][0]['branch']='warming';d['evidence'][0]['expected_series'][0]['branch']='thawing'
        d=run(d)
        self.assertEqual(d['coverage']['coverage_percentage'],100)
        self.assertFalse(any('missing' in r['description'].lower() for r in d['review_queue'] if r['severity']=='critical'))


@unittest.skipUnless(
    (FIXTURES/'wang2023.json').exists(),
    'Private recorded-paper fixtures are not distributed in the public repository.',
)
class RealPaperHardeningTests(unittest.TestCase):
    def test_real_fits_do_not_replace_measurements_or_claim_trace_completeness(self):
        d=run(read('wang2023.json'))
        self.assertEqual(d['coverage']['expected_curve_count'],21)
        self.assertEqual(len([c for c in d['curves'] if c['curve_data_type']=='measured_point']),3)
        self.assertEqual(len([c for c in d['curves'] if c['curve_data_type']=='fitted_curve']),18)
        self.assertEqual(d['anchor_summary']['checked_count'],3)
        self.assertEqual(d['point_coverage']['not_checked_curve_count'],21)
        self.assertEqual(d['point_coverage']['unexplained_gap_count'],0)
        self.assertEqual(d['point_coverage']['protocol_difference_count'],7)
        self.assertFalse(d['paper']['database_ready'])

    def test_single_curve_preserves_japanese_source_and_unknown_nmr_state(self):
        d=run(read('tokoro2010.json'))
        self.assertEqual((d['coverage']['expected_curve_count'],len(d['curves']),len(d['uwc_points'])),(1,1,12))
        self.assertEqual(d['curves'][0]['uwc_definition_reported'],'不凍水分量（%）')
        self.assertEqual(d['curves'][0]['branch'],'unknown')
        self.assertTrue(all(p['uwc_preferred_value'] is None for p in d['uwc_points']))
        self.assertFalse(d['paper']['database_ready'])
        self.assertEqual(len([r for r in d['review_queue'] if r['severity']=='critical' and r['status']=='open']),2)

    def test_chen_anchors_preserve_graph_and_choose_exact_values(self):
        d=read('chen_2024.json');result=run(d)
        self.assertEqual(len(result['uwc_points']),115)
        self.assertEqual(result['uwc_points'],d['uwc_points'])
        a=result['anchor_summary']
        self.assertEqual((a['checked_count'],a['selected_count'],a['strong_warning_count']),(15,15,2))
        self.assertAlmostEqual(a['maximum_absolute_error'],.032)
        self.assertAlmostEqual(a['mean_absolute_error'],.005033333333333336)
        self.assertFalse(result['paper']['database_ready'])
        points=[p for p in selected_points(result) if p['curve_id']=='curve_57_freezing' and p['temperature_celsius']==-15]
        self.assertAlmostEqual(points[0]['uwc_preferred_value'],.0772)
        block=next(b for b in curve_blocks(result) if b['curve_id']=='curve_57_freezing')
        self.assertIn((-15,.0772),block['pairs'])

    def test_chen_known_source_gaps_are_separate_from_curve_coverage(self):
        d=run(read('chen_2024.json'))
        self.assertEqual(d['coverage']['coverage_percentage'],100)
        self.assertEqual(d['point_coverage']['protocol_expected_point_count'],120)
        self.assertEqual(d['point_coverage']['protocol_difference_count'],5)
        self.assertEqual(d['point_coverage']['known_expected_point_count'],0)
        self.assertEqual(d['point_coverage']['unexplained_gap_count'],0)
        dimensions={p['property']:p['value'] for p in d['soil_properties'] if p.get('experiment_role')=='uwc_measurement'}
        self.assertEqual(dimensions,{'sample_diameter':25,'sample_height':60})

    def test_lai_all_model_variants_are_distinct(self):
        d=run(read('lai2021.json'))
        self.assertEqual((d['coverage']['expected_curve_count'],d['coverage']['extracted_curve_count']),(9,9))
        self.assertEqual(len(d['uwc_points']),294)
        self.assertEqual(len([c for c in d['curves'] if c['curve_data_type']=='measured_point']),3)
        self.assertEqual(d['coverage']['duplicate_conditions'],[])
        self.assertTrue(d['paper']['database_ready'])

    def test_removing_one_model_does_not_shrink_manifest(self):
        d=read('lai2021.json');cid=d['curves'][-1]['curve_id']
        d['curves']=d['curves'][:-1];d['uwc_points']=[p for p in d['uwc_points'] if p['curve_id']!=cid]
        d=run(d)
        self.assertEqual(d['coverage']['expected_curve_count'],9)
        self.assertEqual(d['coverage']['extracted_curve_count'],8)
        self.assertEqual(len(d['recovery_attempts']),1)
        self.assertFalse(d['paper']['database_ready'])

    def test_ren_uncertain_water_basis_does_not_merge_conditions_or_force_theta(self):
        d=run(read('ren2023.json'))
        self.assertEqual(d['coverage']['expected_curve_count'],5)
        self.assertEqual(len(d['uwc_points']),105)
        self.assertEqual(len(d['conditions']),3)
        self.assertTrue(all(p['uwc_preferred_value'] is None for p in d['uwc_points']))
        self.assertFalse(d['paper']['database_ready'])

    def test_multipanel_total_uwc_does_not_duplicate_components_or_hide_occluded_points(self):
        d=run(read('chen2021.json'))
        self.assertEqual(d['coverage']['expected_curve_count'],3)
        self.assertEqual(d['coverage']['coverage_percentage'],100)
        self.assertEqual((d['point_coverage']['protocol_expected_point_count'],len(d['uwc_points'])),(39,36))
        self.assertEqual(d['point_coverage']['unexplained_gap_count'],0)
        self.assertEqual(d['point_coverage']['protocol_difference_count'],3)
        self.assertTrue(all(p['uwc_original_unit']=='percent' for p in d['uwc_points']))
        self.assertTrue(all(abs(p['uwc_original_value']/100-p['uwc_preferred_value'])<1e-12 for p in d['uwc_points']))
        self.assertFalse(d['paper']['database_ready'])

    def test_report_contract_is_compact_and_preserves_uncertain_values(self):
        report=markdown_report(run(read('chen_2024.json')))
        headings=[line[3:] for line in report.splitlines() if line.startswith('## ')]
        self.assertEqual(headings,['Paper','Extraction Summary','UWC/SFCC Sources','Variable Handling','Cross-source Validation','Notes','Manual Review'])
        self.assertIn('26.33',report);self.assertIn('1.89',report)
        self.assertIn('basis unspecified',report)


if __name__=='__main__':unittest.main()
