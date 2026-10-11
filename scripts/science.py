"""Conservative terminology mapping and auditable scientific calculations."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB = json.loads((ROOT / "schemas/vocabulary.json").read_text(encoding="utf-8"))


def property_role(record):
    """Return an explicit role, with a narrow legacy mapping for older packages."""
    if record.get("property_role"):
        return record["property_role"]
    prop = record.get("property")
    if prop == "maximum_dry_density": return "maximum_dry_density"
    if prop == "particle_density": return "particle_density"
    if prop == "specific_gravity": return "specific_gravity"
    if prop == "wet_density": return "wet_bulk_density"
    if prop == "porosity": return "porosity"
    if prop == "water_density": return "water_density"
    if prop in ("initial_volumetric_water_content", "initial_gravimetric_water_content"):
        return "initial_water_content"
    if prop == "dry_density":
        role = record.get("experiment_role")
        if role in ("uwc_measurement", "uwc_nmr", "uwc_dsc") or (
                role is None and record.get("condition_id") is not None):
            return "test_dry_density"
        return "dry_density_reported_unspecified_context"
    return "other"


def experiment_role_compatible(record, curve):
    role = record.get("experiment_role")
    if role == "uwc_measurement": return True
    if role == "uwc_nmr": return curve.get("method") in ("nuclear_magnetic_resonance", "pulsed_nuclear_magnetic_resonance")
    if role == "uwc_dsc": return curve.get("method") in ("differential_scanning_calorimetry", "calorimetry")
    # Backward compatibility is limited to an exact condition-bound legacy test property.
    return role is None and record.get("condition_id") == curve.get("condition_id")


def normalize_term(domain, reported, affects_uwc=False):
    """Exact aliases only. Return the source unchanged; never fuzzy-match science."""
    values = list(VOCAB["units"]) if domain == "unit" else VOCAB["terms"][domain]
    key = reported.strip().casefold() if isinstance(reported, str) else ""
    lookup = {v.casefold(): v for v in values}
    normalized = lookup.get(key)
    status = "exact_match"
    if normalized is None:
        normalized = VOCAB["aliases"].get(domain, {}).get(key)
        status = "verified_mapping"
    if normalized is None:
        normalized, status = "unknown", "unmapped"
    return {"reported": reported, "normalized": normalized,
            "normalization_status": status,
            "needs_manual_review": affects_uwc and normalized in ("unknown", "other")}


# (dimension, multiplier, offset) relative to each recommended unit.
UNITS = {
    "degree_celsius": ("temperature", 1, 0), "kelvin": ("temperature", 1, -273.15),
    "degree_fahrenheit": ("temperature", 5 / 9, -32 * 5 / 9),
    "kilogram_per_cubic_meter": ("density", 1, 0), "gram_per_cubic_centimeter": ("density", 1000, 0),
    "square_meter_per_gram": ("surface_area", 1, 0), "square_meter_per_kilogram": ("surface_area", .001, 0),
    "millimeter": ("length", 1, 0), "centimeter": ("length", 10, 0), "meter": ("length", 1000, 0),
    "kilopascal": ("pressure", 1, 0), "megapascal": ("pressure", 1000, 0), "pascal": ("pressure", .001, 0),
    "degree_celsius_per_hour": ("thermal_rate", 1, 0), "degree_celsius_per_minute": ("thermal_rate", 60, 0),
    "hour": ("time", 1, 0), "minute": ("time", 1 / 60, 0), "second": ("time", 1 / 3600, 0),
    "decisiemens_per_meter": ("conductivity", 1, 0), "microsiemens_per_centimeter": ("conductivity", .001, 0),
    "percent": ("ratio", .01, 0), "fraction": ("ratio", 1, 0),
    "kilogram_per_kilogram": ("dry_mass_ratio", 1, 0),
    "cubic_meter_per_cubic_meter": ("volume_ratio", 1, 0), "dimensionless": ("dimensionless", 1, 0),
    "mole_per_liter": ("concentration", 1, 0), "millimole_per_liter": ("concentration", .001, 0),
}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("A finite numeric value is required")
    return value


def convert_value(value, source_unit, target_unit, basis=None):
    number(value)
    if source_unit not in UNITS or target_unit not in UNITS:
        raise ValueError("Unsupported unit conversion; preserve original and request review")
    sdim, sfactor, soffset = UNITS[source_unit]
    tdim, tfactor, toffset = UNITS[target_unit]
    if source_unit == target_unit:
        return value
    if {source_unit, target_unit} <= {"fraction", "percent", "dimensionless"}:
        return value * sfactor / tfactor
    if {sdim, tdim} <= {"ratio", "dry_mass_ratio", "volume_ratio"}:
        # Fraction/percent carries no mass/volume semantics by itself.
        required = "volumetric" if "volume_ratio" in (sdim, tdim) else "gravimetric_dry_mass"
        if "volume_ratio" in (sdim, tdim) and "dry_mass_ratio" in (sdim, tdim):
            raise ValueError("Mass-to-volume conversion requires density, not unit scaling")
        if sdim != tdim and basis != required:
            raise ValueError("Explicit water-content basis is required")
    elif sdim != tdim:
        raise ValueError("Incompatible unit dimensions")
    return (value * sfactor + soffset - toffset) / tfactor


def normalize_point(point):
    """Simple scaling only; preserve original evidence and scientific derivations."""
    result = dict(point)
    if result["temperature_value_source"] != "derived":
        result["temperature_celsius"] = convert_value(result["temperature_original_value"],
                                                      result["temperature_original_unit"], "degree_celsius")
        result["temperature_normalized"] = result["temperature_original_unit"] != "degree_celsius"
    if result["uwc_original_basis"] == "volumetric" and result["uwc_preferred_value_source"] != "derived":
        result.update(uwc_preferred_value=convert_value(result["uwc_original_value"], result["uwc_original_unit"],
                                                       "cubic_meter_per_cubic_meter", "volumetric"),
                      uwc_preferred_unit="cubic_meter_per_cubic_meter", uwc_preferred_basis="volumetric",
                      uwc_preferred_value_source=result["value_source"],
                      uwc_normalized=result["uwc_original_unit"] != "cubic_meter_per_cubic_meter")
    return result


def make_input(variable, value, unit, source_id, source_field="value", evidence_ids=(),
               definition_status="explicit", assumed=False):
    return {"variable": variable, "value": number(value), "unit": unit,
            "source_id": source_id, "source_field": source_field,
            "evidence_ids": list(evidence_ids), "definition_status": definition_status,
            "assumed": assumed}


def check_inputs(inputs):
    if not inputs or len({x["variable"] for x in inputs}) != len(inputs):
        raise ValueError("Inputs must be nonempty with unique variable names")
    for item in inputs:
        number(item["value"])
        if item["definition_status"] != "explicit":
            raise ValueError("Ambiguous definitions prohibit derivation")
        if not item["assumed"] and (not item["source_id"] or not item["source_field"] or not item["evidence_ids"]):
            raise ValueError("Every reported input needs a source and evidence")


RELATIONS = {
    "volumetric_unfrozen_water_content_from_saturation": (
        {"unfrozen_water_saturation": "fraction", "porosity": "fraction"},
        "cubic_meter_per_cubic_meter", "theta_u = porosity * unfrozen_water_saturation"),
    "volumetric_unfrozen_water_content": (
        {"gravimetric_unfrozen_water_content": "kilogram_per_kilogram", "dry_density": "kilogram_per_cubic_meter", "water_density": "kilogram_per_cubic_meter"},
        "cubic_meter_per_cubic_meter", "theta_u = w_u * dry_density / water_density"),
    "porosity": ({"dry_density": "kilogram_per_cubic_meter", "particle_density": "kilogram_per_cubic_meter"}, "fraction", "porosity = 1 - dry_density / particle_density"),
    "void_ratio_from_porosity": ({"porosity": "fraction"}, "dimensionless", "void_ratio = porosity / (1 - porosity)"),
    "void_ratio_from_densities": ({"dry_density": "kilogram_per_cubic_meter", "particle_density": "kilogram_per_cubic_meter"}, "dimensionless", "void_ratio = particle_density / dry_density - 1"),
    "degree_of_saturation": ({"volumetric_water_content": "cubic_meter_per_cubic_meter", "porosity": "fraction"}, "fraction", "degree_of_saturation = volumetric_water_content / porosity"),
    "wet_density": ({"dry_density": "kilogram_per_cubic_meter", "gravimetric_water_content": "kilogram_per_kilogram"}, "kilogram_per_cubic_meter", "wet_density = dry_density * (1 + gravimetric_water_content)"),
    "particle_density": ({"specific_gravity": "dimensionless", "water_density": "kilogram_per_cubic_meter"}, "kilogram_per_cubic_meter", "particle_density = specific_gravity * water_density"),
}


def derive(relation, inputs, derivation_id, confidence="high", allow_default_water_density=False):
    """Caller checks scope; package validation checks source references and values."""
    required, unit, formula = RELATIONS[relation]
    required = dict(required)
    inputs = [dict(item) for item in inputs]
    assumptions = []
    if "water_density" in required and not any(i["variable"] == "water_density" for i in inputs):
        if not allow_default_water_density:
            raise ValueError("Water density missing; explicitly enable the permitted default assumption")
        inputs.append(make_input("water_density", 1000, "kilogram_per_cubic_meter", None,
                                 source_field=None, assumed=True))
        assumptions.append({"variable": "water_density", "value": 1000,
                            "unit": "kilogram_per_cubic_meter",
                            "description": "Water density assumed to be 1000 kg/m³; not reported by the paper."})
    check_inputs(inputs)
    percent_uwc = relation == "volumetric_unfrozen_water_content" and any(
        i["variable"] == "gravimetric_unfrozen_water_content" and i["unit"] == "percent" for i in inputs)
    if percent_uwc:
        required["gravimetric_unfrozen_water_content"] = "percent"
        formula = "theta_u = (w_u / 100) * dry_density / water_density"
    saturation_unit = next((i["unit"] for i in inputs if i["variable"] == "unfrozen_water_saturation"), None)
    if relation == "volumetric_unfrozen_water_content_from_saturation" and saturation_unit in ("percent", "dimensionless"):
        required["unfrozen_water_saturation"] = saturation_unit
        if saturation_unit == "percent":
            formula = "theta_u = porosity * (unfrozen_water_saturation / 100)"
    if {x["variable"]: x["unit"] for x in inputs} != required:
        raise ValueError("Variables or units do not match the relation; normalize inputs first")
    if any(x["assumed"] for x in inputs) and not assumptions:
        raise ValueError("Only the documented water density default is supported")
    values = {x["variable"]: x["value"] for x in inputs}
    if any(v <= 0 for k, v in values.items() if k.endswith("density") or k == "specific_gravity"):
        raise ValueError("Densities and specific gravity must be positive")
    if any(v < 0 for k, v in values.items() if "water_content" in k):
        raise ValueError("Negative water content cannot be used in a derivation")
    if "dry_density" in values and "particle_density" in values and values["dry_density"] > values["particle_density"]:
        raise ValueError("Density conflict prohibits derivation")
    if "porosity" in values:
        n = values["porosity"]
        if not 0 <= n < 1 or (relation == "degree_of_saturation" and n == 0):
            raise ValueError("Invalid porosity for this relation")
    v = values
    if relation == "volumetric_unfrozen_water_content":
        result = v["gravimetric_unfrozen_water_content"] * v["dry_density"] / v["water_density"] / (100 if percent_uwc else 1)
    elif relation == "volumetric_unfrozen_water_content_from_saturation":
        saturation = v["unfrozen_water_saturation"] / (100 if saturation_unit == "percent" else 1)
        if not 0 <= saturation <= 1.01:
            raise ValueError("Saturation is outside the allowed small digitization tolerance")
        result = v["porosity"] * saturation
    elif relation == "porosity":
        result = 1 - v["dry_density"] / v["particle_density"]
    elif relation == "void_ratio_from_porosity":
        result = v["porosity"] / (1 - v["porosity"])
    elif relation == "void_ratio_from_densities":
        result = v["particle_density"] / v["dry_density"] - 1
    elif relation == "degree_of_saturation":
        result = v["volumetric_water_content"] / v["porosity"]
    elif relation == "wet_density":
        result = v["dry_density"] * (1 + v["gravimetric_water_content"])
    else:
        result = v["specific_gravity"] * v["water_density"]
    return {"derivation_id": derivation_id, "derived_variable": relation,
            "derivation_type": "physical_relation", "formula": formula, "input_variables": inputs,
            "assumption_used": bool(assumptions), "assumptions": assumptions,
            "result": number(result), "unit": unit, "confidence": confidence}


def convert_record(item, target_unit, derivation_id, basis=None, confidence="high"):
    check_inputs([item])
    if item["assumed"]:
        raise ValueError("A unit conversion requires an evidence-linked source")
    result = convert_value(item["value"], item["unit"], target_unit, basis)
    sf, so = UNITS[item["unit"]][1:]
    tf, to = UNITS[target_unit][1:]
    return {"derivation_id": derivation_id, "derived_variable": item["variable"],
            "derivation_type": "unit_conversion",
            "formula": f"result = (input * {sf!r} + {so!r} - {to!r}) / {tf!r}; basis = {basis or 'not_applicable'}",
            "input_variables": [dict(item)], "assumption_used": False, "assumptions": [],
            "result": result, "unit": target_unit, "confidence": confidence}
