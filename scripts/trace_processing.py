"""Turn dense measured traces into compact scientific curves without losing raw geometry."""
import copy
import math
from statistics import median

import numpy as np

from geometry import adaptive_indices, normalized_points, segment_distances
from manifest import settings
from semantics import representation
from curve_isolation import isolate_continuous_curves
from branch_tracking import joint_track_candidate_graph


def _ordered(points):
    keyed = []
    for offset, point in enumerate(points, 1):
        order = point.get("trace_order", point.get("point_index", offset))
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise ValueError("Continuous trace order must be a positive integer")
        keyed.append((order, point))
    if len({order for order, _ in keyed}) != len(keyed):
        raise ValueError("Continuous trace order must be unique within a curve")
    return [point for _, point in sorted(keyed)]


def _xy(point):
    return float(point["temperature_celsius"]), float(point["uwc_original_value"])


def _spans(points):
    values = np.asarray([_xy(point) for point in points], dtype=float)
    if len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("A continuous trace needs at least two finite coordinates")
    xmin, ymin = values.min(axis=0)
    xmax, ymax = values.max(axis=0)
    if xmax <= xmin or ymax <= ymin:
        raise ValueError("Continuous trace axes must have positive spans")
    return values, (float(xmin), float(xmax), float(ymin), float(ymax))


def _copy_at(point, curve_id, index, x, y, segment=None):
    result = copy.deepcopy(point)
    result["point_id"] = f"{curve_id}_scientific_{index:04d}"
    result["point_index"] = index
    result["temperature_celsius"] = float(x)
    unit = result["temperature_original_unit"]
    result["temperature_original_value"] = float(x + 273.15 if unit == "kelvin" else x)
    result["uwc_original_value"] = float(y)
    result.update(uwc_preferred_value=None, uwc_preferred_unit=None, uwc_preferred_basis=None,
                  uwc_preferred_value_source=None, uwc_derivation_id=None,
                  observation_quality="continuous_trace_sample", trace_segment=segment)
    result.pop("trace_order", None)
    result.pop("raw_pixel_x", None)
    result.pop("raw_pixel_y", None)
    return result


def _centerline(points, bounds, x_tolerance):
    xmin, xmax, ymin, ymax = bounds
    xspan, yspan = xmax - xmin, ymax - ymin
    ordered = sorted(points, key=lambda p: (_xy(p)[0], p.get("trace_order", p.get("point_index", 0))))
    groups, current = [], []
    for point in ordered:
        nx = (_xy(point)[0] - xmin) / xspan
        if current and nx - current[0][0] > x_tolerance:
            groups.append(current); current = []
        current.append((nx, point))
    if current: groups.append(current)
    result, vertical = [], False
    for group in groups:
        xs = [_xy(p)[0] for _, p in group]
        ys = [_xy(p)[1] for _, p in group]
        x, y = median(xs), median(ys)
        nearest = min((p for _, p in group), key=lambda p: abs(_xy(p)[0]-x) + abs(_xy(p)[1]-y)/yspan)
        result.append((nearest, float(x), float(y)))
        vertical |= (max(ys)-min(ys))/yspan > .08 and len(group) > 2
    return result, vertical


def path_centerline(points, bounds, tolerance, raw_points=None, fidelity_threshold=None):
    """Preserve explicit path order and multi-valued x; never collapse by x."""
    ordered=sorted(points,key=lambda p:(p.get('path_order',p.get('path_position',0)),p.get('candidate_id','')))
    center=[(p,float(p.get('x',p.get('temperature_celsius'))),float(p.get('y',p.get('uwc_original_value')))) for p in ordered]
    coords=normalized_points(np.asarray([(x,y) for _,x,y in center],float),bounds)
    delta=np.diff(coords,axis=0) if len(coords)>1 else np.empty((0,2))
    vertical=bool(len(delta) and np.any((np.abs(delta[:,0]) <= max(tolerance,1e-12)) & (np.abs(delta[:,1]) > .08)))
    status='pass';p95=None
    if raw_points is not None and len(center)>=2:
        raw_norm=normalized_points(np.asarray(raw_points,float),bounds)
        distances=[]
        for point in raw_norm:
            distances.append(min(float(segment_distances(point[None,:],coords[i],coords[i+1])[0]) for i in range(len(coords)-1)))
        p95=float(np.percentile(distances,95))
        if fidelity_threshold is not None and p95>fidelity_threshold: status='unresolved'
    return center,{'near_vertical':vertical,'status':status,'raw_to_centerline_p95':p95,'topology':'path_order'}


def _denoise(centerline, bounds, tolerance):
    if len(centerline) < 3 or tolerance <= 0:
        return centerline
    ymin, ymax = bounds[2], bounds[3]
    yspan = ymax - ymin
    result = list(centerline)
    for index in range(1, len(centerline)-1):
        point, x, y = centerline[index]
        left, right = centerline[index-1], centerline[index+1]
        if right[1] == left[1]:
            continue
        predicted = left[2] + (right[2]-left[2]) * (x-left[1])/(right[1]-left[1])
        if abs(y-predicted)/yspan <= tolerance:
            result[index] = (point, x, float(predicted))
    return result


def _raw_to_centerline_distances(raw, centerline, bounds):
    """Orthogonal normalized distances to locally appropriate centerline segments."""
    raw_xy = normalized_points(np.asarray([_xy(point) for point in raw]), bounds)
    line_xy = normalized_points(np.asarray([(x,y) for _,x,y in centerline]), bounds)
    if len(line_xy) < 2:
        distances = np.linalg.norm(raw_xy-line_xy[0],axis=1)
    else:
        xs=line_xy[:,0]
        values=[]
        for point in raw_xy:
            position=int(np.searchsorted(xs,point[0]))
            candidates=[]
            for start in (position-2,position-1,position):
                if 0 <= start < len(line_xy)-1:
                    candidates.append(float(segment_distances(point[None,:],line_xy[start],line_xy[start+1])[0]))
            values.append(min(candidates) if candidates else float(np.min(np.linalg.norm(line_xy-point,axis=1))))
        distances=np.asarray(values)
    return distances


def _raw_to_path_distances(raw, centerline, bounds):
    raw_xy=normalized_points(np.asarray([_xy(point) for point in raw]),bounds)
    line_xy=normalized_points(np.asarray([(x,y) for _,x,y in centerline]),bounds)
    if len(line_xy)<2: return np.linalg.norm(raw_xy-line_xy[0],axis=1)
    return np.asarray([min(float(segment_distances(point[None,:],line_xy[i],line_xy[i+1])[0])
        for i in range(len(line_xy)-1)) for point in raw_xy])


def _raw_to_centerline_fidelity(raw, centerline, bounds):
    distances = _raw_to_centerline_distances(raw, centerline, bounds)
    return dict(median=float(np.median(distances)), p95=float(np.percentile(distances,95)),
                maximum=float(np.max(distances)), mean=float(np.mean(distances)))


def _transition_mask(coords):
    if len(coords) < 5:
        return np.zeros(len(coords), dtype=bool)
    dx = np.diff(coords[:, 0])
    dy = np.diff(coords[:, 1])
    slopes = np.divide(np.abs(dy), np.maximum(np.abs(dx), 1e-12))
    curvature = np.zeros(len(coords))
    curvature[1:-1] = np.abs(np.diff(slopes))
    nonzero = slopes[slopes > 0]
    slope_cut = np.quantile(nonzero, .75) if len(nonzero) else math.inf
    curve_nonzero = curvature[curvature > 0]
    curve_cut = np.quantile(curve_nonzero, .75) if len(curve_nonzero) else math.inf
    mask = np.zeros(len(coords), dtype=bool)
    mask[:-1] |= slopes >= slope_cut
    mask[1:] |= slopes >= slope_cut
    mask |= curvature >= curve_cut
    mask[0] = mask[-1] = True
    return mask


def _direction_segments(points):
    """Split an ordered trace at real x-direction reversals; retain the turning point."""
    if len(points) < 3:
        return [points]
    starts, direction = [0], 0
    for index in range(1, len(points)):
        delta = _xy(points[index])[0] - _xy(points[index-1])[0]
        sign = 1 if delta > 0 else -1 if delta < 0 else direction
        if direction and sign and sign != direction:
            starts.append(index-1)
        if sign: direction = sign
    starts.append(len(points)-1)
    return [points[a:b+1] for a,b in zip(starts[:-1],starts[1:]) if b>a]


def _simplify_single(centerline, bounds, tolerance, transition_factor):
    data = np.asarray([(x, y) for _, x, y in centerline], dtype=float)
    coords = normalized_points(data, bounds)
    protected = _transition_mask(coords)
    local = np.where(protected, tolerance * transition_factor, tolerance)
    keep = {0, len(coords)-1}
    # Preserve real turning extrema before applying the error bound.
    slopes = np.diff(coords[:, 1])
    for i in range(1, len(coords)-1):
        if slopes[i-1] * slopes[i] < 0:
            keep.add(i)
    anchors = sorted(keep)
    stack = list(zip(anchors[:-1], anchors[1:]))
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        segment = coords[start+1:end]
        ratio = (segment[:, 0]-coords[start,0]) / (coords[end,0]-coords[start,0])
        predicted = coords[start,1] + ratio * (coords[end,1]-coords[start,1])
        error = np.abs(segment[:,1]-predicted)
        score = error / local[start+1:end]
        offset = int(np.argmax(score))
        if score[offset] > 1:
            index = start + offset + 1
            keep.add(index); stack.extend(((start,index),(index,end)))
    return sorted(keep), protected


def _reconstruction(coords, keep):
    reconstructed = np.interp(coords[:,0], coords[keep,0], coords[keep,1])
    error = np.abs(coords[:,1]-reconstructed)
    return float(error.max(initial=0)), float(error.mean() if len(error) else 0)


def _path_reconstruction(coords,keep):
    errors=[]
    for start,end in zip(keep[:-1],keep[1:]):
        errors.extend(segment_distances(coords[start:end+1],coords[start],coords[end]).tolist())
    return max(errors,default=0.0),sum(errors)/len(errors) if errors else 0.0


def _process_curve(curve, raw, cfg, isolation):
    ordered = _ordered(raw)
    _, bounds = _spans(ordered)
    geometry = curve.get("trace_geometry", "unknown")
    warnings = list(isolation.get("isolation_warning_codes", []))
    accepted_segments = isolation.get("segments") or []
    accepted = [point for segment in accepted_segments for point in segment]
    if geometry == "single_valued":
        scientific=[]; center_count=0; transition_count=0; violations=0
        component_errors=[]; fidelity_distances=[];fidelity_diagnostics=[];fidelity_excluded=0
        for segment_number, segment in enumerate(accepted_segments, 1):
            if len(segment)<2:
                continue
            topology=all(p.get('candidate_id') is not None and p.get('path_position') is not None for p in segment)
            if topology:
                centerline,topology_meta=path_centerline(segment,bounds,cfg["trace_x_tolerance_normalized"])
                vertical=topology_meta['near_vertical']
            else:
                centerline, vertical = _centerline(segment, bounds, cfg["trace_x_tolerance_normalized"])
                centerline = _denoise(centerline, bounds, cfg["trace_denoise_tolerance_normalized"])
            if len(centerline)<2:
                warnings.append("insufficient_curve_local_geometry");continue
            local_distances=(_raw_to_path_distances if topology else _raw_to_centerline_distances)(segment, centerline, bounds)
            local_p95=float(np.percentile(local_distances,95))
            if local_p95 > cfg['trace_centerline_fidelity_p95_threshold_normalized']:
                fidelity_diagnostics.append(dict(segment_id=f"{curve['curve_id']}_fidelity_{segment_number:03d}",
                    curve_id=curve['curve_id'],condition_id=curve['condition_id'],branch=curve['branch'],status='unresolved',
                    failure_reason='centerline_fidelity_failure',resolution_class='algorithmically_resolvable',
                    start_candidate=segment[0].get('candidate_id',segment[0]['point_id']),
                    end_candidate=segment[-1].get('candidate_id',segment[-1]['point_id']),
                    candidate_ids=[p.get('candidate_id',p['point_id']) for p in segment],pixel_coordinates=None,
                    mapped_coordinates=[list(_xy(p)) for p in segment],local_tangent=None,local_curvature=None,
                    competing_paths=[],competing_branch_ids=[],component_ids=list(dict.fromkeys(p.get('component_id') for p in segment if p.get('component_id') is not None)),
                    shared_candidate_ids=[],local_confidence='low',diagnostic_note=f'Accepted-segment P95 {local_p95:.6g} exceeds {cfg["trace_centerline_fidelity_p95_threshold_normalized"]:.6g}.',
                    temperature_range=[min(_xy(p)[0] for p in segment),max(_xy(p)[0] for p in segment)],
                    uwc_range=[min(_xy(p)[1] for p in segment),max(_xy(p)[1] for p in segment)]))
                if cfg.get('trace_enforce_segment_fidelity',0)>=1:
                    fidelity_excluded+=len(segment);warnings.append('centerline_fidelity_segment_unresolved');continue
            fidelity_distances.extend(local_distances.tolist())
            if topology:
                data=np.asarray([(x,y) for _,x,y in centerline],float)
                indices=adaptive_indices(data,bounds,cfg["trace_simplification_tolerance_normalized"])
                transition=_transition_mask(normalized_points(data,bounds))
            else:
                indices, transition = _simplify_single(centerline, bounds, cfg["trace_simplification_tolerance_normalized"],
                                                        cfg["trace_transition_tolerance_factor"])
            normalized = normalized_points(np.asarray([(x,y) for _,x,y in centerline]), bounds)
            component_max, component_mean = (_path_reconstruction if topology else _reconstruction)(normalized, indices)
            component_errors.append((component_max,component_mean,len(centerline)))
            center_count += len(centerline);transition_count += int(np.count_nonzero(transition))
            if vertical: warnings.append("large_same_x_extent_requires_segment_review")
            selected=[(centerline[i][0],centerline[i][1],centerline[i][2],segment_number) for i in indices]
            component=[_copy_at(point,curve["curve_id"],len(scientific)+i,x,y,segment_number)
                       for i,(point,x,y,_) in enumerate(selected,1)]
            if topology:
                for position,item in enumerate(component,1): item.update(path_position=float(position),near_vertical=vertical)
            violations += sum(component[i]["uwc_original_value"] < component[i-1]["uwc_original_value"] - 1e-12
                for i in range(1,len(component)) if component[i]["temperature_celsius"] > component[i-1]["temperature_celsius"])
            scientific.extend(component)
        distances=np.asarray(fidelity_distances,dtype=float)
        fidelity=dict(median=float(np.median(distances)) if len(distances) else None,
            p95=float(np.percentile(distances,95)) if len(distances) else None,
            maximum=float(np.max(distances)) if len(distances) else None,
            mean=float(np.mean(distances)) if len(distances) else None)
        maximum=max((item[0] for item in component_errors),default=0)
        mean=sum(item[1]*item[2] for item in component_errors)/sum((item[2] for item in component_errors),start=0) if component_errors else 0
        if fidelity['p95'] is not None and fidelity['p95'] > cfg['trace_centerline_fidelity_p95_threshold_normalized']:
            warnings.append("centerline_fidelity_warning")
        segments=len(accepted_segments)
    else:
        fidelity = dict(median=None,p95=None,maximum=None,mean=None);fidelity_diagnostics=[];fidelity_excluded=0
        parts = _direction_segments(accepted) if geometry == "segmented" else [accepted]
        selected, error_values, transition_count = [], [], 0
        for segment_number, part in enumerate(parts,1):
            data = np.asarray([_xy(p) for p in part])
            indices = adaptive_indices(data, bounds, cfg["trace_simplification_tolerance_normalized"])
            normalized = normalized_points(data, bounds)
            errors = np.full(len(data), math.inf)
            for start, end in zip(indices[:-1], indices[1:]):
                errors[start:end+1] = np.minimum(errors[start:end+1], segment_distances(normalized[start:end+1], normalized[start], normalized[end]))
            error_values.extend(errors.tolist())
            transition_count += int(np.count_nonzero(_transition_mask(normalized)))
            for i in indices:
                if selected and part[i] is selected[-1][0]:
                    continue
                selected.append((part[i],data[i,0],data[i,1],segment_number))
        maximum, mean = max(error_values,default=0), sum(error_values)/len(error_values) if error_values else 0
        transition = np.ones(transition_count,dtype=bool)
        segments = len(parts)
        if geometry == "unknown": warnings.append("trace_geometry_assumption_not_verified")
        scientific = [_copy_at(point, curve["curve_id"], i, x, y, segment) for i,(point,x,y,segment) in enumerate(selected,1)]
        violations = sum(scientific[i]["uwc_original_value"] < scientific[i-1]["uwc_original_value"] - 1e-12
                         for i in range(1,len(scientific)) if scientific[i]["temperature_celsius"] > scientific[i-1]["temperature_celsius"])
        center_count=len(accepted);transition_count=int(np.count_nonzero(transition))
    if violations: warnings.append("monotonicity_warning")
    raw_count, exported = len(raw), len(scientific)
    accepted_count=isolation.get("accepted_raw_point_count",len(accepted))
    accepted_count=max(0,accepted_count-fidelity_excluded)
    if accepted_count > 100 and (exported > cfg["trace_oversampled_absolute_count"] or exported/accepted_count > cfg["trace_oversampled_fraction"]):
        warnings.append("oversampled_scientific_curve")
    if exported < 4 and transition_count and center_count > 20:
        warnings.append("undersampled_transition_region")
    if accepted_count > 20 and exported >= accepted_count:
        warnings.append("raw_trace_exported_unsimplified")
    warnings = list(dict.fromkeys(warnings))
    status = "pass"
    if not scientific or isolation.get("curve_isolation_status") == "failed" or maximum > cfg["trace_simplification_tolerance_normalized"] + 1e-12 or "raw_trace_exported_unsimplified" in warnings:
        status = "failed"
    elif warnings or isolation.get("curve_isolation_status") != "pass":
        status = "review_required"
    stats = dict(algorithm="normalized_adaptive_centerline_v1", status=status,
        raw_point_count=raw_count, centerline_point_count=center_count,
        exported_point_count=exported, max_normalized_reconstruction_error=maximum,
        mean_normalized_reconstruction_error=mean, reduction_ratio=1-exported/raw_count,
        raw_to_centerline_median_normalized_error=fidelity['median'],
        raw_to_centerline_p95_normalized_error=fidelity['p95'],
        raw_to_centerline_max_normalized_error=fidelity['maximum'],
        raw_to_centerline_mean_normalized_error=fidelity['mean'],
        transition_point_count=transition_count, segment_count=segments,
        monotonicity_checked_on="scientific_curve_points", monotonicity_violation_count=violations,
        warnings=warnings, simplification_tolerance_normalized=cfg["trace_simplification_tolerance_normalized"],
        x_tolerance_normalized=cfg["trace_x_tolerance_normalized"],
        denoise_tolerance_normalized=cfg["trace_denoise_tolerance_normalized"],
        centerline_fidelity_p95_threshold_normalized=cfg['trace_centerline_fidelity_p95_threshold_normalized'],
        fidelity_excluded_raw_point_count=fidelity_excluded,
        **{key:value for key,value in isolation.items() if key!='segments'})
    stats['unresolved_segment_count']=stats.get('unresolved_segment_count',0)+len(fidelity_diagnostics)
    stats['excluded_contaminated_point_count']=stats.get('excluded_contaminated_point_count',0)+fidelity_excluded
    stats['accepted_raw_point_count']=accepted_count
    return scientific, stats, fidelity_diagnostics


def process_continuous_traces(package):
    """Move dense continuous traces to raw storage and replace them with compact points."""
    cfg = settings(package)
    raw_store = package.setdefault("raw_trace_points", [])
    raw_curve_ids = {p["curve_id"] for p in raw_store}
    continuous = {c["curve_id"]: c for c in package["curves"] if representation(c) == "continuous_measured_trace"
                  and (c.get("trace_geometry") is not None or c["curve_id"] in raw_curve_ids)}
    if not continuous:
        return package
    current = {}
    for point in raw_store:
        current.setdefault(point["curve_id"], []).append(point)
    incoming = {}
    for point in package["uwc_points"]:
        if point["curve_id"] in continuous:
            incoming.setdefault(point["curve_id"], []).append(point)
    ordinary = [p for p in package["uwc_points"] if p["curve_id"] not in continuous]
    for curve_id in continuous:
        if current.get(curve_id):
            continue
        raw = copy.deepcopy(incoming.get(curve_id, []))
        for order, point in enumerate(raw, 1):
            point.setdefault("trace_order", order)
        if raw:
            current[curve_id]=raw;raw_store.extend(raw)
    # Joint assignment is opt-in and evidence-driven. Legacy packages without
    # candidate/component identity retain their conservative unresolved behavior.
    package['branch_tracking_results']=[]
    for spec in package.get('branch_tracking_specs',[]):
        pair=(spec['freezing_curve_id'],spec['thawing_curve_id'])
        if not all(cid in current for cid in pair): continue
        candidates={}
        for cid in pair:
            for point in current[cid]:
                candidate_id=point.get('candidate_id')
                if not candidate_id: continue
                candidates.setdefault(candidate_id,dict(candidate_id=candidate_id,x=_xy(point)[0],y=_xy(point)[1],
                    path_order=point.get('path_position',point.get('trace_order',point['point_index'])),
                    component_id=point.get('component_id'),marker_identity=point.get('component_id'),
                    confirmed_shared=point.get('confirmed_shared',False)))
        result=joint_track_candidate_graph(list(candidates.values()),{
            'freezing':dict(start_id=spec['freezing_start_candidate'],end_id=spec['freezing_end_candidate'],seed_component=spec.get('freezing_component_id')),
            'thawing':dict(start_id=spec['thawing_start_candidate'],end_id=spec['thawing_end_candidate'],seed_component=spec.get('thawing_component_id'))},
            spec['max_edge_distance_normalized']) if candidates else {'status':'unresolved','paths':{},'candidate_assignments':{},'confirmed_shared_ids':[],
                'unresolved_candidate_ids':[],'true_crossing_count':0,'identity_switch_count':0,'bridged':False}
        package['branch_tracking_results'].append({'condition_id':spec['condition_id'],**result})
        if result['status']=='pass':
            for branch,cid in (('freezing',pair[0]),('thawing',pair[1])):
                selected=set(result['paths'][branch]);current[cid]=[p for p in current[cid] if p.get('candidate_id') in selected]
                for position,p in enumerate(current[cid],1):
                    p['candidate_assignment']='confirmed_shared' if p.get('candidate_id') in result['confirmed_shared_ids'] else branch
                    p['path_position']=float(position)
    isolations=isolate_continuous_curves(list(continuous.values()),current,cfg)
    scientific = [];package['trace_diagnostics']=[]
    for curve_id, curve in continuous.items():
        raw = current.get(curve_id)
        if not raw:
            curve["trace_processing"] = dict(algorithm="normalized_adaptive_centerline_v1", status="failed",
                raw_point_count=0, centerline_point_count=0, exported_point_count=0,
                max_normalized_reconstruction_error=None, mean_normalized_reconstruction_error=None,
                raw_to_centerline_median_normalized_error=None, raw_to_centerline_p95_normalized_error=None,
                raw_to_centerline_max_normalized_error=None, raw_to_centerline_mean_normalized_error=None,
                reduction_ratio=0, transition_point_count=0, segment_count=0,
                monotonicity_checked_on="scientific_curve_points", monotonicity_violation_count=0,
                warnings=["raw_trace_missing"], simplification_tolerance_normalized=cfg["trace_simplification_tolerance_normalized"],
                x_tolerance_normalized=cfg["trace_x_tolerance_normalized"], denoise_tolerance_normalized=cfg["trace_denoise_tolerance_normalized"],
                centerline_fidelity_p95_threshold_normalized=cfg['trace_centerline_fidelity_p95_threshold_normalized'],
                curve_isolation_status="failed",accepted_raw_point_count=0,excluded_contaminated_point_count=0,
                unresolved_segment_count=0,shared_exact_coordinate_count=0,shared_near_coordinate_fraction=0,
                shared_segment_fraction=0,trace_domain_coverage_fraction=0,accepted_domain_fraction=0,
                unresolved_domain_fraction=1,isolation_warning_codes=["raw_trace_missing"])
            continue
        isolation=isolations.get(curve_id,dict(segments=[raw],
            curve_isolation_status="pass",accepted_raw_point_count=len(raw),excluded_contaminated_point_count=0,
            unresolved_segment_count=0,shared_exact_coordinate_count=0,shared_near_coordinate_fraction=0,
            shared_segment_fraction=0,trace_domain_coverage_fraction=1,accepted_domain_fraction=1,
            unresolved_domain_fraction=0,isolation_warning_codes=[]))
        package['trace_diagnostics'].extend(isolation.pop('segment_diagnostics',[]))
        points, stats, fidelity_diagnostics = _process_curve(curve, raw, cfg, isolation)
        package['trace_diagnostics'].extend(fidelity_diagnostics)
        curve["trace_processing"] = stats
        scientific.extend(points)
    package["uwc_points"] = ordinary + scientific
    return package
