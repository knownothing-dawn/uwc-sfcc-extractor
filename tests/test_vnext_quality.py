"""Regression tests for v1.6 raw/axis/numerical/physical safety gates."""
import copy
import unittest
from unittest.mock import patch

from branch_tracking import track_two_branches
from hardening import prepare_scientific
from quality import qa
from test_extractor import fixture


def run_vnext(data):
    data["schema_version"] = data["vocabulary_version"] = "1.6.0"
    with patch("sources.targeted_search", return_value=([], [], [])):
        return qa(prepare_scientific(data, "."))


def anchors(curve):
    curve["digitization"].update(
        x_axis_anchors=[{"coordinate": x, "value": x, "label_reported": str(x), "evidence_ids": ["ev_1"]} for x in (0, 1, 2)],
        y_axis_anchors=[{"coordinate": y, "value": y, "label_reported": str(y), "evidence_ids": ["ev_1"]} for y in (0, 1, 2)])


class VNextQualityTests(unittest.TestCase):
 def test_axis_counts_without_explicit_anchors_fail_vnext(self):
    data = fixture(); curve = data["curves"][0]
    curve.update(extraction_method="pdf_vector", digitization={
        "coordinate_system":"pdf_points", "x_axis_scale":"linear", "y_axis_scale":"linear",
        "x_axis_orientation":"normal", "y_axis_orientation":"normal", "x_calibration_points":3,
        "y_calibration_points":3, "x_calibration_residual_px":.1, "y_calibration_residual_px":.1,
        "axis_confidence":"high", "calibration_artifact":"cal.json", "trace_artifact":None,
        "overlay_path":None, "normalized_error_tolerance":None, "benchmark_status":"pending",
        "benchmark_reference":None})
    data["uwc_points"][0].update(extraction_method="pdf_vector", value_source="figure_digitized",
                                  temperature_value_source="figure_digitized")
    result = run_vnext(data)
    self.assertEqual(result["qa_gates"]["axis_anchor_validation"], "fail")
    self.assertFalse(result["paper"]["database_ready"])


 def test_initial_water_upper_bound_is_blocking(self):
    data = fixture(); data["soil_properties"].append({**copy.deepcopy(data["soil_properties"][0]),
        "property_id":"theta0", "property":"initial_volumetric_water_content", "value":.15,
        "original_value":.15, "unit":"cubic_meter_per_cubic_meter", "original_unit":"cubic_meter_per_cubic_meter"})
    result = run_vnext(data)
    self.assertEqual(result["qa_gates"]["physical_quality"], "fail")
    self.assertTrue(any(r["issue_type"] == "initial_water_content_exceeded" for r in result["review_queue"]))


 def test_branch_tracker_preserves_candidate_identity(self):
    columns = [[(0, 0.1, "a0"), (0, 0.3, "b0")], [(1, 0.12, "a1"), (1, 0.28, "b1")],
               [(2, 0.14, "a2"), (2, 0.26, "b2")]]
    result = track_two_branches(columns, (.1, .3))
    self.assertEqual([p[2] for p in result["tracks"][0]], ["a0", "a1", "a2"])
    self.assertEqual([p[2] for p in result["tracks"][1]], ["b0", "b1", "b2"])
