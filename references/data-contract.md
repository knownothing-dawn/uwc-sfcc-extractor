# Data contract

JSON is authoritative: Paper → Sample → Condition → Curve → Point, with evidence
and physical derivations. Canonical keys are English lower_snake_case and enums
come from `schemas/vocabulary.json`. Schema 1.4 also reads 1.0/1.1/1.2/1.3. Regenerate with
`python scripts/build_schema.py` after intentional schema changes. Original titles,
captions, legends, equations and evidence remain verbatim in their source language.
Unavailable scalars are null, never artificial zero. IDs are internal and unique.

## Design and coverage

Create `experimental_cases` from source design tables/captions/legends before
digitization. Each case binds a sample, varying property, source-reported label,
`variables` (property, numeric values, unit, original labels, evidence IDs),
`condition_ids`, `branches`, `curve_data_types`, and optional Celsius protocol range.
Do not omit a design condition merely because its curve was not recovered.
QA compares case values with scoped condition properties; mismatches require an
explicit source-backed `design_aliases` entry. Preserve the table value for design
and legend value for curve identity when correspondence is supported.

Evidence roles: `primary_uwc`, `validation`, `sfcc_model`, `supporting`.
Legacy datasets may provide `expected_series` in evidence, each containing
`condition_id`, `branch`, `curve_data_type`. Measured points must link a primary
UWC source; fitted/predicted series can link an inventoried SFCC model source.
Validation anchors never substitute for missing primary series.

QA stores expected/extracted/matched_curve_count, coverage_percentage,
missing_conditions, unexpected_conditions and duplicate_conditions under
`coverage`. Expected count is unique design identities; coverage is matched/
expected. No independent inventory means unknown coverage.
Exact repeated observations show once. Nonidentical datasets at the same state
require source resolution or explicit independent replicate labels. Never average
them. Curves retain `source_occurrences` with evidence, case, original legend,
relationship and source locator. A selected conflicting source is documented.

Coverage counts curves, not markers or temperature span. Inspect those against
the full primary source before setting `coverage_verified`; partial marker recovery
must still produce an explicit critical review. Missing curves or unresolved
scientific errors prevent `complete`, even if a review was acknowledged.

## Variables, properties and calculations

`raw_variable` distinguishes volumetric/gravimetric UWC, unfrozen/liquid water
saturation, normalized water content, mass fraction and unknown. Preserve
`raw_variable_reported` and `uwc_definition_reported`; set
`variable_definition_verified` only from source evidence. Su is pore-volume
fraction; it must not be relabeled θu without porosity. Without a supported
conversion Excel displays the original variable and an honest unit.

Properties use `property_scope` material/test_state and optionally
`applicable_condition_ids`. State-specific properties override sample-wide ones.
`maximum_dry_density` and `optimum_water_content` describe material compaction;
`dry_density` is the applicable specimen dry density. Uncertain/low-confidence or
conflicting inputs are ineligible. `conversion_property_ids` explicitly binds
reported inputs but cannot bypass scope/definition validation.

Schema 1.5 records `property_role`, `experiment_role` and applicability evidence.
A dry-density input for wu→θu must be `test_dry_density` and tied to the actual UWC
NMR/DSC specimen. Maximum density, natural/wet bulk density and unspecified average
density never become test dry density by numerical similarity. Physical derivations
retain sample, condition, specimen role and applicability evidence. Unresolved role
provenance leaves the original quantity unconverted.

Export applies θu = φSu only with verified Su definition and applicable reported
porosity; dry-mass UWC uses θu = wuρd/ρw. If water density is absent, the explicit
1000 kg/m³ assumption appears once in Markdown. Each physical result retains
source input IDs/fields, original values, formula, units, assumptions and result.
Derived θu materially above applicable porosity is critical. Tiny graphical Su
overshoot up to 0.01 is retained with a note, not silently clipped.

Simple K→°C, percent→fraction and density scaling preserve originals and use
normalization flags, not new derivation objects. Percent requires explicit mass
or volume meaning. Unknown basis/denominator means no forced conversion.

## Presentation

The [hardening contract](hardening.md) defines backward-compatible manifest, numerical
source, point inventory, comparison, source resolution and readiness fields.
`reference_points` preserve exact observations alongside the full original
`uwc_points`; `observation_selections` identifies which values the human view uses.

For continuous measured traces, `raw_trace_points` retains maximum recoverable
ordered geometry. Canonical `uwc_points` contains the compact scientific curve after
curve isolation, centerline construction and normalized adaptive simplification.
Per-curve
`trace_processing` records raw/centerline/export counts, reconstruction errors,
accepted/excluded/unresolved raw geometry, domain coverage, reduction ratio,
transition count, warnings and post-processing monotonicity. Raw
trace coordinates are internal and never populate Excel.

Version 1.4 separates `data_semantics` (measured/fitted/predicted/derived/unknown)
from `representation`. A continuous measured trace is not a model fit. Existing
`curve_data_type` is retained for input compatibility: use its compatible value,
or `unknown` when the legacy vocabulary cannot express the new combination.
Scientific identity uses semantics, so a table and graph may describe the same
observation. Representation does not create a second independent dataset.

Expected point information has `protocol_expected`, `reported_expected` and
`source_observable`, with separate evidence. Legacy reported_targets migrate to
protocol plans, reported_observations to hard reported expectations, and
visible_markers to observable source information. The legacy fields remain
readable; after migration edit the canonical nested fields.

The manifest also records `target_quantity_status` and `availability_status`.
Verified unavailable targets and proxy signals stay in the design inventory but
not in the available numerical-series denominator. Unavailable target data still
block whole-design autonomous import; non-target proxies do not masquerade as
missing UWC. See the hardening contract for evidence and gate requirements.

`paper.review_status` now expresses usability: database_ready, usable_with_review,
partial, insufficient. Legacy pending/approved/rejected inputs are retained as
`legacy_review_status`; they cannot grant automatic import. `database_ready` is
recomputed independently from all scientific gates.
The exporter consumes this resolved view and never assigns scientific meaning.

Default deliverables are `PaperID_UWC.xlsx` and `PaperID_report.md`.
JSON, source downloads and selected diagnostics stay in `.internal/`; no extra
default sheets, source PDF copies, screenshots or overlays.

One `UWC_SFCC` worksheet contains:

1. Paper Information: original title/authors, year, journal, DOI, method and
   coverage summary; wrap long text.
2. Basic Soil Properties: one row/material; available LL/PL/PI, optimum water
   content, maximum dry density, Gs, porosity, SSA, grain-size fractions, void ratio.
   Omit universally absent columns; do not duplicate material rows for states.
3. Test Conditions: compact source-design cases and parameter lists, test dry
   density and protocol temperature range. Do not expand each combination to a row.
4. UWC/SFCC Data: experimental factor → soil → adjacent Temp–θu pairs; fixed
   conditions at group level and only the varying condition in each title.

At most four two-column blocks per band; wrap additional blocks below. Preserve
separate branches, measured/fitted types and independent replicates. A common
single cycle is omitted; distinct cycles must remain identifiable. Already shown
conditions are referenced without repeating points; missing conditions are visible.
Preserve point_index including duplicate temperatures; otherwise sort by thermal
direction with each numeric pair intact. No interpolation or production resampling.

Use Calibri, dark-blue paper header, muted gold property/condition sections,
light-blue UWC/factor headers, soft-green material headers, pale-grey curve
headers, white data cells. Center numeric data, wrap text, modest row heights,
one or two blank rows. UWC four decimals, density/porosity three; display rounding
does not change stored values. Keep internal IDs/calibrations out of Excel.
Source strings beginning with `=` are text, not formulas. Lossless originals stay
in JSON when Excel cannot represent a string.

Condition display binds value, unit, basis and precision atomically. When the
source reports `15.62%`, the curve title preserves that reported value and unit.
If a normalized fraction is shown instead, its numeric value, normalized unit and
precision are derived together; reported and normalized components are never mixed.

Markdown contains Paper, Summary, UWC Sources, Variable handling, Conflicts/Notes,
Manual review. Preserve source captions. State physical conversions once, group
repeat warnings, keep resolved label conflicts in notes and only actionable
critical/important items in review. No dump of missing optional properties or
per-point derivations. Translation is display-only and never evidence.
