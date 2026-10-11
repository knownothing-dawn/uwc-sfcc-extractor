"""Build the closed English-keyed JSON Schema from the versioned vocabulary."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB = json.loads((ROOT / "schemas/vocabulary.json").read_text(encoding="utf-8"))


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


def arr(item):
    return {"type": "array", "items": item}


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def enum(name):
    return {"type": "string", "enum": VOCAB["terms"][name]}


def ref(name):
    return {"$ref": "#/$defs/" + name}


S = {"type": "string"}
TEXT = nullable(S)
N = {"type": "number"}
NUM = nullable(N)
B = {"type": "boolean"}
ID = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]*$"}
IDS = {"type": "array", "items": ID, "uniqueItems": True}
UNIT = {"type": "string", "enum": list(VOCAB["units"])}
PAGE = nullable({"type": "integer", "minimum": 1})
EVIDENCE = {"evidence_ids": IDS, "confidence": enum("confidence")}


def build():
    defs = {}
    defs["paper"] = obj({
        "paper_id": ID, "paper_title": TEXT, "authors": arr(S), "first_author": TEXT,
        "publication_year": nullable({"type": "integer", "minimum": 1000, "maximum": 9999}),
        "journal": TEXT, "volume": TEXT, "issue": TEXT, "pages": TEXT, "doi": TEXT,
        "language": TEXT, "pdf_filename": S, "source_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "citation_short": TEXT, "extraction_status": enum("extraction_status"),
        "review_status": enum("review_status"), "uwc_relevance": nullable(enum("confidence")),
        "extractable_uwc_data": nullable(B), "coverage_verified": B, **EVIDENCE})
    defs["sample"] = obj({
        "sample_id": ID, "paper_id": ID, "sample_name_reported": TEXT,
        "soil_type_reported": TEXT, "soil_type_normalized": enum("soil_type"),
        "soil_type_normalization_status": enum("normalization_status"),
        "material_category": enum("material_category"),
        "sample_preparation": arr(enum("sample_preparation")),
        "sample_preparation_reported": TEXT, "sample_preparation_notes": TEXT, **EVIDENCE})
    defs["condition"] = obj({
        "condition_id": ID, "sample_id": ID, "condition_label_reported": TEXT,
        "cycle_number": nullable({"type": "integer", "minimum": 0}),
        "thermal_history_reported": TEXT, "salt_type_reported": TEXT,
        "pore_water_chemistry_reported": TEXT, "condition_notes": TEXT, **EVIDENCE})
    defs["property"] = obj({
        "property_id": ID, "sample_id": ID, "condition_id": nullable(ID),
        "property": enum("property"), "property_reported": TEXT,
        "value": N, "value_reported": TEXT, "unit": UNIT, "unit_reported": TEXT,
        "original_value": NUM, "original_unit": nullable(UNIT),
        "definition_reported": TEXT, "definition_status": {"enum": ["explicit", "uncertain"]},
        "value_source": enum("value_source"), "derivation_id": nullable(ID),
        "mineral_name_reported": TEXT, "mineral_name_normalized": nullable(enum("mineral")),
        **EVIDENCE})
    defs["digitization"] = obj({
        "coordinate_system": {"enum": ["pdf_points", "image_pixels"]},
        "x_axis_scale": {"enum": ["linear", "log", "broken", "unknown"]},
        "y_axis_scale": {"enum": ["linear", "log", "broken", "unknown"]},
        "x_axis_orientation": {"enum": ["normal", "reversed", "unknown"]},
        "y_axis_orientation": {"enum": ["normal", "reversed", "unknown"]},
        "x_calibration_points": {"type": "integer", "minimum": 0},
        "y_calibration_points": {"type": "integer", "minimum": 0},
        "x_calibration_residual_px": NUM, "y_calibration_residual_px": NUM,
        "axis_confidence": enum("confidence"), "calibration_artifact": TEXT,
        "trace_artifact": TEXT, "overlay_path": TEXT,
        "normalized_error_tolerance": nullable({"type": "number", "exclusiveMinimum": 0}),
        "benchmark_status": {"enum": ["pending", "validated"]},
        "benchmark_reference": TEXT})
    anchor = obj({"coordinate": N, "value": N, "label_reported": TEXT, "evidence_ids": IDS})
    defs["digitization"]["properties"].update(x_axis_anchors=arr(anchor), y_axis_anchors=arr(anchor))
    defs["curve"] = obj({
        "curve_id": ID, "paper_id": ID, "sample_id": ID, "condition_id": ID,
        "figure_id": TEXT, "figure_panel": TEXT, "page": PAGE,
        "branch_reported": TEXT, "branch": enum("branch"), "branch_source": enum("branch_source"),
        "cycle_number": nullable({"type": "integer", "minimum": 0}),
        "method_reported": TEXT, "method": enum("measurement_method"),
        "curve_data_type": enum("curve_data_type"), "legend_label": TEXT,
        "color_reported": TEXT, "marker_style_reported": TEXT, "line_style_reported": TEXT,
        "uwc_basis": enum("uwc_basis"), "uwc_definition_reported": TEXT,
        "temperature_unit": {"const": "degree_celsius"},
        "extraction_method": enum("extraction_method"), "data_origin": enum("data_origin"),
        "original_citation_reported": TEXT, "digitization": nullable(ref("digitization")),
        "needs_manual_review": B, **EVIDENCE})
    defs["point"] = obj({
        "point_id": ID, "curve_id": ID, "point_index": {"type": "integer", "minimum": 1},
        "temperature_celsius": N, "temperature_original_value": N,
        "temperature_original_unit": UNIT, "temperature_original_unit_reported": TEXT,
        "temperature_value_source": enum("value_source"), "temperature_derivation_id": nullable(ID),
        "uwc_original_value": N, "uwc_original_unit": UNIT, "uwc_original_unit_reported": TEXT,
        "uwc_original_basis": enum("uwc_basis"),
        "uwc_preferred_value": NUM,
        "uwc_preferred_unit": nullable({"const": "cubic_meter_per_cubic_meter"}),
        "uwc_preferred_basis": nullable({"const": "volumetric"}),
        "uwc_preferred_value_source": nullable(enum("value_source")),
        "uwc_derivation_id": nullable(ID), "curve_data_type": enum("curve_data_type"),
        "extraction_method": enum("extraction_method"), "value_source": enum("value_source"),
        **EVIDENCE})
    defs["model_value"] = obj({
        "model_value_id": ID, "name_reported": S, "symbol_reported": TEXT, "value": NUM, "value_reported": TEXT,
        "original_value": NUM, "original_unit": nullable(UNIT),
        "unit": UNIT, "unit_reported": TEXT, "value_source": enum("value_source"),
        "derivation_id": nullable(ID), **EVIDENCE})
    defs["model"] = obj({
        "model_id": ID, "paper_id": ID, "sample_id": nullable(ID), "condition_id": nullable(ID),
        "model_name_reported": TEXT, "model_type": enum("model_type"),
        "proposed_by_authors": nullable(B), "comparison_model": nullable(B), "existing_model": nullable(B),
        "equation_reported": TEXT, "equation_normalized": TEXT,
        "parameters": arr(ref("model_value")), "fit_statistics": arr(ref("model_value")),
        "applicable_temperature_range_reported": TEXT,
        "page": PAGE, "equation_number": TEXT, **EVIDENCE})
    defs["evidence"] = obj({
        "evidence_id": ID, "source_type": enum("source_type"), "source_file": S,
        "page": PAGE, "section_reported": TEXT, "figure_number": TEXT,
        "figure_panel": TEXT, "table_number": TEXT, "equation_number": TEXT,
        "figure_caption": TEXT, "table_caption": TEXT, "quoted_evidence": TEXT,
        "source_context": TEXT, "source_language": TEXT,
        "transcription_status": {"enum": ["verified", "unverified", "ocr_uncertain"]}})
    defs["input"] = obj({
        "variable": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "value": N, "unit": UNIT, "source_id": nullable(ID), "source_field": nullable(S),
        "evidence_ids": IDS, "definition_status": {"enum": ["explicit", "uncertain"]},
        "assumed": B})
    defs["derivation"] = obj({
        "derivation_id": ID, "derived_variable": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"}, "derivation_type": enum("derivation_type"),
        "formula": S, "input_variables": arr(ref("input")), "assumption_used": B,
        "assumptions": arr(obj({"variable": S, "value": N, "unit": UNIT, "description": S})),
        "result": N, "unit": UNIT, "confidence": enum("confidence")})
    defs["review"] = obj({
        "review_id": ID, "paper_id": ID, "object_type": enum("object_type"), "object_id": ID,
        "issue_type": enum("issue_type"), "description": S, "page": PAGE, "figure": TEXT,
        "confidence": enum("confidence"), "recommended_action": S,
        "status": {"enum": ["open", "resolved"]}, "resolution_notes": TEXT,
        "generated_by": {"enum": ["agent", "validator", "human"]}})
    defs["translation"] = obj({
        "translation_id": ID, "source_pointer": S, "language": S, "text": S,
        "translation_status": {"enum": ["verified", "uncertain"]}})
    defs["case_variable"] = obj({"property": enum("experimental_factor"), "values": arr(N),
                                  "unit": UNIT, "values_reported": arr(S), "evidence_ids": IDS})
    defs["experimental_case"] = obj({
        "case_id": ID, "sample_id": ID, "case_label_reported": S,
        "varying_property": enum("experimental_factor"), "factor_label_reported": TEXT,
        "variables": arr(ref("case_variable")), "condition_ids": IDS,
        "branches": arr(enum("branch")), "curve_data_types": arr(enum("curve_data_type")),
        "temperature_range_celsius": nullable(arr(N)), "evidence_ids": IDS})
    defs["coverage_series"] = obj({"sample_id": ID, "condition_id": ID,
                                    "branch": enum("branch"), "curve_data_type": enum("curve_data_type")})
    defs["coverage"] = obj({
        "expected_curve_count": {"type": "integer", "minimum": 0},
        "extracted_curve_count": {"type": "integer", "minimum": 0},
        "matched_curve_count": {"type": "integer", "minimum": 0},
        "coverage_percentage": NUM, "inventory_available": B,
        "source_occurrence_count": {"type": "integer", "minimum": 0},
        "unique_curve_ids": IDS, "missing_conditions": arr(ref("coverage_series")),
        "unexpected_conditions": arr(ref("coverage_series")),
        "duplicate_conditions": arr(obj({"condition_id": ID, "curve_ids": IDS, "identical": B}))})
    # Optional additions keep existing 1.0 datasets readable without a migration pass.
    for name in ("property", "model_value"):
        defs[name]["properties"]["normalized"] = B
    defs["point"]["properties"].update(temperature_normalized=B, uwc_normalized=B)
    defs["property"]["properties"].update(property_scope={"enum": ["material", "test_state"]},
                                            applicable_condition_ids=IDS)
    defs["curve"]["properties"].update(
        raw_variable=enum("uwc_variable"), raw_variable_reported=TEXT,
        variable_definition_verified=B, conversion_property_ids=IDS,
        replicate_label_reported=TEXT,
        source_occurrences=arr(obj({"evidence_ids": IDS, "case_id": nullable(ID),
                                   "legend_label": TEXT, "relationship": {"enum": ["primary", "repeated_identical", "validation", "conflicting"]}})))
    defs["curve"]["properties"]["source_occurrences"]["items"]["properties"]["source_locator"] = TEXT
    defs["condition"]["properties"]["design_aliases"] = arr(obj({"case_id": ID, "property": enum("property"),
        "value": N, "unit": UNIT, "evidence_ids": IDS}))
    defs["review"]["properties"]["severity"] = {"enum": ["critical", "important"]}
    defs["evidence"]["properties"].update(
        source_role=enum("source_role"),
        expected_series=arr(obj({"condition_id": ID, "branch": enum("branch"),
                                 "curve_data_type": enum("curve_data_type")})))
    result = obj({"schema_version": {"enum": ["1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0", "1.6.0"]},
                  "vocabulary_version": {"enum": ["1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0", VOCAB["vocabulary_version"]]},
                  "paper": ref("paper"),
                  **{k: arr(ref(v)) for k, v in {
                      "samples": "sample", "conditions": "condition", "soil_properties": "property",
                      "curves": "curve", "uwc_points": "point", "models": "model", "evidence": "evidence",
                      "derivations": "derivation", "review_queue": "review",
                      "display_translations": "translation"}.items()}})
    result["properties"].update(experimental_cases=arr(ref("experimental_case")), coverage=ref("coverage"))
    from hardening_schema import extend
    extend(result, defs, obj, arr, ref, nullable, enum, S, N, B, ID, IDS, UNIT)
    result.update({"$schema": "https://json-schema.org/draft/2020-12/schema",
                   "title": "UWC SFCC per-paper extraction package", "$defs": defs})
    return result


if __name__ == "__main__":
    path = ROOT / "schemas/paper.schema.json"
    path.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)
