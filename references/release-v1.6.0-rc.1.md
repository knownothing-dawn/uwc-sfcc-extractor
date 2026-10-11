# UWC/SFCC Extractor v1.6.0-rc.1

Release date: 2026-09-29
Maturity: Safety-Gated Human-Reviewed Production release candidate
Schema and vocabulary: 1.6.0

## Scope

This release candidate hardens continuous-trace resolution between raw candidate
acquisition and scientific-curve construction. It does not change the source
priority, scientific-variable conversions, axis calibration contract, one-sheet
Excel layout, or the requirement for human scientific review.

## Changes

- Preserves `candidate_id`, `component_id`, `path_position`, ownership and
  explicitly confirmed sharing when the source exposes them.
- Tracks freezing and thawing jointly on a two-dimensional candidate graph.
  Candidate sharing is forbidden unless supported as `confirmed_shared`.
- Preserves path order and near-vertical multi-valued geometry instead of
  collapsing every trace to a single value per temperature.
- Emits segment-level diagnostics for shared-path collisions, multimodal
  candidate sets, abrupt path discontinuities, insufficient local geometry and
  fidelity failures.
- Moves accepted segments whose raw-to-centerline P95 exceeds the configured
  contract to unresolved instead of smoothing them into compliance.
- Separates numerical equality from same-candidate reuse, confirmed physical
  overlap, suspicious shared assignment, true crossing and identity switching.
- Adds topology-aware reverse-jump reporting.
- Adds point-to-polyline and symmetric geometry metrics for offline benchmark
  analysis only; they do not affect production readiness.
- Adds a canonical release-count synchronizer and 15 trace-resolution RC tests.

## Compatibility

- New v1.6 extractions use the strict trace and scientific-quality gates.
- Legacy schema 1.0–1.5 packages remain readable and exportable.
- Legacy packages without candidate/component identity remain unresolved where
  ownership cannot be proved; absence of those fields is never reported as a
  passing v1.6 identity check.
- Candidate-graph tracking is opt-in when the required source metadata exists,
  so legacy and non-trace datasets do not acquire invented topology.

## Verification

The canonical command is:

```bash
python -m unittest discover -s tests -v
```

Maintainer full-fixture result: `Ran 180 tests` / `OK`.

The public repository discovers the same 180 test definitions, executes 158
synthetic and contract tests, and explicitly skips 22 tests whose recorded-paper
fixtures are not distributed. Public CI and private release evidence are reported
separately.

Cross-paper regression covers a simple paper fixture and two complex paper
fixtures. Their sample, condition, curve and point structures are preserved.

## Scientific release boundary

Passing the software suite does not make every extracted paper database-ready.
The Sun Yanding regression fixture retains all 3,012 raw candidates and reduces
the worst accepted raw-to-centerline P95 from 0.05745 to 0.00831, with no accepted
segment above the 0.01 fidelity limit. Its maximum offline point error remains
above the benchmark threshold and legacy source data lack sufficient identity
metadata to resolve every shared path. That paper therefore remains
`manual_review_required` with `database_ready=false`.

No manually digitized reference value is used by production extraction. Manual
comparison data are confined to offline regression evaluation.

## Installation

Copy the `uwc-sfcc-extractor` directory into the Codex skills directory without
renaming it. Keep `SKILL.md`, `agents`, `references`, `schemas`, `scripts`,
`tests`, `README.md` and `requirements.txt` together. Runtime caches such as
`__pycache__` and `.pytest_cache` are not part of the release.
