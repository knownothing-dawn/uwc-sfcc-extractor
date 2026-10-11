# Changelog

All notable public changes are documented here.

## [1.6.0-rc.1] - 2026-09-29

### Added

- Schema and vocabulary 1.6.0 scientific-quality gates.
- Candidate/component identity and path-order trace metadata.
- Joint two-dimensional candidate-graph assignment for paired branches.
- Segment-level trace diagnostics and fidelity enforcement.
- Topology-aware duplicate, crossing and reverse-jump QA.
- Offline point-to-polyline benchmark metrics.
- Public repository governance, CI and data/copyright policy.

### Changed

- Near-vertical traces preserve two-dimensional path order.
- Fidelity-failed accepted segments move to unresolved.
- Numerical equality no longer proves candidate reuse or physical overlap.

### Security and data boundary

- Recorded-paper fixtures and source-derived extraction packages are excluded
  from the public distribution.

Full scientific notes are in
[`references/release-v1.6.0-rc.1.md`](references/release-v1.6.0-rc.1.md).
