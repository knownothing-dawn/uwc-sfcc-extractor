"""Schema/reference enforcement and non-destructive scientific review warnings."""
import copy
import hashlib
import json
import math
import re
from pathlib import Path
from jsonschema import Draft202012Validator
from science import convert_record, convert_value, derive, property_role, experiment_role_compatible
from coverage import curve_coverage, case_inventory_errors
from manifest import branch_key
from semantics import data_semantics, representation
from hardening import extra_issues, finalize_qa

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/paper.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
ID_FIELDS = {"samples": "sample_id", "conditions": "condition_id", "soil_properties": "property_id",
             "curves": "curve_id", "uwc_points": "point_id", "models": "model_id", "evidence": "evidence_id",
             "derivations": "derivation_id", "review_queue": "review_id", "display_translations": "translation_id"}
DIGITIZED = {"pdf_vector", "raster_marker", "raster_curve"}
PROPERTY_UNITS = {
    "maximum_dry_density": "kilogram_per_cubic_meter", "optimum_water_content": "percent",
    "initial_water_saturation": "fraction", "initial_ionic_concentration": "mole_per_liter", "matric_suction": "kilopascal",
    **{k: "kilogram_per_cubic_meter" for k in ("dry_density", "wet_density", "particle_density", "water_density")},
    **{k: "cubic_meter_per_cubic_meter" for k in ("volumetric_water_content", "initial_volumetric_water_content")},
    **{k: "kilogram_per_kilogram" for k in ("gravimetric_water_content", "initial_gravimetric_water_content")},
    **{k: "fraction" for k in ("porosity", "degree_of_saturation")},
    **{k: "dimensionless" for k in ("specific_gravity", "void_ratio", "ph")},
    **{k: "percent" for k in ("liquid_limit", "plastic_limit", "plasticity_index", "sand_fraction", "silt_fraction", "clay_fraction", "mineral_fraction", "organic_carbon")},
    **{k: "millimeter" for k in ("sample_diameter", "sample_height", "d10", "d30", "d50", "d60")},
    **{k: "degree_celsius" for k in ("freezing_point", "initial_freezing_temperature", "phase_transition_temperature")},
    **{k: "kilopascal" for k in ("pressure", "confining_pressure")},
    **{k: "degree_celsius_per_hour" for k in ("cooling_rate", "warming_rate")},
    "specific_surface_area": "square_meter_per_gram", "electrical_conductivity": "decisiemens_per_meter",
    "cation_exchange_capacity": "centimole_charge_per_kilogram", "holding_time": "hour"}


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON constant: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique,
                      parse_constant=reject_constant)


def walk(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield path + "/" + key, key, child
            yield from walk(child, path + "/" + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, path + "/" + str(index))


def pointer(document, path):
    if not path.startswith("/"):
        raise ValueError("An absolute JSON pointer is required")
    value = document
    for token in path[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def issues(package):
    """Return hard validation errors. Do not mutate or coerce source values."""
    errors = [f"/{'/'.join(map(str, e.absolute_path))}: {e.message}"
              for e in VALIDATOR.iter_errors(package)]
    for path, key, value in walk(package):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            errors.append(f"{path}: canonical keys must be English lower_snake_case")
        if isinstance(value, float) and not math.isfinite(value):
            errors.append(f"{path}: non-finite number")
    if errors:
        return errors
    paper = package["paper"]
    maps = {name: {r[field]: r for r in package[name]} for name, field in ID_FIELDS.items()}
    maps['uwc_points'].update({p['point_id']: p for p in package.get('reference_points', [])})
    all_objects = {paper["paper_id"]: paper}
    object_types = {paper["paper_id"]: "paper"}
    types = dict(zip(ID_FIELDS, ("sample", "condition", "property", "curve", "point", "model", "evidence", "derivation", "review", "translation")))
    for name, id_field in ID_FIELDS.items():
        for row in package[name] + (package.get('reference_points', []) if name == 'uwc_points' else []):
            rid = row[id_field]
            if rid in all_objects:
                errors.append(f"Duplicate object ID: {rid}")
            all_objects[rid] = row
            object_types[rid] = types[name]
    for row in package.get("raw_trace_points", []):
        rid = row["point_id"]
        if rid in all_objects:
            errors.append(f"Duplicate object ID: {rid}")
        all_objects[rid] = row
        object_types[rid] = "point"
    for model in package["models"]:
        for row in model["parameters"] + model["fit_statistics"]:
            rid = row["model_value_id"]
            if rid in all_objects:
                errors.append(f"Duplicate model value ID: {rid}")
            all_objects[rid] = row
            object_types[rid] = "model"
    cases = {c["case_id"]: c for c in package.get("experimental_cases", [])}
    if len(cases) != len(package.get("experimental_cases", [])) or set(cases) & set(all_objects):
        errors.append("Duplicate experimental case ID")
    for case in cases.values():
        for cid in case["condition_ids"]:
            if cid not in maps["conditions"] or maps["conditions"][cid]["sample_id"] != case["sample_id"]:
                errors.append(f"{case['case_id']}: invalid condition/sample binding")
        if not case["condition_ids"] or not case["branches"] or not case["curve_data_types"]:
            errors.append(f"{case['case_id']}: expected design inventory is empty")
    errors.extend(case_inventory_errors(package))
    errors.extend(extra_issues(package))

    refs = {"paper_id": {paper["paper_id"]: paper}, "sample_id": maps["samples"],
            "condition_id": maps["conditions"], "curve_id": maps["curves"],
            "derivation_id": maps["derivations"], "temperature_derivation_id": maps["derivations"],
            "uwc_derivation_id": maps["derivations"], "case_id": cases}
    definition_paths = {f"/{name}/{i}/{field}" for name, field in ID_FIELDS.items()
                        for i in range(len(package[name]))}
    definition_paths.update(f"/experimental_cases/{i}/case_id" for i in range(len(cases)))
    for path, key, value in walk(package):
        if key in refs and value is not None and path not in definition_paths and value not in refs[key]:
            errors.append(f"{path}: dangling reference {value}")
        if key == "evidence_ids":
            for evidence_id in value:
                if evidence_id not in maps["evidence"]:
                    errors.append(f"{path}: missing evidence {evidence_id}")
    for curve in package["curves"]:
        condition = maps["conditions"].get(curve["condition_id"])
        if condition and (condition["sample_id"] != curve["sample_id"] or condition["cycle_number"] != curve["cycle_number"]):
            errors.append(f"{curve['curve_id']}: condition/sample/cycle mismatch")
        if curve["data_origin"] == "reproduced_literature_data" and not curve["original_citation_reported"]:
            errors.append(f"{curve['curve_id']}: reproduced data require the original citation")
        variable = curve.get("raw_variable")
        expected_basis = {"unfrozen_water_saturation": "unfrozen_water_saturation", "liquid_water_saturation": "liquid_water_saturation",
                          "volumetric_unfrozen_water_content": "volumetric", "gravimetric_unfrozen_water_content": "gravimetric_dry_mass"}.get(variable)
        if expected_basis and expected_basis != curve["uwc_basis"]:
            errors.append(f"{curve['curve_id']}: original variable and UWC basis disagree")
        for pid in curve.get("conversion_property_ids", []):
            prop = maps["soil_properties"].get(pid)
            if not prop or prop["sample_id"] != curve["sample_id"] or prop["condition_id"] not in (None, curve["condition_id"]):
                errors.append(f"{curve['curve_id']}: invalid conversion property binding")
        d = curve["digitization"]
        if d and d["benchmark_status"] == "validated" and not d["benchmark_reference"]:
            errors.append(f"{curve['curve_id']}: validated settings require a benchmark reference")
        if representation(curve) == 'discrete_markers' and (curve["extraction_method"] == "raster_curve" or d and d["normalized_error_tolerance"] is not None):
            errors.append(f"{curve['curve_id']}: measured markers cannot be continuously traced or resampled")
        trace = curve.get("trace_processing")
        if representation(curve) == "continuous_measured_trace" and trace:
            actual = sum(p["curve_id"] == curve["curve_id"] for p in package.get("raw_trace_points", []))
            if actual != trace["raw_point_count"]:
                errors.append(f"{curve['curve_id']}: raw trace count does not match recoverable storage")
    for group in ("soil_properties", "models"):
        for row in package[group]:
            condition = maps["conditions"].get(row["condition_id"])
            if condition and condition["sample_id"] != row["sample_id"]:
                errors.append(f"{row[ID_FIELDS[group]]}: sample/condition mismatch")

    derivation_targets = {}
    def derived_link(row_id, result, unit, source, derivation_id):
        if source == "derived":
            derivation_targets.setdefault(derivation_id, []).append(row_id)
            derivation = maps["derivations"].get(derivation_id)
            if not derivation:
                errors.append(f"{row_id}: derived value lacks a derivation")
            elif unit != derivation["unit"] or not math.isclose(result, derivation["result"], rel_tol=1e-10, abs_tol=1e-12):
                errors.append(f"{row_id}: derived result/unit does not match derivation")
        elif derivation_id is not None:
            errors.append(f"{row_id}: derivation attached to a non-derived value")

    values = package["soil_properties"] + [v for m in package["models"] for v in m["parameters"] + m["fit_statistics"]]
    for row in values:
        rid = row.get("property_id", row.get("model_value_id"))
        if row.get("property") == "dry_density" and re.search(r"maximum|max\.?\s+dry|最大干密度", row.get("property_reported") or "", re.I):
            errors.append(f"{rid}: maximum dry density must not be classified as test dry density")
        if row.get("property_id"):
            role = property_role(row)
            if row.get("property") == "maximum_dry_density" and role != "maximum_dry_density":
                errors.append(f"{rid}: maximum dry density has an incompatible property role")
            if role == "test_dry_density" and row.get("property") != "dry_density":
                errors.append(f"{rid}: test dry density role requires a dry-density property")
        for cid in row.get("applicable_condition_ids", []):
            if cid not in maps["conditions"] or maps["conditions"][cid]["sample_id"] != row["sample_id"]:
                errors.append(f"{rid}: invalid property applicability")
        if row["value"] is not None:
            derived_link(rid, row["value"], row["unit"], row["value_source"], row["derivation_id"])
        if (row["original_value"] is None) != (row["original_unit"] is None):
            errors.append(f"{rid}: original value/unit must be paired")
        if row["value_source"] != "derived" and row["original_value"] is not None:
            if row.get("normalized", False):
                basis = {"initial_volumetric_water_content": "volumetric", "volumetric_water_content": "volumetric",
                         "initial_gravimetric_water_content": "gravimetric_dry_mass", "gravimetric_water_content": "gravimetric_dry_mass"}.get(row.get("property"))
                try:
                    expected = convert_value(row["original_value"], row["original_unit"], row["unit"], basis)
                    if not math.isclose(row["value"], expected, rel_tol=1e-10, abs_tol=1e-12):
                        errors.append(f"{rid}: incorrect normalization")
                except ValueError as exc:
                    errors.append(f"{rid}: {exc}")
            elif row["value"] != row["original_value"] or row["unit"] != row["original_unit"]:
                errors.append(f"{rid}: simple unit scaling requires normalized=true")
        elif row.get("normalized", False):
            errors.append(f"{rid}: normalized=true requires original values and unchanged source provenance")
        expected_unit = PROPERTY_UNITS.get(row.get("property"))
        if expected_unit and row["unit"] not in (expected_unit, "unknown", "other"):
            errors.append(f"{rid}: normalized property unit must be {expected_unit}; preserve the original separately")

    point_indexes = set()
    reference_ids = {r['point_id'] for r in package.get('reference_points', [])}
    for p in package["uwc_points"] + package.get('reference_points', []):
        pid, curve = p["point_id"], maps["curves"].get(p["curve_id"])
        reference = pid in reference_ids
        pair = (p["curve_id"], p["point_index"])
        if pair in point_indexes and not reference:
            errors.append(f"{pid}: duplicate point index in curve")
        if not reference: point_indexes.add(pair)
        if curve:
            for key in ("curve_data_type", "extraction_method"):
                if p[key] != curve[key] and not (reference and key == 'extraction_method'):
                    errors.append(f"{pid}: {key} does not match curve")
            if p["uwc_original_basis"] != curve["uwc_basis"]:
                errors.append(f"{pid}: UWC basis does not match curve")
        expected_source = "figure_digitized" if p["extraction_method"] in DIGITIZED else "reported"
        if p["value_source"] != expected_source:
            errors.append(f"{pid}: original UWC provenance does not match extraction method")
        derived_link(pid, p["temperature_celsius"], "degree_celsius", p["temperature_value_source"], p["temperature_derivation_id"])
        if p["temperature_value_source"] != "derived":
            try:
                expected_t = convert_value(p["temperature_original_value"], p["temperature_original_unit"], "degree_celsius")
                if not math.isclose(p["temperature_celsius"], expected_t, rel_tol=1e-10, abs_tol=1e-12) or p["temperature_value_source"] != expected_source or (p["temperature_original_unit"] != "degree_celsius" and not p.get("temperature_normalized", False)):
                    errors.append(f"{pid}: temperature normalization/provenance is incorrect")
            except ValueError as exc:
                errors.append(f"{pid}: {exc}")
        preferred_keys = ("uwc_preferred_unit", "uwc_preferred_basis", "uwc_preferred_value_source")
        if p["uwc_preferred_value"] is None:
            if any(p[k] is not None for k in preferred_keys) or p["uwc_derivation_id"]:
                errors.append(f"{pid}: absent preferred value must have null preferred metadata")
        else:
            if any(p[k] is None for k in preferred_keys):
                errors.append(f"{pid}: preferred value requires basis/unit/provenance")
            derived_link(pid, p["uwc_preferred_value"], p["uwc_preferred_unit"], p["uwc_preferred_value_source"], p["uwc_derivation_id"])
            if p["uwc_preferred_value_source"] != "derived":
                try:
                    expected_u = convert_value(p["uwc_original_value"], p["uwc_original_unit"], "cubic_meter_per_cubic_meter", p["uwc_original_basis"])
                    if p["uwc_original_basis"] != "volumetric" or not math.isclose(p["uwc_preferred_value"], expected_u, rel_tol=1e-10, abs_tol=1e-12) or p["uwc_preferred_value_source"] != p["value_source"] or (p["uwc_original_unit"] != "cubic_meter_per_cubic_meter" and not p.get("uwc_normalized", False)):
                        errors.append(f"{pid}: preferred UWC normalization/provenance is incorrect")
                except ValueError as exc:
                    errors.append(f"{pid}: {exc}")

    dependencies = {}
    conflicting_sources = set()
    property_groups = {}
    for r in package["soil_properties"]:
        key = (r["sample_id"], r["condition_id"], r["property"],
               r["mineral_name_reported"] if r["property"] == "mineral_fraction" else None,
               r["property_reported"] if r["property"] == "other" else None)
        property_groups.setdefault(key, []).append(r)
    for rows in property_groups.values():
        if len({(r["value"], r["unit"]) for r in rows}) > 1:
            conflicting_sources.update(r["property_id"] for r in rows)
    blocking_reviews = {r["object_id"] for r in package["review_queue"]
                        if r["generated_by"] != "validator" and r["status"] == "open" and r["issue_type"] in
                        ("conflicting_values", "physical_conflict", "unit_uncertain", "uwc_definition_uncertain", "formula_uncertain")}
    field_units = {"value": "unit", "original_value": "original_unit", "uwc_original_value": "uwc_original_unit",
                   "uwc_preferred_value": "uwc_preferred_unit", "temperature_celsius": None,
                   "temperature_original_value": "temperature_original_unit"}
    for d in package["derivations"]:
        did, scopes, basis = d["derivation_id"], set(), None
        dependencies[did] = set()
        for i in d["input_variables"]:
            if i["assumed"]:
                if i["source_id"] or i["source_field"] or i["evidence_ids"]:
                    errors.append(f"{did}: assumed input must not impersonate reported evidence")
                continue
            source = all_objects.get(i["source_id"])
            field = i["source_field"]
            if source is None or field not in field_units or field not in source:
                errors.append(f"{did}: invalid derivation input source/field")
                continue
            unit = "degree_celsius" if field == "temperature_celsius" else source.get(field_units[field])
            if source[field] != i["value"] or unit != i["unit"]:
                errors.append(f"{did}: input value/unit differs from its source")
            if not set(i["evidence_ids"]).issubset(source.get("evidence_ids", [])):
                errors.append(f"{did}: input evidence differs from its source")
            if source.get("definition_status", "explicit") != "explicit" or source.get("confidence") == "low":
                errors.append(f"{did}: ambiguous or low-confidence source used for derivation")
            if i["source_id"] in conflicting_sources or i["source_id"] in blocking_reviews:
                errors.append(f"{did}: unresolved conflicting/ambiguous source used for derivation")
            if "curve_id" in source:
                c = maps["curves"].get(source["curve_id"])
                if c:
                    scopes.add((c["sample_id"], c["condition_id"]))
                basis = source.get("uwc_original_basis") if field == "uwc_original_value" else basis
            elif "sample_id" in source:
                scopes.add((source["sample_id"], source.get("condition_id")))
                if source.get("property") in ("gravimetric_water_content", "initial_gravimetric_water_content"):
                    basis = "gravimetric_dry_mass"
                elif source.get("property") in ("volumetric_water_content", "initial_volumetric_water_content"):
                    basis = "volumetric"
            if d["derivation_type"] == "physical_relation":
                variable = i["variable"]
                allowed_properties = {
                    "gravimetric_water_content": {"gravimetric_water_content", "initial_gravimetric_water_content"},
                    "volumetric_water_content": {"volumetric_water_content", "initial_volumetric_water_content"}}
                if variable == "gravimetric_unfrozen_water_content":
                    if "point_id" not in source or field != "uwc_original_value" or source["uwc_original_basis"] != "gravimetric_dry_mass":
                        errors.append(f"{did}: unfrozen water input must come from a dry-mass UWC observation")
                elif variable == "unfrozen_water_saturation":
                    c = maps["curves"].get(source.get("curve_id"), {})
                    if ("point_id" not in source or field != "uwc_original_value" or source["uwc_original_basis"] != "unfrozen_water_saturation"
                            or not c.get("variable_definition_verified")):
                        errors.append(f"{did}: saturation input requires an explicitly verified pore-volume Su definition")
                elif source.get("property") not in allowed_properties.get(variable, {variable}) or field != "value":
                    errors.append(f"{did}: scientific input variable does not match source property definition")
                if variable == "dry_density" and source.get("property_id"):
                    target_curve = None
                    for target_id in derivation_targets.get(did, []):
                        target = all_objects.get(target_id, {})
                        target_curve = maps["curves"].get(target.get("curve_id"))
                        if target_curve: break
                    if property_role(source) != "test_dry_density" or target_curve and not experiment_role_compatible(source, target_curve):
                        errors.append(f"{did}: dry-density input is not bound to the UWC specimen role")
            if field in ("value", "uwc_preferred_value", "temperature_celsius"):
                dep_field = {"value": "derivation_id", "uwc_preferred_value": "uwc_derivation_id", "temperature_celsius": "temperature_derivation_id"}[field]
                if source.get(dep_field):
                    dependencies[did].add(source[dep_field])
        for target_id in derivation_targets.get(did, []):
            target = all_objects[target_id]
            if "point_id" in target:
                curve = maps["curves"].get(target["curve_id"])
                if curve:
                    scopes.add((curve["sample_id"], curve["condition_id"]))
                    for inp in d["input_variables"]:
                        prop = maps["soil_properties"].get(inp["source_id"])
                        if prop and prop["property"] == "porosity" and prop["condition_id"] is None:
                            if prop["property_id"] not in curve.get("conversion_property_ids", []) and curve["condition_id"] not in prop.get("applicable_condition_ids", []):
                                errors.append(f"{did}: material porosity lacks explicit specimen applicability")
            elif "sample_id" in target:
                scopes.add((target["sample_id"], target.get("condition_id")))
        if len({s[0] for s in scopes}) > 1 or len({s[1] for s in scopes if s[1] is not None}) > 1:
            errors.append(f"{did}: derivation mixes sample or condition scopes")
        try:
            if d["derivation_type"] == "unit_conversion":
                if len(d["input_variables"]) != 1:
                    raise ValueError("Unit conversion requires exactly one input")
                expected = convert_record(d["input_variables"][0], d["unit"], did, basis, d["confidence"])
            else:
                given = [i for i in d["input_variables"] if not i["assumed"]]
                if d["derived_variable"] == "volumetric_unfrozen_water_content" and basis != "gravimetric_dry_mass":
                    raise ValueError("Dry-mass UWC basis is not established by source")
                if d["derived_variable"] == "volumetric_unfrozen_water_content_from_saturation" and basis != "unfrozen_water_saturation":
                    raise ValueError("Pore-volume unfrozen saturation basis is not established by source")
                expected = derive(d["derived_variable"], given, did, d["confidence"], d["assumption_used"])
            for key in ("formula", "unit", "input_variables", "assumption_used", "assumptions"):
                if expected[key] != d[key]:
                    errors.append(f"{did}: derivation {key} differs from reproducible calculation")
            if not math.isclose(expected["result"], d["result"], rel_tol=1e-10, abs_tol=1e-12):
                errors.append(f"{did}: incorrect calculated result")
        except (ValueError, KeyError, ZeroDivisionError) as exc:
            errors.append(f"{did}: {exc}")

    def cycle(node, active, seen):
        if node in active:
            return True
        if node in seen:
            return False
        seen.add(node)
        return any(cycle(child, active | {node}, seen) for child in dependencies.get(node, ()))
    if any(cycle(node, set(), set()) for node in dependencies):
        errors.append("Circular derivation dependency")
    for translation in package["display_translations"]:
        try:
            path = translation["source_pointer"]
            source = pointer(package, path)
            source_field = path.split("/")[-1]
            allowed = source_field.endswith("_reported") or source_field in ("paper_title", "legend_label", "figure_caption", "table_caption", "quoted_evidence", "source_context")
            if not isinstance(source, str) or not allowed:
                errors.append(f"{translation['translation_id']}: translation must point to an original evidence string")
        except (KeyError, IndexError, ValueError, TypeError):
            errors.append(f"{translation['translation_id']}: invalid translation source pointer")
    for r in package["review_queue"]:
        if r["object_id"] not in all_objects or object_types.get(r["object_id"]) != r["object_type"]:
            errors.append(f"{r['review_id']}: invalid review target")
        if r["status"] == "resolved" and not r["resolution_notes"]:
            errors.append(f"{r['review_id']}: resolution requires notes")
    return errors


def review_severity(review):
    if review.get("severity"):
        return review["severity"]
    if review["issue_type"] in ("terminology_uncertain", "translation_uncertain", "missing_overlay", "benchmark_pending"):
        return "note"
    if review["issue_type"] in ("axis_uncertain", "curve_identity_uncertain", "legend_uncertain", "overlapping_curves", "conflicting_values", "physical_conflict"):
        return "critical"
    return "important"


def add_issue(package, object_type, object_id, issue_type, description, action, page=None, figure=None, severity="critical"):
    if severity == "note":
        return
    digest = hashlib.sha256(f"{object_type}|{object_id}|{issue_type}|{description}".encode()).hexdigest()[:16]
    review_id = "review_" + digest
    if not any(r["review_id"] == review_id for r in package["review_queue"]):
        package["review_queue"].append({"review_id": review_id, "paper_id": package["paper"]["paper_id"],
            "object_type": object_type, "object_id": object_id, "issue_type": issue_type,
            "description": description, "page": page, "figure": figure, "confidence": "low", "severity": severity,
            "recommended_action": action, "status": "open", "resolution_notes": None, "generated_by": "validator"})


def qa(package, artifact_root=None, mode="production", *, copy_package=True):
    """One validation pass; aggregate actionable issues around sources and curves."""
    errors = issues(package)
    if errors:
        raise ValueError("\n".join(errors))
    if copy_package:
        package = copy.deepcopy(package)
    old_auto = {r["review_id"]: r for r in package["review_queue"] if r["generated_by"] == "validator"}
    package["review_queue"] = [r for r in package["review_queue"]
                               if r["generated_by"] != "validator" and review_severity(r) != "note"]
    p = package["paper"]
    if p.get('review_status') in ('pending', 'approved', 'rejected'):
        p['legacy_review_status'] = p['review_status']
    curves = {c["curve_id"]: c for c in package["curves"]}
    evidence = {e["evidence_id"]: e for e in package["evidence"]}
    points = {cid: [] for cid in curves}
    for point in package["uwc_points"]:
        points[point["curve_id"]].append(point)
    sources = [e for e in evidence.values() if e.get("source_role") == "primary_uwc"]
    def warn(typ, rid, kind, message, severity="critical", action="Check this item against the cited source."):
        add_issue(package, typ, rid, kind, message, action, severity=severity)

    coverage = curve_coverage(package)
    package["coverage"] = coverage
    if coverage["missing_conditions"]:
        samples = {s["sample_id"]: s["sample_name_reported"] or s["soil_type_reported"] or s["soil_type_normalized"] for s in package["samples"]}
        names = {c["condition_id"]: samples[c["sample_id"]] + "; " + (c["condition_label_reported"] or "Unidentified condition") for c in package["conditions"]}
        missing_labels = "; ".join(dict.fromkeys(names[x["condition_id"]] + " / " + x["branch"] for x in coverage["missing_conditions"]))
        warn("paper", p["paper_id"], "extraction_incomplete",
             f"Expected design inventory is missing {len(coverage['missing_conditions'])} curves: {missing_labels}.",
             action="Recover the primary numerical data or keep this paper incomplete; do not insert synthetic points.")
    if coverage["unexpected_conditions"]:
        warn("paper", p["paper_id"], "curve_identity_uncertain", "Extracted curves include conditions outside the expected design inventory.")
    for duplicate in coverage["duplicate_conditions"]:
        if not duplicate["identical"]:
            warn("curve", duplicate["curve_ids"][0], "duplicate_record", "Same experimental condition has nonidentical datasets; resolve provenance or identify independent replicates.")

    if p["extraction_status"] != "not_relevant":
        missing = [k for k in ("paper_title", "authors", "publication_year", "journal") if not p[k]]
        if missing:
            warn("paper", p["paper_id"], "missing_core_information", "Missing bibliographic fields: " + ", ".join(missing) + ".", "important")
        if not p["coverage_verified"]:
            warn("paper", p["paper_id"], "extraction_incomplete", "UWC source coverage has not been checked.", "important")
        if p["extractable_uwc_data"] and not package["uwc_points"] and (coverage['expected_curve_count'] or not package.get('expected_datasets')):
            warn("paper", p["paper_id"], "extraction_incomplete", "Primary UWC data remain unextracted.")
        if package["uwc_points"] and not sources:
            warn("paper", p["paper_id"], "extraction_incomplete", "Primary UWC source has not been distinguished from supporting/validation sources.", "important")

    # Coverage is checked against the identified source, not against easy-to-read anchors.
    for source in ([] if package.get("experimental_cases") or package.get('expected_datasets') else sources):
        expected = source.get("expected_series", [])
        if not expected:
            warn("evidence", source["evidence_id"], "extraction_incomplete", "Primary source lacks a condition/branch coverage inventory.", "important")
            continue
        present = {(c["condition_id"], branch_key(c["branch"]), c["curve_data_type"]) for c in curves.values()
                   if source["evidence_id"] in c["evidence_ids"] and points[c["curve_id"]]}
        missing = {(s["condition_id"], branch_key(s["branch"]), s["curve_data_type"]) for s in expected} - present
        if missing:
            branches = ", ".join(sorted({x[1] for x in missing}))
            warn("evidence", source["evidence_id"], "extraction_incomplete",
                 f"Primary UWC source is missing {len(missing)} condition/branch series ({branches}); validation anchors do not replace them.",
                 action="Finish the missing primary-source series, or document why they cannot be recovered.")

    props = package["soil_properties"]
    grouped = {}
    scoped_props = {}
    for row in props:
        scoped_props.setdefault((row["sample_id"], row["condition_id"]), []).append(row)
        key = (row["sample_id"], row["condition_id"], row["property"],
               row["mineral_name_reported"] if row["property"] == "mineral_fraction" else None,
               row["property_reported"] if row["property"] == "other" else None)
        grouped.setdefault(key, []).append(row)
        field, value = row["property"], row["value"]
        if row["definition_status"] != "explicit" and (field in ("dry_density", "wet_density", "gravimetric_water_content", "initial_gravimetric_water_content", "volumetric_water_content", "initial_volumetric_water_content") or field == "other" and row["unit"] in ("kilogram_per_cubic_meter", "gram_per_cubic_centimeter")):
            warn("property", row["property_id"], "formula_uncertain", "Reported density/water-content basis is unclear; value is not eligible for scientific derivation.", "important")
        if (field == "porosity" and row["unit"] == "fraction" and not 0 <= value <= 1) or (field == "degree_of_saturation" and row["unit"] == "fraction" and not 0 <= value <= 1) or (field.endswith("density") and value <= 0):
            warn("property", row["property_id"], "physical_consistency_warning", f"Physical range warning for {field}; reported value retained.", "important")
    for rows in grouped.values():
        if len({(r["value"], r["unit"]) for r in rows}) > 1:
            warn("property", rows[0]["property_id"], "conflicting_values", "Conflicting reported values for the same sample/condition property; neither was silently selected.")

    resolved_scopes = {}
    for condition in package["conditions"]:
        inherited = scoped_props.get((condition["sample_id"], None), [])
        exact = scoped_props.get((condition["sample_id"], condition["condition_id"]), [])
        by_property = {}
        for row in inherited:
            by_property.setdefault(row["property"], []).append(row)
        for key in {r["property"] for r in exact}:
            by_property[key] = [r for r in exact if r["property"] == key]
        resolved_scopes[condition["condition_id"]] = by_property
        for high, low in (("wet_density", "dry_density"), ("liquid_limit", "plastic_limit")):
            a, b = by_property.get(high, []), by_property.get(low, [])
            if len(a) == len(b) == 1 and a[0]["unit"] == b[0]["unit"] and a[0]["value"] < b[0]["value"]:
                warn("condition", condition["condition_id"], "physical_consistency_warning", f"{high} is smaller than {low}; observations retained.", "important")

    for c in curves.values():
        cid, cp = c["curve_id"], points[c["curve_id"]]
        missing = [k for k in ("branch", "data_origin") if c[k] == "unknown"]
        if data_semantics(c) == 'unknown': missing.append('data_semantics')
        if representation(c) == 'unknown': missing.append('representation')
        if missing:
            warn("curve", cid, "curve_identity_uncertain", "Uncertain curve classification: " + ", ".join(missing) + ".")
        if c["method"] == "unknown":
            warn("curve", cid, "missing_core_information", "UWC measurement method is not identified.", "important")
        if c["confidence"] == "low" or any(x["confidence"] == "low" for x in cp):
            warn("curve", cid, "low_confidence", "Low-confidence UWC observations require source confirmation.")
        linked = [evidence[eid] for eid in c["evidence_ids"]]
        if linked and all(e.get("source_role") == "validation" for e in linked):
            warn("curve", cid, "duplicate_record", "Validation-only observations are stored as an independent UWC series; confirm they do not duplicate the primary dataset.")
        relevant_ids = set(c["evidence_ids"])
        for point in cp:
            relevant_ids.update(point["evidence_ids"])
        if cp and (not linked or any(not x["evidence_ids"] for x in cp) or any(evidence[eid]["transcription_status"] != "verified" for eid in relevant_ids)):
            warn("curve", cid, "source_verification_required", "UWC evidence is missing or its source transcription is unverified.")
        if c["uwc_basis"] in ("unknown", "other") or any(x["uwc_original_unit"] in ("unknown", "other") for x in cp):
            warn("curve", cid, "uwc_definition_uncertain", "UWC definition/unit is unresolved; original values are retained without forced volumetric conversion.")
        if c["uwc_basis"] in ("unfrozen_water_saturation", "liquid_water_saturation"):
            if not c.get("variable_definition_verified"):
                warn("curve", cid, "uwc_definition_uncertain", "Saturation denominator/variable definition has not been verified against the paper.")
            saturation = []
            for x in cp:
                try:
                    saturation.append(convert_value(x["uwc_original_value"], x["uwc_original_unit"], "fraction"))
                except ValueError:
                    warn("curve", cid, "uwc_definition_uncertain", "Saturation unit cannot be normalized to a pore-volume fraction; source unit needs confirmation.")
            if any(x < -.01 or x > 1.01 for x in saturation):
                warn("curve", cid, "physical_conflict", "Saturation is outside [0, 1] by more than the 0.01 graphical tolerance; values retained.")
        if c["extraction_method"] in DIGITIZED:
            d = c["digitization"]
            if not d or min(d["x_calibration_points"], d["y_calibration_points"]) < 3 or d["axis_confidence"] != "high" or any(d[k] is None for k in ("x_calibration_residual_px", "y_calibration_residual_px", "calibration_artifact")) or d["x_axis_scale"] in ("unknown", "broken") or d["y_axis_scale"] in ("unknown", "broken"):
                warn("curve", cid, "axis_uncertain", "UWC digitization lacks a reliable multi-tick axis mapping.")
        if not cp:
            warn("curve", cid, "extraction_incomplete", "Identified UWC series has no extracted points.")
        ordered = sorted(cp, key=lambda x: x["temperature_celsius"])
        if any(a["uwc_original_value"] > b["uwc_original_value"] for a, b in zip(ordered[:-1], ordered[1:]) if a["temperature_celsius"] != b["temperature_celsius"] and a["uwc_original_unit"] == b["uwc_original_unit"]):
            warn("curve", cid, "monotonicity_warning", "UWC decreases over an increasing-temperature interval; points retained.", "important")
        porosities = resolved_scopes.get(c["condition_id"], {}).get("porosity", [])
        negative = sum(x["uwc_original_value"] < 0 or x["uwc_preferred_value"] is not None and x["uwc_preferred_value"] < 0 for x in cp)
        excess = sum(x["uwc_preferred_value"] is not None and x["uwc_preferred_value"] > porosities[0]["value"] + .005 for x in cp) if len(porosities) == 1 and porosities[0]["unit"] == "fraction" else 0
        if negative or excess:
            derived_conflict = any(x["uwc_preferred_value_source"] == "derived" and
                (x["uwc_preferred_value"] < 0 or len(porosities) == 1 and porosities[0]["unit"] == "fraction" and
                 x["uwc_preferred_value"] > porosities[0]["value"] + .005) for x in cp)
            warn("curve", cid, "physical_conflict" if derived_conflict else "physical_consistency_warning",
                 f"UWC physical warnings: {negative} negative, {excess} above porosity; points retained.",
                 "critical" if derived_conflict else "important")

    for r in package["review_queue"]:
        old = old_auto.get(r["review_id"])
        if old and old["status"] == "resolved" and review_severity(r) != "critical":
            r.update(status="resolved", resolution_notes=old["resolution_notes"])
    critical = [r for r in package["review_queue"] if r["status"] == "open" and review_severity(r) == "critical"]
    targets = {r["object_id"] for r in critical}
    for c in curves.values():
        related = {p["paper_id"], c["curve_id"], c["sample_id"], c["condition_id"]} | set(c["evidence_ids"]) | {x["point_id"] for x in points[c["curve_id"]]}
        c["needs_manual_review"] = bool(related & targets)
    if critical:
        p["extraction_status"] = "manual_review_required"
        p["review_status"] = "pending"
    elif p["extraction_status"] != "not_relevant":
        coverage_pending = any(r["status"] == "open" and r["issue_type"] == "extraction_incomplete" for r in package["review_queue"])
        if not p["coverage_verified"] or coverage_pending or coverage["coverage_percentage"] != 100:
            p["extraction_status"] = "partial" if package["uwc_points"] else "metadata_only"
        elif package["uwc_points"]:
            p["extraction_status"] = "complete"
        else:
            p["extraction_status"] = "metadata_only"
    return finalize_qa(package, warn)
