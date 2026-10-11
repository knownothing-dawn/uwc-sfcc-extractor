# Digitization on demand

Select the complete primary UWC source first. For its numerical acquisition,
prefer direct data, then PDF paths, raster markers, continuous raster traces.
`geometry.py` is unchanged: semantic legend/series selection remains agent work.

Use `uwc.py inspect PACKAGE --pages ... --vectors` only for selected plot pages;
use `--tables` only for selected numerical-table pages. `--render` is explicit
when visual inspection/raster processing is needed, not a default page export.
Outputs stay under `.internal/pages`. The coordinate metadata records unrotated
PDF points and, when rendered, a scale of 2 pixels per PDF point.

1. Match source caption, plot/legend, sample, condition, branch, cycle and method.
2. `calibrate_axis(anchors, scale, max_residual_px)` uses at least three ticks.
   Linear, reversed linear and positive log axes are supported. Broken/ambiguous
   dual axes and negative-log conventions require reviewed explicit mappings.
3. `vector_polylines` flattens actual cubic paths; Bézier control points are not
   observations. It preserves disconnected paths. Check visibility/clipping and
   style against the source instead of assuming all paths are actual curves.
4. `marker_centers` accepts an isolated verified marker mask; remove axes, labels,
   connecting lines and error bars first. Keep accepted centers only.
5. `trace_columns` supports one isolated continuous single-valued raster curve.
   Gaps, crossings and multiple runs are refused rather than silently bridged.
6. Continuous fitted/predicted curves use `adaptive_indices` in normalized data
   coordinates with explicit tolerance, preserving endpoints and extrema. No
   default fixed point count or temperature interpolation; no marker resampling.
7. Continuous measured traces pass through `trace_processing.py` after coordinate
   conversion. Before centerline construction, `curve_isolation.py` compares
   series in the same panel, removes sustained shared-path contamination and
   foreign local path excursions, and marks unresolved overlapping candidates.
   One-point crossings do not count as shared paths. Accepted components are
   processed independently so excluded geometry cannot shift the centerline.
   It then validates trace order, removes line-width duplicates only under
   an explicit single-valued assumption, applies conservative local denoising,
   protects high-slope/curvature transitions, and simplifies in normalized
   coordinates. Dense raw points remain in `raw_trace_points`; `uwc_points` is the
   scientific curve used by QA and Excel. Loops or discontinuities use segmented
   geometry. Raw-to-centerline P95 orthogonal error and centerline-to-scientific
   reconstruction error are separate QA stages. Failed fidelity/reconstruction or
   an unsimplified dense export blocks readiness. Partial/ambiguous isolation is
   retained as review-required provenance and cannot grant autonomous import.

Preserve calibration/trace evidence internally. Production does not require an
overlay for a reliable curve and does not raise missing_overlay review tasks.
`save_overlay` is available for benchmark/debug, a user-requested review, uncertain
axes or curve identity, overlaps or low confidence. Do not create it by default.
Pending literature benchmark validation is disclosed once as a limitation; it
does not generate one manual-review task per otherwise reliable series. Never
misstate candidate tolerances as scientifically validated.

The benchmark harness is development-only; importing/running it is not part of
normal production. Geometry and scientific calculations are not approximated
or weakened for speed.
