# Historical v1.3 benchmark and acceptance

This is the preserved earlier-phase result, not a current RC benchmark batch.
The v1.0-RC semantic phase uses recorded fixtures only; see implementation-status.md
and hardening.md for current behavior. Do not run another benchmark or blind-test
batch without an explicit user request. Previously used papers are not unseen.

Development-only reference, updated 2026-09-24. No benchmark, overlay, screenshot
or timing loop runs during ordinary production. Paper-specific facts below belong
to regression fixtures and development scripts, never extraction rules.

## Earlier-phase result

105 software tests pass. The geometric engine is unchanged from the preserved
baseline. Seven real development papers exercise the required categories, but
the scientific acceptance standard is not met. The release remains a hardened
beta. A test that correctly blocks an incomplete package is a passing software
test, not evidence of complete extraction.

| Development paper | Expected / extracted | Original points | Critical / important | Database ready | Main limitation |
| --- | ---: | ---: | ---: | --- | --- |
| Luo 2024 | 19 / 18 | 149 | 1 / 2 | No | Missing measured salinity condition |
| Chen 2024 | 10 / 10 | 115 | 2 / 6 | No | Two large exact/graph conflicts |
| Ren 2023 | 5 / 5 | 105 | 5 / 6 | No | UWC percentage basis not explicit |
| Lai 2021 | 9 / 9 | 294 | 0 / 8 | Yes | Noncritical property/source qualifications |
| Chen 2021 | 3 / 3 | 36 | 1 / 0 | No | Three reported-temperature observations missing |
| Tokoro 2010 | 1 / 1 | 12 | 2 / 1 | No | Branch and percentage basis unresolved |
| Wang 2023 | 21 / 21 | 492 | 3 / 22 | No | Seven measured gaps; 18 fitted traces incomplete |

Luo's design has 22 occurrences / 19 unique states. Author NMR data have 21 source
occurrences / 18 unique curves / 149 points. A targeted return to Table 2, Figure
5(f) and the author's Data2 NMR rows did not recover clayey silt Sw0=0.870,
C0=1.240 mol/L. Coverage is 94.7368%; full-data acceptance fails. Conductivity at
that concentration cannot substitute for Su. Author repository:
https://zenodo.org/records/7688602 . Su-to-theta conversion retains the applicable
porosity and all original observations.

Chen keeps 115 original graph pairs, uses 15 explicit labels at corresponding
observations and does not truncate curves to those anchors. Of 15 comparisons,
eight are within tolerance, five warn and two strongly warn. Maximum error is
0.032 and mean error is 0.0050333333 m3/m3. The 120 reported targets differ from
the 115 visible observations by five source-explained gaps; no points were filled.

Ren provides 63 measured plus 42 predicted table values at three initial water
contents. Lai provides 98 measured plus 196 predicted vector markers across three
panels. Predicted curves do not fulfill the fitted-curve category. Wang supplies
that category with three measured series (35 points) and 18 separately identified
fits (457 partial trace coordinates), plus three text anchors within tolerance.
Its complete identities do not make its traces complete. Tokoro supplies the
single-curve category and preserves Japanese evidence and unresolved definitions.

## Frozen blind challenge

Five PDFs were registered with SHA256 before their contents were inspected in this
development run. No prior mentions were found in its development scripts,
fixtures or reports; this is the documented eligibility scope, not a claim about
every historical session. All 17 production script/schema hashes stayed unchanged.
All five attempts, including failures, remain in the denominator.

| Paper | Expected / extracted | Original points | Critical / important | Database ready | Wall / export seconds |
| --- | ---: | ---: | ---: | --- | ---: |
| Watanabe and Osada 2016 | 7 / 7 | 80 | 0 / 2 | No | 208.08 / 0.240 |
| Ren and Vanapalli 2019 | 20 / 16 | 192 | 2 / 10 | No | 186.03 / 0.306 |
| Huang et al. 2023 | 16 / 16 | 120 | 16 / 1 | No | 268.18 / 0.272 |
| Kozlowski and Nartowska 2013 | At least 14 / 10 | 115 | 8 / 1 | No | 268.29 / 0.292 |
| Xiao et al. 2017 | 12 / 6 | 96 | 1 / 1 | No | 554.16 / 0.322 |

Wall time is the first-read-to-first-successful-export interval, including agent
reading, coordinate annotation, input construction, tool latency and conversation
overhead. Some intervals overlap. A later targeted-review annotation is logged
separately. These numbers are not isolated algorithm time or reproducible paper
throughput. Export time covers deterministic conversion, QA and output.

- Watanabe: touching markers prevent verification of all seven point inventories.
- Ren: four TLC design branches remain absent after a targeted source revisit;
  all 20 point inventories remain unchecked.
- Huang: 160 reported targets, 120 recovered markers and 56 unmatched targets.
  Missing observations plus disagreement near zero temperature explain why the
  gap is not simply 160 minus 120. Su conversion uses reported porosity, not density.
- Kozlowski: 14 is a lower bound for identifiable displayed datasets; whole-paper
  expected count and coverage are unknown. Four displayed cycles remain missing.
  Five continuous measured DSC functions retain unknown curve type because the
  frozen enum lacks that category; they are not relabeled as fits or markers.
- Xiao: AB/A1-A5 have all 96 target markers. B1-B6 are measured NMR intensity that
  the authors expressly did not convert to UWC. Their six missing UWC states remain
  unresolved; no signals or invented calibration are substituted.

All five have zero independent comparable anchors found in the inspected sources;
zero is not an accuracy-validation pass. Huang's initial input identity/type
errors and Xiao's unsupported normalized soil term were corrected as input data,
without modifying the production engine. This is an agent-assisted challenge,
not unattended extraction. No independent WebPlotDigitizer truth set was produced.

## Performance scope

For deterministic preparation/QA/export comparison against a preserved skill:

```
python tests/runtime_regression.py --baseline OLD_SKILL_DIRECTORY --out VALIDATION_DIRECTORY --repeats 3
```

Five explicitly synthetic cases preserve their point fingerprints. Current
before/after median seconds are: complex figure 0.05384/0.05620; freezing/thawing
0.04959/0.05100; measured/fitted 0.07592/0.07744; multiple conditions
0.09000/0.09122; single curve 0.04395/0.04697. They exclude semantic extraction
and real-paper coordinate accuracy.

Five warm real-package export medians: Luo 0.13323 to 0.17140 seconds; Chen 0.06128
to 0.07861 seconds. Added QA costs about 38 ms and 17 ms respectively (about 28%).
No end-to-end speedup is claimed. Single-pass QA, shared workbook reads and bounded
recovery avoid redundant work, but do not prove an overall runtime reduction.

## Further scientific acceptance

Resolve outstanding source/point/identity failures before claiming stable v1.0.
Freeze the next generic revision before a fresh held-out challenge; papers used
for tuning are no longer unseen. Retain failures and distinguish software pass,
source completeness, metadata correctness and independently assessed accuracy.

Independent coordinate benchmarking is still pending. A proposed 25–30-figure
WebPlotDigitizer reference set and a median normalized error target of at most 1%
are future validation plans, not observed achievements. Include vector/raster,
markers/continuous traces, overlaps, line styles, materials/conditions, branches
and special axes with source provenance and reviewer identity.

Continuous-trace sampling may be compared explicitly in benchmark mode:

```
python scripts/benchmark.py --trace trace.csv --reference wpd.csv --out comparison.json --bounds -20 0 0 0.5 --fixed-count 30 --temperature-step 0.5 --tolerance 0.005
```

CSV headers are `temperature,uwc`, with matched units. These are candidate settings,
not production defaults. Interpolation is benchmark-only. Report reconstruction
errors, retained points and runtime; matched-temperature reconstruction error is
not an independent axis-calibration metric. Set `benchmark_status: validated`
only after independent paired-reference assessment, never merely from QA gates.
