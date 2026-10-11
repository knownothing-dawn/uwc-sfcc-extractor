"""Numerical and physical QA for UWC curves, independent of rendering/export."""
from collections import defaultdict
import math

from geometry import calibrate_axis
from science import convert_value


def topology_reverse_jumps(points, warning, severe):
    """Classify path-ordered decreases without treating near-vertical x order as scalar truth."""
    ordered=sorted(points,key=lambda p:p.get('path_position',p.get('point_index',0)))
    warning_count=severe_count=artifact=0;maximum=0.0
    for a,b in zip(ordered[:-1],ordered[1:]):
        av=_value(a);bv=_value(b)
        if av is None or bv is None: continue
        dt=float(b['temperature_celsius'])-float(a['temperature_celsius'])
        drop=av-bv
        if drop<=warning: continue
        if a.get('near_vertical') or b.get('near_vertical') or abs(dt)<=1e-4:
            artifact+=1;continue
        warning_count+=1;maximum=max(maximum,drop)
        severe_count+=int(drop>severe)
    return {'warning_count':warning_count,'severe_count':severe_count,
            'topology_artifact_count':artifact,'maximum_reverse_jump':maximum}


def _value(point):
    if point.get("uwc_preferred_value") is not None:
        return float(point["uwc_preferred_value"])
    try:
        return float(convert_value(point["uwc_original_value"], point["uwc_original_unit"],
                                   "cubic_meter_per_cubic_meter"))
    except ValueError:
        return None


def _initial_water(package, condition_id):
    priority = ("initial_volumetric_water_content", "volumetric_water_content")
    for name in priority:
        matches = [p for p in package["soil_properties"] if p.get("condition_id") == condition_id and p["property"] == name]
        if len(matches) == 1:
            try:
                return convert_value(matches[0]["value"], matches[0]["unit"], "cubic_meter_per_cubic_meter")
            except ValueError:
                return None
    return None


def validate_axis(digitization, tolerance=0.25):
    """Re-fit explicit tick anchors; counts/residual claims alone are not evidence."""
    if not digitization:
        return {"status": "not_applicable", "x_anchor_count": 0, "y_anchor_count": 0,
                "x_max_residual": None, "y_max_residual": None}
    xs, ys = digitization.get("x_axis_anchors", []), digitization.get("y_axis_anchors", [])
    result = {"status": "not_checked", "x_anchor_count": len(xs), "y_anchor_count": len(ys),
              "x_max_residual": None, "y_max_residual": None}
    if len(xs) < 3 or len(ys) < 3:
        return result
    try:
        x = calibrate_axis([[a["coordinate"], a["value"]] for a in xs], digitization["x_axis_scale"], tolerance)
        y = calibrate_axis([[a["coordinate"], a["value"]] for a in ys], digitization["y_axis_scale"], tolerance)
    except (ValueError, KeyError):
        result["status"] = "fail"
        return result
    result.update(status="pass", x_max_residual=x.residual_px, y_max_residual=y.residual_px)
    return result


def assess(package, settings):
    """Return auditable per-curve, pair and axis metrics without changing observations."""
    points = defaultdict(list)
    for p in package["uwc_points"]:
        points[p["curve_id"]].append(p)
    raw_ids = {p["curve_id"] for p in package.get("raw_trace_points", [])}
    curve_metrics, axis_metrics = [], []
    warning_drop = settings.get("reverse_jump_warning", .003)
    severe_drop = settings.get("reverse_jump_severe", .010)
    theta_warning = settings.get("initial_theta_warning", .003)
    theta_severe = settings.get("initial_theta_severe", .010)
    for curve in package["curves"]:
        ordered = sorted(((float(p["temperature_celsius"]), _value(p), p["point_id"]) for p in points[curve["curve_id"]]), key=lambda r: r[0])
        ordered = [r for r in ordered if r[1] is not None]
        drops = [(ordered[i][0], ordered[i + 1][0], ordered[i][1] - ordered[i + 1][1])
                 for i in range(len(ordered) - 1) if ordered[i + 1][0] != ordered[i][0] and ordered[i][1] > ordered[i + 1][1]]
        initial = _initial_water(package, curve["condition_id"])
        exceed = [r[1] - initial for r in ordered if initial is not None and r[1] > initial]
        slopes = [abs((b[1] - a[1]) / (b[0] - a[0])) for a, b in zip(ordered[:-1], ordered[1:]) if b[0] != a[0]]
        metric = {"curve_id": curve["curve_id"], "point_count": len(ordered),
                  "temperature_min": min((r[0] for r in ordered), default=None),
                  "temperature_max": max((r[0] for r in ordered), default=None),
                  "uwc_min": min((r[1] for r in ordered), default=None),
                  "uwc_max": max((r[1] for r in ordered), default=None),
                  "reverse_jump_count": sum(d[2] > warning_drop for d in drops),
                  "severe_reverse_jump_count": sum(d[2] > severe_drop for d in drops),
                  "maximum_reverse_jump": max((d[2] for d in drops), default=0.0),
                  "maximum_absolute_slope": max(slopes, default=None),
                  "initial_water_content": initial,
                  "above_initial_count": sum(v > theta_warning for v in exceed),
                  "severe_above_initial_count": sum(v > theta_severe for v in exceed),
                  "maximum_above_initial": max(exceed, default=0.0),
                  "raw_observations_retained": curve["curve_id"] in raw_ids or curve["extraction_method"] not in ("pdf_vector", "raster_marker", "raster_curve")}
        curve_metrics.append(metric)
        axis_metrics.append({"curve_id": curve["curve_id"], **validate_axis(curve.get("digitization"), settings.get("axis_anchor_residual_tolerance", .25))})
    pairs = []
    grouped = defaultdict(dict)
    for c in package["curves"]:
        branch = {"cooling": "freezing", "warming": "thawing"}.get(c["branch"], c["branch"])
        grouped[(c["sample_id"], c["condition_id"], c["curve_data_type"], c.get("series_variant_reported"))][branch] = c
    temp_tol = settings.get("temperature_match_tolerance_celsius", .15)
    exact_tol = settings.get("branch_exact_value_tolerance", 1e-12)
    near_tol = settings.get("branch_near_value_tolerance", .001)
    for key, branches in grouped.items():
        if not {"freezing", "thawing"} <= set(branches):
            continue
        a, b = branches["freezing"], branches["thawing"]
        aa = sorted((p["temperature_celsius"], _value(p)) for p in points[a["curve_id"]] if _value(p) is not None)
        bb = sorted((p["temperature_celsius"], _value(p)) for p in points[b["curve_id"]] if _value(p) is not None)
        pa=sorted((p["temperature_celsius"],_value(p),p) for p in points[a["curve_id"]] if _value(p) is not None)
        pb=sorted((p["temperature_celsius"],_value(p),p) for p in points[b["curve_id"]] if _value(p) is not None)
        used, matched = set(), []
        for ta, va, point_a in pa:
            choices = [(abs(ta - tb), j, tb, vb,point_b) for j, (tb, vb,point_b) in enumerate(pb) if j not in used and abs(ta - tb) <= temp_tol]
            if choices:
                _, j, tb, vb,point_b = min(choices); used.add(j); matched.append(((ta + tb) / 2, va, vb,point_a,point_b))
        signs = [0 if abs(va-vb) <= near_tol else (1 if va > vb else -1) for _, va, vb,_,_ in matched]
        nonzero = [s for s in signs if s]
        switches = sum(x != y for x, y in zip(nonzero[:-1], nonzero[1:]))
        exact = sum(abs(va-vb) <= exact_tol for _, va, vb,_,_ in matched)
        near = sum(abs(va-vb) <= near_tol for _, va, vb,_,_ in matched)
        identity_checked=bool(matched) and all(pa.get('candidate_id') and pb.get('candidate_id') for *_,pa,pb in matched)
        reused=sum(pa.get('candidate_id')==pb.get('candidate_id') for *_,pa,pb in matched) if identity_checked else 0
        confirmed=sum(pa.get('candidate_id')==pb.get('candidate_id') and pa.get('confirmed_shared') and pb.get('confirmed_shared') for *_,pa,pb in matched) if identity_checked else 0
        suspicious=reused-confirmed
        topology_checked=bool(matched) and all(pa.get('component_id') and pb.get('component_id') for *_,pa,pb in matched)
        def component_switches(index):
            seq=sorted((row[3+index] for row in matched),key=lambda p:p.get('path_position',p.get('point_index',0)))
            comps=[p.get('component_id') for p in seq]
            return sum(x!=y for x,y in zip(comps[:-1],comps[1:]))
        identity_switches=component_switches(0)+component_switches(1) if topology_checked else 0
        true_crossings=max(0,switches-identity_switches) if topology_checked else 0
        unclassified=0 if topology_checked else switches
        pairs.append({"freezing_curve_id": a["curve_id"], "thawing_curve_id": b["curve_id"],
                      "matched_temperature_count": len(matched), "exact_duplicate_count": exact,
                      "exact_duplicate_fraction": exact / len(matched) if matched else 0.0,
                      "near_duplicate_count": near, "near_duplicate_fraction": near / len(matched) if matched else 0.0,
                      "branch_order_switch_count": switches,
                      "candidate_identity_status": "checked" if identity_checked else "not_checked",
                      "same_candidate_reuse_count": reused,"confirmed_shared_count": confirmed,
                      "suspicious_shared_assignment_count": suspicious,
                      "true_crossing_count": true_crossings,"identity_switch_count": identity_switches,
                      "unclassified_order_crossing_count": unclassified,
                      "possible_copied_or_shared_candidates": bool(identity_checked and len(matched)>=6 and suspicious/len(matched)>=settings.get("branch_duplicate_fraction_threshold",.5)),
                      "possible_branch_switch": identity_switches >= settings.get("branch_order_switch_threshold", 2)})
    return {"curve_metrics": curve_metrics, "pair_metrics": pairs, "axis_metrics": axis_metrics}


def gate_status(metrics, strict):
    if not strict:
        return {"axis_anchor_validation": "not_checked", "numerical_quality": "not_checked", "physical_quality": "not_checked"}
    axis = "pass" if metrics["axis_metrics"] and all(m["status"] in ("pass", "not_applicable") for m in metrics["axis_metrics"]) else "fail"
    numerical = "fail" if any(m["severe_reverse_jump_count"] for m in metrics["curve_metrics"]) or any(p["possible_copied_or_shared_candidates"] or p["possible_branch_switch"] for p in metrics["pair_metrics"]) else "pass"
    physical = "fail" if any(m["severe_above_initial_count"] for m in metrics["curve_metrics"]) else "pass"
    return {"axis_anchor_validation": axis, "numerical_quality": numerical, "physical_quality": physical}
