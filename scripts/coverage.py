"""Compare an evidence-led design inventory with unique recovered UWC series."""
from collections import defaultdict
import json

from science import convert_value
import math
from manifest import branch_key, dataset_identity
from semantics import data_semantics, numerical_expected


STATE_PROPERTIES = {"dry_density", "initial_water_saturation", "degree_of_saturation",
                    "initial_volumetric_water_content", "initial_gravimetric_water_content",
                    "initial_ionic_concentration", "solution_concentration", "salinity", "pressure",
                    "matric_suction", "confining_pressure", "cooling_rate", "warming_rate", "holding_time"}
CANONICAL_UNITS = {"dry_density": "kilogram_per_cubic_meter", "initial_water_saturation": "fraction",
                   "degree_of_saturation": "fraction", "initial_ionic_concentration": "mole_per_liter",
                   "solution_concentration": "mole_per_liter", "pressure": "kilopascal", "matric_suction": "kilopascal"}
PROPERTY_BASES = {"initial_volumetric_water_content": "volumetric",
                  "initial_gravimetric_water_content": "gravimetric_dry_mass"}


def case_inventory_errors(package):
    """An omitted condition cannot shrink the denominator when the table lists it."""
    errors=[]
    conditions={c["condition_id"]:c for c in package["conditions"]}
    for case in package.get("experimental_cases", []):
        for variable in case["variables"]:
            found=[]
            key=variable["property"]
            for cid in case["condition_ids"]:
                condition=conditions.get(cid)
                if not condition:continue
                if key == "cycle_number":
                    if condition["cycle_number"] is not None:found.append(condition["cycle_number"])
                    continue
                aliases=[a for a in condition.get("design_aliases",[]) if a["case_id"]==case["case_id"] and a["property"]==key]
                exact=[p for p in package["soil_properties"] if p["condition_id"]==cid and p["property"]==key]
                rows=aliases or exact or [p for p in package["soil_properties"] if p["sample_id"]==case["sample_id"] and p["condition_id"] is None and p["property"]==key]
                for row in rows:
                    try:found.append(convert_value(row["value"],row["unit"],variable["unit"],PROPERTY_BASES.get(key)))
                    except ValueError:pass
            if any(not any(math.isclose(value,n,rel_tol=1e-10,abs_tol=1e-12) for n in found) for value in variable["values"]):
                errors.append(f"{case['case_id']}: expected condition inventory omits a reported {key} value")
            if any(not any(math.isclose(n,value,rel_tol=1e-10,abs_tol=1e-12) for value in variable["values"]) for n in found):
                errors.append(f"{case['case_id']}: condition identity conflicts with the reported {key} design values; preserve an evidence-linked alias if resolved")
    return errors


def condition_keys(package):
    values = defaultdict(list)
    for prop in package["soil_properties"]:
        if prop['condition_id'] and prop['property']=='other':
            # An unspecified physical basis does not erase a reported condition.
            values[prop['condition_id']].append(('other', prop['property_reported'], prop['value'], prop['unit'], prop['unit_reported']))
        if prop["condition_id"] and prop["property"] in STATE_PROPERTIES:
            key = {"degree_of_saturation": "initial_water_saturation",
                   "solution_concentration": "initial_ionic_concentration"}.get(prop["property"], prop["property"])
            unit = CANONICAL_UNITS.get(key, prop["unit"])
            try:
                value = convert_value(prop["value"], prop["unit"], unit, PROPERTY_BASES.get(key))
            except ValueError:
                value, unit = prop["value"], (prop["unit"], prop["unit_reported"])
            values[prop["condition_id"]].append((key, value, unit))
    result = {}
    for condition in package["conditions"]:
        cid = condition["condition_id"]
        state = sorted(values[cid], key=repr) if values[cid] else condition["condition_label_reported"]
        result[cid] = json.dumps([condition["sample_id"], state, condition["cycle_number"],
                                  condition["salt_type_reported"], condition["pore_water_chemistry_reported"]],
                                 sort_keys=True, ensure_ascii=False)
    return result


def observation_fingerprint(points):
    # Exact numerical equality only. Similar-looking/differently sampled curves
    # require source resolution and are never silently merged.
    rows = []
    for point in points:
        basis, unit, value = point["uwc_original_basis"], point["uwc_original_unit"], point["uwc_original_value"]
        target = {"volumetric": "cubic_meter_per_cubic_meter", "gravimetric_dry_mass": "kilogram_per_kilogram",
                  "unfrozen_water_saturation": "fraction", "liquid_water_saturation": "fraction"}.get(basis, unit)
        try:
            value = convert_value(value, unit, target, basis)
            unit = target
        except ValueError:
            unit = (unit, point["uwc_original_unit_reported"])
        rows.append((point["temperature_celsius"], value, repr(unit), basis))
    return tuple(sorted(rows))


def curve_coverage(package):
    conditions = {c["condition_id"]: c for c in package["conditions"]}
    keys = condition_keys(package)
    points = defaultdict(list)
    for point in package["uwc_points"]:
        points[point["curve_id"]].append(point)
    expected = {}
    def series(cid, branch, kind, variant=None):
        row = {"sample_id": conditions[cid]["sample_id"], "condition_id": cid,
                "branch": branch, "curve_data_type": kind}
        if variant is not None: row['series_variant_reported'] = variant
        return row
    def identity(cid, branch, kind, variant=None):
        return dataset_identity(dict(condition_id=cid, branch=branch, curve_data_type=kind, series_variant_reported=variant), keys)
    cases = package.get("experimental_cases", [])
    if package.get('expected_datasets'):
        for item in package['expected_datasets']:
            if numerical_expected(item):
                cid, branch, kind = item['condition_id'], item['branch'], item['curve_data_type']
                row = series(cid, branch, kind, item.get('series_variant_reported'))
                row['data_semantics'] = data_semantics(item)
                expected.setdefault(dataset_identity(item, keys), row)
    elif cases:
        for case in cases:
            for cid in case["condition_ids"]:
                for branch in case["branches"]:
                    for kind in case["curve_data_types"]:
                        expected.setdefault(identity(cid, branch, kind), series(cid, branch, kind))
    else:
        for evidence in package["evidence"]:
            for item in evidence.get("expected_series", []):
                cid, branch, kind = item["condition_id"], item["branch"], item["curve_data_type"]
                expected.setdefault(dataset_identity(item, keys), series(cid, branch, kind, item.get('series_variant_reported')))
    primary = {e["evidence_id"] for e in package["evidence"] if e.get("source_role") == "primary_uwc"}
    models = {e["evidence_id"] for e in package["evidence"] if e.get("source_role") == "sfcc_model"}
    actual, unique, duplicates = defaultdict(list), [], []
    occurrences = 0
    for curve in package["curves"]:
        cp = points[curve["curve_id"]]
        if not cp:
            continue
        key = dataset_identity(curve, keys)
        occurrences += max(1, len(curve.get("source_occurrences", [])))
        linked = set(curve["evidence_ids"]) | {e for p in cp for e in p["evidence_ids"]}
        eligible = primary if data_semantics(curve) == 'measured' else primary | models
        actual[key].append((curve, cp, bool(linked & eligible)))
    recovered = set()
    for key, records in actual.items():
        fingerprints = {}
        for curve, cp, linked in records:
            if linked:
                recovered.add(key)
            signature = (curve["method"], curve["data_origin"], curve.get("replicate_label_reported"), observation_fingerprint(cp))
            fingerprints.setdefault(signature, []).append(curve["curve_id"])
        for group in fingerprints.values():
            unique.append(group[0])
            if len(group) > 1:
                duplicates.append({"condition_id": records[0][0]["condition_id"], "curve_ids": group, "identical": True})
        unresolved = [c for c, _, _ in records if not c.get("replicate_label_reported")]
        if len(fingerprints) > 1 and len(unresolved) > 1:
            duplicates.append({"condition_id": records[0][0]["condition_id"],
                               "curve_ids": [c["curve_id"] for c in unresolved], "identical": False})
    matched = len(set(expected) & recovered)
    return {"expected_curve_count": len(expected), "extracted_curve_count": len(unique),
            "matched_curve_count": matched, "coverage_percentage": 100 * matched / len(expected) if expected else None,
            "inventory_available": bool(expected), "source_occurrence_count": occurrences, "unique_curve_ids": unique,
            "missing_conditions": [item for key, item in expected.items() if key not in recovered],
            "unexpected_conditions": [dict(series(records[0][0]["condition_id"], key[1], records[0][0]['curve_data_type'], key[3]), data_semantics=data_semantics(records[0][0]))
                                      for key, records in actual.items() if key not in expected] if expected else [],
            "duplicate_conditions": duplicates,
            "design_dataset_count": len(package.get('expected_datasets', [])) or len(expected),
            "documented_unavailable_dataset_ids": [m['expected_curve_id'] for m in package.get('expected_datasets', []) if not numerical_expected(m)],
            "proxy_dataset_ids": [m['expected_curve_id'] for m in package.get('expected_datasets', []) if m.get('target_quantity_status')=='proxy_signal_only'],
            "unavailable_target_dataset_ids": [m['expected_curve_id'] for m in package.get('expected_datasets', []) if m.get('measurement_status')=='expected' and
                m.get('target_quantity_status')!='proxy_signal_only' and m.get('availability_status') in ('reported_but_not_numerically_available','not_found_in_source')]}
