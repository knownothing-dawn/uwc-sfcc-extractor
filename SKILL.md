---
name: uwc-sfcc-extractor
description: Extract UWC/SFCC data from research PDFs, prioritizing complete primary curves and preserving source evidence, with a single-sheet paired-curve Excel and compact Markdown review output.
---

# UWC/SFCC extraction

## Release status

**UWC/SFCC Extractor v1.6.0-rc.1 — Safety-Gated Human-Reviewed Production.** Designed for:
PDF → automated UWC/SFCC extraction → Excel + concise report → human scientific
review → master database. It is not intended for fully autonomous database import
without review. See the [v1.6.0-rc.1 release notes](references/release-v1.6.0-rc.1.md)
and the [v1.0 release notes](references/release-v1.0.md), and record
recurring real-paper failures in the [v1.1 backlog](references/v1.1-backlog.md).

New extractions that claim vNext readiness must explicitly use schema/vocabulary
`1.6.0`. Legacy 1.0–1.5 packages remain readable, but their absence of vNext
metrics must not be described as passing the new numerical or physical gates.

Extract unfrozen water content and soil freezing characteristic curves accurately
with minimal preprocessing and human review. Process each paper independently.
Never modify a master database. This skill is agent-assisted: deterministic tools
acquire coordinates and calculate values; the agent interprets paper semantics.

Read [language policy](references/language-policy.md) and
[data contract](references/data-contract.md). Use the existing Python dependencies
in `requirements.txt`. Production is the default; do not add steps or artifacts
merely to make a more exhaustive paper database.

## Production workflow

1. Run `python scripts/uwc.py prepare --pdf PAPER.pdf --paper-id PAPER_ID --out OUTPUT_ROOT`.
   This reads page text once. Read `.internal/candidates.json`; keyword hits are
   navigation hints, not evidence of presence/absence. Check first-page metadata,
   UWC methods/results, figure/table references, and candidate captions. Follow
   cross-references so an unmatched page containing primary SFCC data is not lost.
2. Build `expected_datasets` from independent experimental tables, captions and
   legends before extracting points. Preserve design values and condition/branch/
   type membership in `experimental_cases`, including missing conditions. Never
   derive the expected count from recovered curves. Check the paper's Data
   Availability statement and explicitly linked supplementary/raw repository
   first; use equivalent author data before digitizing. Do not search random
   datasets. Lock the primary UWC source before auxiliary properties.
   Read [extraction rules](references/extraction.md). Distinguish full measured
   SFCC curves from validation anchors and fitting/model sources. A few printed
   values cannot replace a fuller freezing/thawing figure. Record source roles
   and the expected condition × branch × data-type series in the evidence record.
   Read [scientific hardening](references/hardening.md) for manifest, point
   expectations, bounded recovery, exact-source matching and readiness gates.
   Distinguish the full design inventory from available numerical target datasets.
   Record target-quantity and availability status with evidence; proxy signals
   without a supported UWC conversion are not expected numerical UWC series.
3. Create only the sample/condition/curve records needed to bind those series.
   Acquire the primary measured points first, using complete numerical sources
   when available. Keep fitted/predicted data distinct. Do not duplicate the same
   observations from a primary figure, its fitted representation, and validation
   chart. Retain `source_occurrences`; exact repeated observations display once.
   Conflicting repeats require a documented source choice, never averaging.
   Preserve titles, captions, legends, equations and quotes verbatim. When table
   and legend labels differ, retain both: table for design, legend for identity,
   with evidence-linked `design_aliases` if correspondence is resolvable.
   Record independent `data_semantics` and `representation`: a continuous measured
   experimental trace is measured, not fitted. Retain compatible legacy curve types.
   Separate protocol plans, explicitly reported observations and source-observable
   points; a protocol temperature list alone is not a hard missing-point denominator.
4. Use expensive PDF operations only on selected pages, as needed:
   `python scripts/uwc.py inspect PACKAGE_DIR --pages 5 9 --tables --vectors`.
   Request only the necessary flags. Do not run both table detection and vector
   extraction on every page. Read [digitization](references/digitization.md) when
   figures are actually needed. Use `--render` only for a required visual/raster
   inspection; keep that work internal. High-confidence production extraction
   requires no screenshot or overlay deliverable.
   For a verified `continuous_measured_trace`, set `trace_geometry` explicitly.
   Export first isolates each named curve from sustained shared paths, foreign
   local excursions and ambiguous overlapping candidates. A single geometric
   crossing is retained. It then preserves dense coordinates in
   `raw_trace_points` and uses the
   compact reconstructed `uwc_points` scientific curve. Do not place raw raster/
   vector trace coordinates in Excel. Review raw-to-centerline P95 orthogonal error,
   isolation exclusions/unresolved segments, simplified reconstruction error,
   reduction, transition retention and post-processing monotonicity.
   For every digitized v1.6 curve, store at least three independent labelled
   ticks per axis in `x_axis_anchors` / `y_axis_anchors`, including coordinate,
   reported label and evidence. Calibration-point counts and self-reported
   residuals alone are insufficient. Retain raw candidates before normalization,
   resampling, interpolation or smoothing. For same-style freezing/thawing
   markers, track the pair jointly with candidate identity and branch continuity;
   do not independently select an upper/lower envelope at each temperature.
   When branch evidence is insufficient, preserve the candidates and unresolved
   interval and stop automatic database promotion.
   Preserve `candidate_id`, `component_id` and `path_position` whenever the source
   exposes them. For evidence-backed branch seeds, use joint candidate-graph
   assignment: one candidate has one final owner unless the source explicitly
   supports `confirmed_shared`. Near-vertical segments use 2-D path order/arc
   length, not x-column collapse. Every unresolved or fidelity-failed segment must
   have an internal trace diagnostic. An accepted segment whose raw-to-centerline
   P95 exceeds the configured contract is moved to unresolved; do not smooth it
   into compliance.
5. Add necessary bibliography, UWC measurement method, soil properties, conditions,
   freezing temperature and directly relevant UWC/SFCC models. Skip unrelated
   SWCC/strain/thermal/SEM/CT models and exhaustive references unless needed to
   understand or compute UWC. Do not postpone primary curves for vocabulary cleanup.
   Make one focused pass over materials/methods/property tables. Retain reported
   values with unspecified bases as such; never infer dry density from an unlabeled
   density. Bind specimen dimensions to the UWC experiment, not adjacent tests.
6. Identify the original variable: Su (water/pore volume) is not θu (water/total
   specimen volume). Set `raw_variable`, verify its definition and bind applicable
   porosity for θu = φSu, or test dry density for θu = wuρd/ρw.
   `maximum_dry_density` never substitutes for `dry_density`. Record `property_role`,
   `experiment_role`, applicability evidence and material versus test-state scope.
   Dry density may support a UWC conversion only when bound to the actual UWC
   specimen and a compatible method role. Export applies supported conversions and retains originals.
   Uncertain applicability means no forced conversion.
   Use `scripts/science.py` for conversion. Simple unit scaling uses normalization
   flags and preserved original values; it creates no derivation object. Genuine
   physical calculations keep input/formula/assumption metadata. Unknown basis
   means no forced conversion. No production interpolation or default model data.
7. Save the internal dataset at `.internal/PAPER_ID_UWC.json`, then run
   `python scripts/uwc.py export PACKAGE_DIR/.internal/PAPER_ID_UWC.json --out PACKAGE_DIR`.
   Export performs validation and QA once; a separate preceding `validate` run is
   unnecessary. Use `validate` only for diagnosing or checking an edited dataset.
   Export performs one targeted numerical recovery attempt for missing manifest
   entries. A `targeted_review_required` result needs a narrow source revisit by
   the agent; no whole-document retry or fabricated point is allowed. Exact
   anchors control matching output observations while originals remain stored.
8. Inspect `PAPER_ID_UWC.xlsx` and `PAPER_ID_report.md`. Excel contains one
   `UWC_SFCC` sheet with Paper Information, Basic Soil Properties (one row/material),
   Test Conditions (compact design cases), and UWC/SFCC Data. Group by experimental
   factor → soil, with adjacent Temp–UWC pairs and at most four blocks per band. Use actual
   distinguishing conditions as titles; keep freezing/thawing and measured/fitted
   curves separate. Preserve recorded point sequence and numeric pairing.
   Source details and review are in Markdown. Check every planned
   condition/branch series, its point count and source. Check expected/extracted
   counts, coverage and missing/unexpected/duplicate conditions; never claim completeness
   merely because supporting values were extracted. If a whole series or individual
   markers could not be recovered, record that limitation rather than fabricate data.
   Set the three `source_inspection` flags only after the relevant work is done.
   Read `point_coverage`, `anchor_summary`, `numerical_quality`, `qa_gates` and
   `paper.database_ready`:
   100% curve coverage alone is insufficient. A missing or unperformed gate never
   grants readiness; acknowledging a critical issue does not repair the data.
   Also report `paper.review_status`: database_ready, usable_with_review, partial
   or insufficient. This describes human-review usability and never overrides the
   autonomous-import gates. Document unavailable target series without labeling
   them failed extractions; retain their effect on whole-design import readiness.
   Preserve source condition precision with `values_reported` / `reported_precisions`;
   digitized curve values keep their separate display precision. Treat condition
   value, unit, basis and precision as one display binding: a reported percent
   stays a percent label, while normalized values use their normalized unit and
   independently computed precision.
   For v1.6, separately report `detection_completeness`,
   `axis_anchor_validation`, `numerical_quality` and `physical_quality`. Inspect
   every curve's reverse jumps, initial-water upper-bound exceedance and raw-layer
   retention, plus every freezing/thawing pair's exact/near duplicate fraction
   and branch-order switches. Run these checks before any presentation-grid
   interpolation. A severe local error blocks readiness even when aggregate MAE
   or curve coverage is acceptable.

Missing-series-only critical issues produce `partial`; other `critical` issues
produce `manual_review_required`. Both have `database_ready: false`. `important`
issues affect interpretation but do not automatically block reliable UWC data.
Safely preserved unmapped terms are notes, not review tasks. Group repeated point
warnings by curve. Keep internal IDs, JSON and calibration details out of the
normal user-facing results. Never hide missing data by suppressing critical issues.

## Development only

`--mode benchmark` permits the full diagnostic preparation path. Overlays,
pixel coordinates and WebPlotDigitizer comparisons are for benchmark/debug or
an actual uncertain-figure review, not normal output. No benchmark runs during
production. Read [benchmark requirements](references/benchmark.md) only for that work.
Run `python -m unittest discover -s tests -v` for software regression checks.
Use `scripts/release_check.py` to synchronize the README/release test count from
that canonical command. Geometry-versus-manual metrics are benchmark-only and
must never enter production readiness.
See [implementation status](references/implementation-status.md) for limitations.
