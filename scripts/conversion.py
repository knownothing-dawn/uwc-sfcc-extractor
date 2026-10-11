"""Bind explicit scientific inputs and populate preferred volumetric UWC once."""
import copy
from collections import defaultdict
from science import derive, make_input, normalize_point, property_role, experiment_role_compatible


def convert_preferred(package, *, copy_package=True):
    result = copy.deepcopy(package) if copy_package else package
    props = {p["property_id"]: p for p in result["soil_properties"]}
    scoped = defaultdict(list)
    for prop in props.values():
        scoped[(prop["sample_id"], prop["property"])].append(prop)
    curves = {c["curve_id"]: c for c in result["curves"]}
    linked = {}
    blocked = {r["object_id"] for r in result["review_queue"] if r["status"] == "open" and
               r["issue_type"] in ("physical_conflict", "conflicting_values", "formula_uncertain", "uwc_definition_uncertain", "unit_uncertain")}
    for curve in curves.values():
        selected = curve.get("conversion_property_ids", [])
        bindings = {}
        for key in ("porosity", "dry_density", "water_density"):
            candidates = scoped.get((curve["sample_id"], key), [])
            exact = [p for p in candidates if p["condition_id"] == curve["condition_id"]]
            candidates = exact or [p for p in candidates if p["condition_id"] is None and
                (p.get("property_scope") == "test_state" or curve["condition_id"] in p.get("applicable_condition_ids", []))]
            if selected:
                candidates = [props[pid] for pid in selected if pid in props and props[pid]["property"] == key]
            if len(candidates) != 1:
                continue
            prop = candidates[0]
            if (prop["sample_id"] != curve["sample_id"] or prop["condition_id"] not in (None, curve["condition_id"])
                    or prop["definition_status"] != "explicit" or prop["confidence"] == "low" or prop["property_id"] in blocked
                    or any(p["value"] != prop["value"] or p["unit"] != prop["unit"] for p in exact)):
                continue
            if key == "dry_density" and (property_role(prop) != "test_dry_density" or not experiment_role_compatible(prop, curve)):
                continue
            if key == "porosity" and prop.get("experiment_role") not in (None, "uwc_measurement", "uwc_nmr", "uwc_dsc"):
                continue
            bindings[key] = prop
        linked[curve["curve_id"]] = bindings
    derivation_ids = {d["derivation_id"] for d in result["derivations"]}
    for index, raw in enumerate(result["uwc_points"]):
        curve = curves[raw["curve_id"]]
        point = normalize_point(raw)
        for flag in ("temperature_normalized", "uwc_normalized"):
            if point.get(flag) is False and flag not in raw:
                point.pop(flag)
        result["uwc_points"][index] = point
        if point["uwc_preferred_value"] is not None:
            continue
        if {result["paper"]["paper_id"], curve["curve_id"], curve["condition_id"], curve["sample_id"]} & blocked:
            continue
        bindings = linked[curve["curve_id"]]
        basis = point["uwc_original_basis"]
        if basis == "unfrozen_water_saturation" and curve.get("variable_definition_verified") and "porosity" in bindings:
            relation, variable, keys = "volumetric_unfrozen_water_content_from_saturation", "unfrozen_water_saturation", ["porosity"]
        elif basis == "gravimetric_dry_mass" and "dry_density" in bindings:
            relation, variable, keys = "volumetric_unfrozen_water_content", "gravimetric_unfrozen_water_content", ["dry_density"]
            if "water_density" in bindings:
                keys.append("water_density")
        else:
            continue
        inputs = [make_input(variable, point["uwc_original_value"], point["uwc_original_unit"], point["point_id"],
                             "uwc_original_value", point["evidence_ids"])]
        inputs.extend(make_input(key, bindings[key]["value"], bindings[key]["unit"], bindings[key]["property_id"],
                                 evidence_ids=bindings[key]["evidence_ids"]) for key in keys)
        did = "derived_" + point["point_id"]
        if did in derivation_ids:
            raise ValueError("Preferred UWC derivation ID already exists without a matching point binding")
        try:
            record = derive(relation, inputs, did, "medium" if point["confidence"] == "medium" else "high", True)
        except ValueError:
            continue  # Keep the scientifically honest original view; QA reports invalid inputs.
        result["derivations"].append(record)
        role = next((bindings[key].get("experiment_role") for key in keys if key in bindings and
                     bindings[key].get("experiment_role")), "uwc_measurement")
        record.update(sample_id=curve["sample_id"], condition_id=curve["condition_id"], specimen_role=role,
                      applicability_evidence_ids=list(dict.fromkeys(e for key in keys if key in bindings
                          for e in bindings[key].get("applicability_evidence_ids", bindings[key]["evidence_ids"]))),
                      scope_verified=True)
        derivation_ids.add(did)
        point.update(uwc_preferred_value=record["result"], uwc_preferred_unit="cubic_meter_per_cubic_meter",
                     uwc_preferred_basis="volumetric", uwc_preferred_value_source="derived", uwc_derivation_id=did)
    return result
