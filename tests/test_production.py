"""Regression checks for subtractive UWC production optimization."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_extractor import fixture, blank
from science import normalize_point
from quality import issues, qa
from uwc import export, prepare
from presentation import curve_blocks


class ProductionTests(unittest.TestCase):
    def test_full_primary_source_not_replaced_by_printed_validation_values(self):
        d = fixture()
        d["evidence"][0].update(source_role="validation", figure_number="12", figure_panel="a")
        primary = copy.deepcopy(d["evidence"][0])
        primary.update(evidence_id="ev_primary", source_role="primary_uwc", figure_number="9", figure_panel=None,
                       expected_series=[{"condition_id": "cond_1", "branch": b, "curve_data_type": "measured_point"}
                                        for b in ("freezing", "thawing")])
        d["evidence"].append(primary)
        result = qa(d)
        self.assertEqual(result["paper"]["extraction_status"], "manual_review_required")
        self.assertTrue(any("missing 2" in r["description"] and r["severity"] == "critical" for r in result["review_queue"]))

    def test_missing_thawing_is_critical(self):
        d = fixture()
        d["evidence"][0]["expected_series"].append({"condition_id": "cond_1", "branch": "thawing", "curve_data_type": "measured_point"})
        result = qa(d)
        self.assertTrue(any("thawing" in r["description"] and r["severity"] == "critical" for r in result["review_queue"]))

    def test_fitted_curve_cannot_satisfy_expected_measured_curve(self):
        d = fixture()
        d["curves"][0]["curve_data_type"] = "fitted_curve"
        d["uwc_points"][0]["curve_data_type"] = "fitted_curve"
        result = qa(d)
        self.assertTrue(any("missing 1" in r["description"] for r in result["review_queue"]))

    def test_minor_vocabulary_does_not_block_complete(self):
        d = fixture()
        d["samples"][0].update(soil_type_normalized="other", soil_type_normalization_status="unmapped")
        for index in range(5):
            r = copy.deepcopy(d["soil_properties"][0])
            r.update(property_id=f"mineral_{index}", property="mineral_fraction", property_reported="矿物含量",
                     value=index + 1, original_value=index + 1, unit="percent", original_unit="percent",
                     unit_reported="%", mineral_name_reported=f"未知矿物 {index}", mineral_name_normalized="other")
            d["soil_properties"].append(r)
        result = qa(d)
        self.assertEqual(result["review_queue"], [])
        self.assertEqual(result["paper"]["extraction_status"], "complete")

    def test_ambiguous_auxiliary_density_is_important_not_critical(self):
        d = fixture()
        prop = copy.deepcopy(d["soil_properties"][0])
        prop.update(property_id="rho_unknown", property="other", property_reported="average density", definition_status="uncertain")
        d["soil_properties"].append(prop)
        result = qa(d)
        self.assertEqual([r["severity"] for r in result["review_queue"]], ["important"])
        self.assertEqual(result["paper"]["extraction_status"], "complete")

    def test_physical_conflict_still_blocks_derivation(self):
        d = fixture()
        prop = copy.deepcopy(d["soil_properties"][0])
        prop.update(property_id="rho_conflict", value=1500, original_value=1500)
        d["soil_properties"].append(prop)
        self.assertTrue(any("conflicting" in error for error in issues(d)))

    def test_simple_unit_changes_need_no_derived_records(self):
        d = fixture()
        d["derivations"] = []
        p = d["uwc_points"][0]
        d["curves"][0]["uwc_basis"] = "volumetric"
        p.update(uwc_original_value=16.92, uwc_original_unit="percent", uwc_original_basis="volumetric",
                 uwc_preferred_value_source="reported", uwc_derivation_id=None,
                 temperature_original_value=271.15, temperature_original_unit="kelvin")
        d["uwc_points"][0] = normalize_point(p)
        density = d["soil_properties"][0]
        density.update(original_value=1.6, original_unit="gram_per_cubic_centimeter", normalized=True)
        self.assertEqual(issues(d), [])
        self.assertAlmostEqual(d["uwc_points"][0]["uwc_preferred_value"], .1692)
        self.assertEqual(d["derivations"], [])
        d["uwc_points"][0]["uwc_preferred_value"] = .2
        self.assertTrue(issues(d))

    def test_unconvertible_observations_remain_numeric_in_excel_view(self):
        d = fixture()
        d["derivations"] = []
        d["uwc_points"][0].update(uwc_preferred_value=None, uwc_preferred_unit=None, uwc_preferred_basis=None,
                                 uwc_preferred_value_source=None, uwc_derivation_id=None)
        block = curve_blocks(d)[0]
        self.assertEqual(block["pairs"], [(-2, .2)])
        self.assertEqual(block["uwc_heading"], "w_u, dry mass (kg/kg)")
        d["uwc_points"][0].update(uwc_original_unit="other", uwc_original_unit_reported="原文自定义单位")
        self.assertIn("原文自定义单位", curve_blocks(d)[0]["uwc_heading"])

    def test_high_confidence_digitization_needs_no_overlay(self):
        d = fixture()
        c, p = d["curves"][0], d["uwc_points"][0]
        c.update(extraction_method="pdf_vector", digitization=blank("digitization", coordinate_system="image_pixels",
            x_axis_scale="linear", y_axis_scale="linear", x_axis_orientation="normal", y_axis_orientation="normal",
            x_calibration_points=4, y_calibration_points=4, x_calibration_residual_px=.1, y_calibration_residual_px=.1,
            axis_confidence="high", calibration_artifact=".internal/calibration.json", benchmark_status="pending"))
        p.update(extraction_method="pdf_vector", value_source="figure_digitized", temperature_value_source="figure_digitized")
        result = qa(d)
        self.assertEqual(result["review_queue"], [])
        self.assertEqual(result["paper"]["extraction_status"], "complete")
        c["digitization"]["axis_confidence"] = "low"
        self.assertTrue(any(r["issue_type"] == "axis_uncertain" and r["severity"] == "critical" for r in qa(d)["review_queue"]))

    def test_production_does_not_call_expensive_pdf_paths(self):
        import pymupdf as fitz
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "test.pdf"
            with fitz.open() as doc:
                for text in ("UWC freezing thawing", "Unrelated mechanical model", "Scanned page candidate"):
                    doc.new_page().insert_text((30, 50), text)
                doc.save(source)
            with patch.object(fitz.Page, "get_drawings", side_effect=AssertionError("Eager vectors")), patch.object(fitz.Page, "find_tables", side_effect=AssertionError("Eager tables")), patch.object(fitz.Page, "get_pixmap", side_effect=AssertionError("Eager screenshot")):
                output = prepare(source, "fast", Path(tmp) / "output")
            self.assertFalse(list(output.rglob("*.png")))
            self.assertFalse((output / "original.pdf").exists())

    def test_only_two_production_files_and_no_point_warnings_explosion(self):
        d = fixture()
        d["derivations"] = []
        p = d["uwc_points"][0]
        p.update(uwc_original_value=-.01, uwc_preferred_value=None, uwc_preferred_unit=None,
                 uwc_preferred_basis=None, uwc_preferred_value_source=None, uwc_derivation_id=None)
        d["uwc_points"] = [dict(p, point_id=f"pt_{i}", point_index=i) for i in range(1, 101)]
        with tempfile.TemporaryDirectory() as tmp:
            result = export(d, tmp)
            self.assertEqual(len(result["review_queue"]), 1)
            self.assertEqual({p.name for p in Path(tmp).iterdir() if p.is_file()}, {"paper_test_UWC.xlsx", "paper_test_report.md"})


if __name__ == "__main__":
    unittest.main()
