# Language and terminology policy

The user's language policy is authoritative for all versions of this skill.

1. Internal schema keys are English. Dataset keys use stable `lower_snake_case`.
2. Controlled vocabularies and enums use normalized English terms.
3. JSON uses English field names and English normalized values. This restriction
   does **not** translate original evidence or human-facing explanatory text.
4. Original source text stays in the original language and is never overwritten
   by a translation.
5. Paper titles, figure/table captions, legend labels, quoted evidence, and
   reported equations preserve original wording, symbols, punctuation, and case.
6. Soil type, SFCC branch, measurement method, curve type, units, value source,
   and other scientific classifications use the versioned vocabulary.
7. Chinese translations are allowed only as display labels or human-review
   explanations, in explicitly designated fields.
8. Excel is a human display: use requested scientific labels such as `Temp (°C)` and `θ (m³/m³)`, or optional bilingual labels. Canonical English field names remain stable in the internal JSON; display symbols never replace schema keys.
9. A translation is never scientific evidence and cannot replace an evidence ID.
10. If normalization or translation is uncertain, keep the source term, use
    `unknown` or `other` as appropriate, and flag the uncertainty. Add an action item only when it can affect UWC data or interpretation.

## Three distinct layers

| Layer | Example | Rule |
| --- | --- | --- |
| Original evidence | `soil_type_reported: "兰州黄土"` | Preserve verbatim |
| Canonical science | `soil_type_normalized: "loess"` | Only when supported by evidence |
| Human display | `display_label_zh: "黄土"` | Never used for joins or scientific inference |

Canonical units are English identifiers, such as `degree_celsius`,
`cubic_meter_per_cubic_meter`, and `kilogram_per_cubic_meter`. Their display
symbols are `°C`, `m³/m³`, and `kg/m³`. Preserve the author's unit spelling in
`unit_reported` / `uwc_original_unit_reported` and evidence even after conversion.
Unknown units stay `unknown`; retaining an original label does not make it a
canonical unit. Unconvertible chemistry remains reported; request review only
when its ambiguity can affect UWC values or scientific interpretation.

`freezing`, `thawing`, `cooling`, and `warming` are distinct terms. Do not translate
or normalize cooling into freezing without supporting protocol evidence.
`freezing_and_thawing` is for inseparable/aggregate reporting; separate branches
and freeze-thaw cycles require separate curve records whenever identifiable.
Method names normalize to terms such as `nuclear_magnetic_resonance` and
`time_domain_reflectometry`. Product names and abbreviations remain reported.

`unknown` means the identity is unresolved. `other` means an identified concept
is outside the current vocabulary; preserve its reported name without forcing an action-queue task for a safely retained noncritical term. Neither is permission to invent an English classification.
Do not strip non-ASCII text, machine-translate entire JSON objects, or apply
case/whitespace normalization to protected evidence strings. Exact alias lookup
is permitted on a temporary copy, never on the stored source text.

Human translations are optional `display_translations` records with a JSON
pointer to the original field, a language code, text, and translation status.
The `source_pointer` must resolve to a source-language string. An uncertain
translation retains its status flag and original text. Optional display translation
uncertainty is a note; only scientific ambiguity requires an actionable review.

Schema validation rejects unlisted enum values and extra fields. It cannot
prove a transcription matches a PDF or that a semantic translation is correct.
Those checks require source inspection. Increment `vocabulary_version` and
update the schema intentionally when adding accepted terms; do not introduce
free-form enum values while extracting a paper.
