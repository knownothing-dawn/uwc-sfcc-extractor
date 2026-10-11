"""v1.0 release-report semantics; production geometry remains frozen."""
import unittest

from test_final_hardening import dense_trace
from test_hardening import graphical, run
from hardening import trace_review_text
from reporting import markdown_report


def trace(**updates):
    value = dict(status='review_required', warnings=[], isolation_warning_codes=[],
        curve_isolation_status='pass', unresolved_segment_count=0,
        max_normalized_reconstruction_error=.001,
        simplification_tolerance_normalized=.005,
        raw_to_centerline_p95_normalized_error=.001,
        centerline_fidelity_p95_threshold_normalized=.01)
    value.update(updates)
    return value


class TraceReviewMessageTests(unittest.TestCase):
    def test_unresolved_isolation_is_not_called_reconstruction_failure(self):
        description, _ = trace_review_text(trace(
            warnings=['unresolved_curve_isolation'], curve_isolation_status='partial',
            unresolved_segment_count=2))
        self.assertIn('unresolved curve-isolation', description)
        self.assertNotIn('reconstruction QA', description)

    def test_centerline_fidelity_is_not_called_reconstruction_failure(self):
        description, _ = trace_review_text(trace(
            warnings=['centerline_fidelity_warning'],
            raw_to_centerline_p95_normalized_error=.02))
        self.assertIn('raw-to-centerline fidelity', description)
        self.assertNotIn('reconstruction QA', description)

    def test_true_reconstruction_failure_is_named_reconstruction(self):
        description, _ = trace_review_text(trace(
            max_normalized_reconstruction_error=.006))
        self.assertIn('scientific-curve reconstruction QA', description)


class CompletenessWordingTests(unittest.TestCase):
    def test_unresolved_continuous_geometry_is_separate_from_reported_points(self):
        result = run(dense_trace())
        stats = result['curves'][0]['trace_processing']
        stats.update(status='review_required', curve_isolation_status='partial',
                     unresolved_segment_count=3)
        report = markdown_report(result)
        self.assertIn('Reported-point completeness:', report)
        self.assertIn('Continuous-trace geometry:', report)
        self.assertIn('3 unresolved segment(s)', report)
        self.assertNotIn('series not fully assessed', report)

    def test_discrete_point_completeness_wording_is_unchanged(self):
        report = markdown_report(run(graphical()))
        self.assertIn('Point/source completeness:', report)
        self.assertIn('series not fully assessed', report)


if __name__ == '__main__':
    unittest.main()
