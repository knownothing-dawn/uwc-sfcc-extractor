# Evidence and readiness contract

These checks operate on structured observations and a short agent source pass.
They do not replace the digitizer or require repeated whole-document reading.
Consult `schemas/paper.schema.json` for exact required fields and enums.

## Before digitization

Build `expected_datasets` from `experimental_cases`, source `expected_series`, or
an explicitly evidence-backed manifest. Never build the denominator from extracted
curves. Each entry includes:

- `expected_curve_id`, `sample_id`, `condition_id`, `experimental_factors`;
- `condition_values` with original evidence bindings;
- `branch`, `curve_data_type`, `expected_source_ids`, `evidence_ids`;
- `measurement_status` and `expected_point_information`.

Record independent `data_semantics` (measured, fitted, predicted, derived,
unknown) and `representation` (discrete_markers, continuous_measured_trace,
continuous_model_curve, tabulated_points, explicit_numeric_labels, equation_only,
unknown). A DSC experimental function uses measured/continuous_measured_trace.
Its continuity does not imply a fit. Legacy curve types remain readable; explicit
semantics must agree with any known legacy type. Use legacy `unknown` for a
combination it cannot express. Points inherit the curve's scientific meaning.

Record `target_quantity_status`: direct_target_quantity, derived_target_quantity,
proxy_signal_only or unknown. Record `availability_status`: available,
partially_available, reported_but_not_numerically_available, not_found_in_source
or not_applicable. Legacy entries default conservatively to unknown/available.

A proxy without a supported UWC conversion is documented, not counted as an
expected numerical UWC series. Numerically unavailable target data likewise stay
in the design inventory but outside the extraction denominator. These exclusions
require `availability_evidence_ids` and `availability_explanation`; never infer
unavailability merely because an extraction attempt returned no points. Preserve
the distinction between total design count and available numerical-series count.
Unavailable target series still block whole-design database readiness without a
Critical claim that nonexistent source values were missed. Partially available
targets stay in the numerical denominator and require source review.

Independent model/method variants at the same physical condition may use
`series_variant_reported`, preserving their original distinguishing legend label.
Use the same verified variant on the expected entry, curve and numerical source.
Do not create variants just to conceal conflicting repeats. Unknown-basis but
reported condition values remain part of condition identity.

Exclude a design condition only with `measurement_status: explicitly_not_measured`,
`exclusion_reason_reported` and verified `exclusion_evidence_ids` containing that
explicit source statement. A missing plotted curve is not proof it was unmeasured.

For point information use the three sets below. For continuous traces with no
meaningful observation count, inspect the full trace and report source completeness;
sampled trace coordinates are not an experimental observation denominator.

## One targeted missing-curve recovery

Export compares the manifest with primary measured/model records. A verified
`numerical_datasets` entry marked `coverage_role: full_series` can recover an absent
curve. `anchors_only` never substitutes for a complete series. Original values and
source locators are retained. Method, branch, cycle, variable and condition bindings
must agree; conflicting equal-priority sources are not automatically chosen.

An explicit `table_binding` can read a local XLSX/CSV/TSV range using SHA256,
sheet, row bounds, one-based temperature/value columns and units. Each workbook
opens once per preparation. The command never discovers arbitrary external files
or fetches a repository. The agent checks the paper's explicit supplementary/data
links before digitization and binds any retrieved source.

If no full numerical source matches, the retry reads only bound source pages from
cached text or selected PDF pages and records `recovery_attempts`. For
`targeted_review_required`, inspect that figure/table/legend/condition, then record
the result as `recovered`, `not_found`, `ambiguous` or `source_unavailable`. An
unchanged failed attempt is not rerun on each export. Changed source inputs allow
a fresh bounded attempt. `python scripts/uwc.py recover DATASET.json` updates the
internal dataset; it does not export extra user artifacts.

## Point/source completeness

`expected_point_information` contains:

- `protocol_expected`: planned counts/temperatures, with evidence.
- `reported_expected`: observations expressly reported for that particular series,
  or verified complete structured numerical rows; these establish a hard denominator.
- `source_observable`: identifiable source points, with evidence and `completeness`
  complete/partial/unknown. A count of identified points can be a lower bound when
  the source is incomplete. It is not proof that every protocol measurement appears.

Each set has `count` (nullable), `temperatures_celsius` and `evidence_ids`. Do not
infer reported_expected from the protocol or from how many points were extracted.
For continuous curves, leave the count null unless it has a defensible meaning.

`point_coverage` compares temperatures one-to-one within the configured tolerance.
Missing reported or independently source-identifiable observations block point
completeness. Protocol differences are provenance information, not Critical errors.
Only `protocol_applies_to_output: true` with a verified verbatim
`protocol_output_statement_reported` and `protocol_output_evidence_ids` can make
the protocol a hard output-series requirement. A hard reported gap cannot be
cleared simply by saying the point is absent from the available source.

Never interpolate missing observations. Partial or unknown source completeness
does not pass merely because protocol and extracted counts happen to agree.
Verified complete sources may legitimately contain fewer points than the protocol.
Legacy expectation fields are readable and preserved; canonical nested fields take
precedence after migration. Compatibility counters now count hard expectations,
while protocol differences have separate counters.

## Numerical sources and anchors

Priority is structured raw/supplementary data → table → printed numerical label →
explicit text → plotted marker → continuous trace. Use `numerical_datasets` with
source kind, scientific identity, original variable, source locator, evidence and
observations; retain source text and original numeric units. Resolve the variable
from definitions/axes/methods/captions, never from magnitude. Unverified numerical
sources block readiness instead of silently disappearing.

Match an anchor to a unique material/condition/variant/branch/cycle/data-type/method/
origin/variable/temperature observation. Unit-compatible values are normalized;
the implementation conservatively flags different physical bases for review.
Store exact `reference_points`, full `anchor_checks` and `observation_selections`.
Keep every original graphical point in `uwc_points`. Highest-priority exact values
control overlapping output pairs; equal-priority conflicts receive no automatic
selection. Never average sources or shorten a graph to its anchors.

Default `qa_settings`:

| Field | Default |
| --- | ---: |
| temperature_match_tolerance_celsius | 0.15 |
| volumetric_warning_threshold | 0.003 m³/m³ |
| volumetric_strong_threshold | 0.010 m³/m³ |
| normalized_warning_threshold | 0.01 of plotted axis span |

Thresholds use strict greater-than with numerical roundoff protection. Set
`plotted_uwc_axis_span` and `plotted_uwc_axis_unit` from the actual axis for the
normalized check; never estimate the span from extracted extrema. Absolute
volumetric thresholds apply only to θu comparisons. Report max/mean errors only
within the same unit; never pool incompatible units.

Review significant discrepancies and neighboring points. Recalibrate only when
the evidence shows a systematic error. A source decision requires
`anchor_resolutions`: check ID, `neighbor_points_checked`, verified evidence,
explanation, resolution and `comparison_fingerprint`. Generate the latter with
`sources.comparison_fingerprint(check, original_point, reference_point)` after
inspection. Changed observations invalidate the earlier decision. Merely marking
an auto-generated critical review resolved cannot override an unresolved conflict.

## Variables, properties and readiness gates

Keep Su, liquid-water saturation, dry-mass wu, volumetric θu, normalized water
content, wet-mass fraction and unknown variables distinct. The resolver records
the evidence-assigned basis; it does not infer semantics. Source wording remains
in `raw_variable_reported`/`uwc_definition_reported`. Physical conversion keeps
input provenance; simple unit scaling does not create verbose derivations.

Make one focused relevant-property pass. Preserve an uncertain reported water
content/density as `other`, `definition_status: uncertain`, with source wording;
do not calculate from it. Such values normally produce important notes. Use
`property_scope`, `property_role`, `experiment_role` and applicability evidence.
Only a role-compatible UWC specimen dry density may support wu→θu. A compaction
maximum, natural/wet bulk density or unspecified average density is ineligible
unless the source separately and explicitly binds it as the UWC specimen state.

For a continuous measured trace, retain ordered dense coordinates internally and
isolate curve-local geometry before centerline construction. Sustained shared
paths and foreign local excursions are excluded; isolated crossings are retained.
Ambiguous overlapping candidates remain explicitly unresolved. Build a compact
scientific curve only from accepted components before monotonicity QA or Excel
export. Raw candidate counts describe recoverable geometry and never become a hard
experimental point denominator. The trace
gate passes only when reconstruction error is within the configured normalized
tolerance and the raw trace was not exported unsimplified. The default tolerance
is 0.005 of normalized axis span and remains configurable. Transition regions use
a tighter local tolerance; flat tails simplify more strongly. Do not force
monotonic correction.

Raw-to-centerline fidelity uses orthogonal distance in the same normalized plot
coordinates. Store median, mean, P95 and maximum distance. The default warning
threshold is P95 > 0.01 normalized units; configure it with
`trace_centerline_fidelity_p95_threshold_normalized`. The robust P95 threshold
tolerates ordinary symmetric line thickness while surfacing centerline shifts.
It does not alter coordinates; a warning requires review and blocks autonomous import.

Set `source_inspection.point_inventory_checked`, `anchor_search_completed`, and
`property_pass_completed` only after these checks, with verified evidence IDs.
QA derives the five source/science gates plus trace and derivation-provenance gates:

1. Evidence-backed expected/extracted curve identities agree.
2. No unexplained expected-point gaps, and source completeness was inspected.
3. No unresolved significant numerical-source conflicts or unavailable bindings.
4. Original scientific variables and physical conversions are valid.
5. Source, paper, material, method, branch, main conditions and relevant-property
   inspection are identifiable.
6. Every explicitly configured continuous measured trace passes raw-to-centerline
   fidelity and centerline-to-scientific reconstruction QA.
7. Physical UWC conversions have verified sample/condition/specimen applicability.

`database_ready` is true only when all gates pass and no critical review is open.
Otherwise preserve `partial`, `manual_review_required`, `metadata_only` or
`not_relevant`, as applicable. Important issues alone do not block otherwise valid
data. The scientific readiness status is distinct from software release maturity.

`paper.review_status` serves the workflow Skill → human review → master Excel:

- database_ready: all autonomous-import gates pass.
- usable_with_review: identifiable UWC data exist, but review/checks remain.
- partial: a usable subset exists with missing/unavailable target series, known
  source incompleteness, hard point gaps or an incomplete whole-paper inventory.
- insufficient: no numerically populated series has enough identified semantics,
  variable, branch and evidence for a usable subset.

Usability never grants `database_ready`. Legacy human approval is kept separately
as `legacy_review_status`, not translated into either scientific approval or data.
The state appears in Markdown and internal JSON; the Excel architecture is unchanged.

## Human output

Keep the existing four-section sheet and at most four paired blocks per band.
Use one compact metadata QA line. Curve notes appear only for review or mixed
exact/graph observations; no per-point provenance columns. Markdown sections are
Paper, Extraction Summary, UWC/SFCC Sources, Variable Handling, Cross-source
Validation, Notes and Manual Review. Only XLSX and Markdown are normal visible
outputs. No production benchmark, default screenshot, overlay or extra dashboard.
