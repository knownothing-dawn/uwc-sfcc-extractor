# Implementation boundary

This is an agent-assisted, UWC-first extractor. Python handles coordinates,
normalization, supported physical conversion, evidence bindings, coverage QA and
presentation. The agent still reads design, identifies variables, resolves source
correspondence and verifies individual markers/temperature span.

Production reads PDF text once and runs tables/vectors/rendering only on selected
pages. Export performs conversion and QA once; no benchmark, overlay or new heavy
dependency is added. The existing geometric extraction code remains unchanged.

Evidence-backed design inventories detect missing/unexpected curves and exact
duplicates. Material versus test-state properties and original versus preferred
UWC variables are explicit. Su conversion needs verified definition and applicable
porosity. Unknown or conflicting inputs remain original and reviewable.

Excel is one four-section worksheet with two-column curve blocks, grouped by
factor then material, at most four blocks per band. JSON/provenance remains
internal; Markdown contains concise sources, transformations, notes and actions.

Schema 1.5 retains independent expected datasets, bounded source recovery, separate
point completeness, exact numerical anchors and conservative database-readiness gates.
Scientific source selection happens before export. Legacy records remain readable,
but absent/unperformed scientific checks cannot grant database readiness.
See the development-only benchmark reference for paper-specific facts.

Complex overlapping/dashed/low-resolution plots and ambiguous bindings require
review. A curve count does not prove all markers were recovered. Synthetic timing
is deterministic preparation/QA/export, not end-to-end scientific extraction or
independent digitization accuracy. Do not present it as real-paper throughput.

Version 1.0 is frozen as **Human-Reviewed Production**. Dense continuous measured traces now
retain raw coordinates internally and export an adaptively simplified scientific
curve with reconstruction statistics. Density/property roles and derivation scope
are explicit, and source-reported condition precision remains separate from curve
display precision. Validation uses existing fixtures plus the three supplied
Sun/Cai/Zou regression records; no literature scan, blind test or benchmark batch
was run.

RC3 adds a generic pre-centerline isolation stage for continuous traces. It detects
sustained shared paths, foreign local excursions and unresolved overlaps without
treating a single crossing as contamination. Completeness now keeps continuous raw
geometry counts separate from experimental point expectations. Reported and
normalized condition values also carry their unit, basis and precision as atomic
display bindings. These controls are conservative: uncertain isolated components
remain review-required and prevent autonomous import.

Protocol plans, hard reported observations and observable source points are now
separate. Scientific data semantics and graphical representation are independent,
so continuous measured DSC functions can be represented without calling them fits.
Design conditions, target quantities and numerical availability are distinct.
Unconverted proxy signals are documented outside the numerical UWC denominator.
Unavailable target data do not masquerade as extraction errors, but still prevent
whole-design autonomous import. Human-review usability is separate from strict
database readiness.

Unresolved source conflicts, genuinely missing or occluded observations and
incomplete experiment inventories remain limitations. All numerical observations
and source evidence in the recorded fixtures were preserved. These changes do not
provide unattended semantic interpretation or independent coordinate-accuracy
validation. No paper-specific production rule was added.

Post-v1.0 maintenance follows the evidence rule in `release-v1.0.md`: do not
change production logic for a single unusual paper unless the failure is severe
and clearly generic, or the same failure class recurs across multiple independent
papers. Record recurring evidence in `v1.1-backlog.md` before development.
