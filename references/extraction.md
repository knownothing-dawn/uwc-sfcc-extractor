# UWC-first extraction scope

Extract the primary UWC dataset before optional descriptive material. Inspect
the whole source inventory sufficiently to identify all relevant figures/tables,
but do not fully structure unrelated paper sections.

## Source priority and coverage

First compare coverage: conditions, freezing/thawing branches, cycles, temperature
range, measured versus fitted/predicted. For equivalent observations, prefer raw
supplementary numbers, tables, explicit labels/text, vector coordinates, raster
markers, then continuous tracing. Numerical precision does not replace coverage.
Check the paper's explicitly linked raw repository/supplementary files first.
Create a design inventory before point recovery; never count only extracted curves
as expected. Preserve absent states and source-specific conflicting labels.

Example: Fig. 9 has five suction conditions with freezing and thawing measured
curves; Fig. 10 gives fits; Fig. 12a prints values at three temperatures. Plan ten
measured series from Fig. 9. Use Fig. 12a as matched validation anchors and Fig. 10
for directly relevant model/fitting information. Do not treat them as three
independent experiments. Match validation anchors only when sample, condition,
branch, cycle, method and basis agree. Flag discrepancies; do not overwrite one
source or select the easier plot silently.

Bind sample/condition/method/branch/cycle/origin before acquiring coordinates.
Extract observed marker centers only, with no inserted measured points. Keep
fitted and predicted records separate. Original-data and reproduced-literature
provenance must remain explicit. No generation from equations unless requested.

## Restricted content

Attempt original title, complete authors, first author, year, journal, volume,
issue, pages, DOI, language, citation; method, soil type, relevant properties,
conditions and initial freezing temperature. Preserve all original wording.
Collect only models that describe UWC/SFCC or are needed to compute/interpret it.
Skip unrelated SWCC, strain, mechanical, thermal, SEM/CT and reference analysis.

Relevant properties can include density, moisture, suction, salinity, porosity,
SSA, consistency limits, composition and dimensions. Use existing `other` plus
`property_reported` for additional terms instead of expanding vocabularies per
paper. Unmapped minerals and correctly retained reported names do not need action.

Assign a scientific role to every density used for interpretation: test dry
density, maximum dry density, natural/wet bulk density, particle density, specific
gravity or an explicitly unspecified basis. Also record the experiment role (UWC
NMR/DSC, triaxial, SWCC, shear, compaction or general material). Do not transfer a
property from an adjacent experiment merely because its value is physically
plausible. Preserve source condition text and decimal precision independently from
digitized curve precision.

## Calculations and review

Simple unit changes create normalization flags, not derivation objects. Scientific
identities supported by `science.py` include θu = φSu with verified pore-volume
Su and specimen-applicable porosity, volumetric UWC from dry-mass UWC and
dry density, porosity from densities, void ratio from porosity/densities, saturation
from volumetric moisture and porosity, wet density from dry density and total
dry-basis moisture, and particle density from specific gravity. Definitions and
sample/condition scope must agree. Water density may be assumed 1000 kg/m³ only
when explicitly recorded. Ambiguous dry/wet density is retained but not used.

Critical: wrong/missing primary curves, uncertain identity, branch, axes, source
transcription affecting UWC, overlapping unresolved series, conflicting reported
values, unresolved UWC definitions, invalid physical conversions. Important: auxiliary density
basis, incomplete contextual conditions or physical warnings. Note: safely retained
unmapped terms, resolved table/legend differences, small retained Su overshoot,
or nonessential units. Notes do not add open review tasks. Never use maximum dry
density for specimen conversion or conductivity as a missing Su series.

Physical and monotonicity warnings retain observations. Review reports group
repeat warnings by curve. A few safe terminology gaps must not turn a complete
UWC extraction into manual_review_required. Missing primary data must remain
visible regardless of the number of successfully extracted validation values.
