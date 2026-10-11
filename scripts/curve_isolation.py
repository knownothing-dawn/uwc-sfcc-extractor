"""Conservative curve-local isolation for continuous vector geometry."""
from collections import defaultdict
import math

import numpy as np


def _xy(point):
    return float(point["temperature_celsius"]), float(point["uwc_original_value"])


def _source_key(curve):
    return (curve.get("page"), curve.get("figure_id"), curve.get("figure_panel"))


def _ordered(points):
    return sorted(points, key=lambda p: p.get("trace_order", p.get("point_index", 0)))


def _bounds(raw_by_curve, curve_ids):
    values = np.asarray([_xy(p) for cid in curve_ids for p in raw_by_curve.get(cid, [])], dtype=float)
    if not len(values):
        return None
    xmin, ymin = values.min(axis=0); xmax, ymax = values.max(axis=0)
    if xmax <= xmin or ymax <= ymin:
        return None
    return float(xmin), float(xmax), float(ymin), float(ymax)


def _normalized(points, bounds):
    xmin, xmax, ymin, ymax = bounds
    data = np.asarray([_xy(p) for p in points], dtype=float)
    return np.column_stack(((data[:, 0]-xmin)/(xmax-xmin), (data[:, 1]-ymin)/(ymax-ymin)))


def _coordinate_keys(coords, tolerance):
    return [tuple(v) for v in np.rint(coords/max(tolerance, 1e-12)).astype(np.int64)]


def _edge_key(a, b):
    return (a, b) if a <= b else (b, a)


def _true_runs(mask):
    runs=[]; start=None
    for index, value in enumerate(list(mask)+[False]):
        if value and start is None:
            start=index
        elif not value and start is not None:
            runs.append((start, index))
            start=None
    return runs


def _domain_fraction(segments, bounds):
    span=bounds[1]-bounds[0]
    if span <= 0 or not segments:
        return 0.0
    intervals=sorted((min(_xy(p)[0] for p in s), max(_xy(p)[0] for p in s)) for s in segments)
    merged=[]
    for left,right in intervals:
        if merged and left <= merged[-1][1]:
            merged[-1]=(merged[-1][0],max(merged[-1][1],right))
        else:
            merged.append((left,right))
    return min(1.0,sum(right-left for left,right in merged)/span)


def _split_contiguous(points, accepted, coords, jump_limit):
    runs=[]; start=None
    for index, keep in enumerate(list(accepted)+[False]):
        if keep and start is None:
            start=index
        elif not keep and start is not None:
            runs.append(list(range(start,index))); start=None
    segments=[]
    for run in runs:
        current=[run[0]]
        local=np.linalg.norm(np.diff(coords[run],axis=0),axis=1) if len(run)>1 else np.asarray([])
        typical=float(np.median(local[local>0])) if np.any(local>0) else 0.0
        threshold=max(jump_limit, typical*12)
        for previous,index in zip(run,run[1:]):
            if float(np.linalg.norm(coords[index]-coords[previous])) > threshold:
                segments.append(current); current=[index]
            else:
                current.append(index)
        segments.append(current)
    return segments


def _remove_foreign_islands(segments, coords, jump_limit, minimum_points):
    """Remove a short excursion when the surrounding path reconnects locally."""
    removed=[]; changed=True
    while changed and len(segments)>=3:
        changed=False
        for index in range(1,len(segments)-1):
            before,current,after=segments[index-1:index+2]
            direct=float(np.linalg.norm(coords[after[0]]-coords[before[-1]]))
            enter=float(np.linalg.norm(coords[current[0]]-coords[before[-1]]))
            leave=float(np.linalg.norm(coords[after[0]]-coords[current[-1]]))
            short=len(current) <= max(minimum_points*3, int(.25*(len(before)+len(after))))
            if short and direct <= jump_limit*2 and min(enter,leave) > max(jump_limit,direct*2):
                removed.extend(current); segments=segments[:index]+segments[index+1:]
                changed=True; break
    return segments,removed


def _remove_overlapping_candidates(segments, coords, separation, support_ratio):
    """Resolve duplicate local candidates by continuity support, never by value."""
    removed=[]; unresolved=0; active=list(segments)
    changed=True
    while changed:
        changed=False
        for i in range(len(active)):
            for j in range(i+1,len(active)):
                a,b=active[i],active[j]
                ax,ay=coords[a,0],coords[a,1]; bx,by=coords[b,0],coords[b,1]
                left=max(float(ax.min()),float(bx.min())); right=min(float(ax.max()),float(bx.max()))
                shorter=max(1e-12,min(float(ax.max()-ax.min()),float(bx.max()-bx.min())))
                if right<=left or (right-left)/shorter < .5:
                    continue
                grid=np.linspace(left,right,25)
                av=np.interp(grid,np.sort(ax),ay[np.argsort(ax)])
                bv=np.interp(grid,np.sort(bx),by[np.argsort(bx)])
                if float(np.median(np.abs(av-bv))) <= separation:
                    continue
                unresolved+=1
                if len(a) >= len(b)*support_ratio:
                    drop=j
                elif len(b) >= len(a)*support_ratio:
                    drop=i
                else:
                    removed.extend(a);removed.extend(b)
                    active=[s for k,s in enumerate(active) if k not in (i,j)]
                    changed=True;break
                removed.extend(active[drop]);active.pop(drop);changed=True;break
            if changed:break
    return active,removed,unresolved


def _diagnostic(curve, segment_id, reason, points, coords, competitors=None, resolution_class="unknown", note=None):
    values=np.asarray([_xy(p) for p in points],dtype=float)
    tangent=(coords[-1]-coords[0]).tolist() if len(coords)>1 else [0.0,0.0]
    pixels=[[p.get('raw_pixel_x'),p.get('raw_pixel_y')] for p in points]
    if not all(all(v is not None for v in pair) for pair in pixels): pixels=None
    return dict(segment_id=segment_id,curve_id=curve['curve_id'],condition_id=curve['condition_id'],branch=curve['branch'],
        status='unresolved',failure_reason=reason,resolution_class=resolution_class,
        start_candidate=points[0].get('candidate_id',points[0]['point_id']),
        end_candidate=points[-1].get('candidate_id',points[-1]['point_id']),
        candidate_ids=[p.get('candidate_id',p['point_id']) for p in points],pixel_coordinates=pixels,
        mapped_coordinates=values.tolist(),local_tangent=tangent,local_curvature=None,
        competing_paths=list(competitors or []),competing_branch_ids=list(competitors or []),
        component_ids=list(dict.fromkeys(p.get('component_id') for p in points if p.get('component_id') is not None)),
        shared_candidate_ids=[],local_confidence='medium' if resolution_class=='algorithmically_resolvable' else 'low',
        diagnostic_note=note,temperature_range=[float(values[:,0].min()),float(values[:,0].max())],
        uwc_range=[float(values[:,1].min()),float(values[:,1].max())])


def isolate_continuous_curves(curves, raw_by_curve, cfg):
    """Return accepted curve-local segments and reproducible contamination QA."""
    groups=defaultdict(list)
    for curve in curves:
        groups[_source_key(curve)].append(curve["curve_id"])
    results={}
    exact_tol=cfg["trace_shared_coordinate_tolerance_normalized"]
    near_tol=cfg["trace_shared_near_tolerance_normalized"]
    shared_limit=cfg["trace_shared_path_fraction_threshold"]
    near_limit=cfg["trace_shared_near_fraction_threshold"]
    minimum_run=max(1,int(cfg["trace_shared_run_min_points"]))
    minimum_segment=max(2,int(cfg["trace_isolation_min_segment_points"]))
    jump_limit=cfg["trace_local_jump_threshold_normalized"]
    separation=cfg["trace_multimodal_y_separation_normalized"]
    support_ratio=cfg["trace_candidate_support_ratio"]
    for curve_ids in groups.values():
        bounds=_bounds(raw_by_curve,curve_ids)
        if bounds is None:
            continue
        ordered={cid:_ordered(raw_by_curve.get(cid,[])) for cid in curve_ids}
        coords={cid:_normalized(points,bounds) if points else np.empty((0,2)) for cid,points in ordered.items()}
        keys={cid:_coordinate_keys(coords[cid],exact_tol) for cid in curve_ids}
        keysets={cid:set(keys[cid]) for cid in curve_ids}
        edges={cid:{_edge_key(a,b) for a,b in zip(keys[cid],keys[cid][1:]) if a!=b} for cid in curve_ids}
        curve_map={c['curve_id']:c for c in curves}
        for cid in curve_ids:
            points=ordered[cid]; n=len(points)
            diagnostics=[];diagnostic_index=0
            if n<2:
                results[cid]=dict(segments=[],curve_isolation_status="failed",accepted_raw_point_count=0,
                    excluded_contaminated_point_count=n,unresolved_segment_count=1 if n else 0,
                    shared_exact_coordinate_count=0,shared_near_coordinate_fraction=0.0,
                    shared_segment_fraction=0.0,trace_domain_coverage_fraction=0.0,
                    accepted_domain_fraction=0.0,unresolved_domain_fraction=1.0,
                    isolation_warning_codes=["insufficient_curve_local_geometry"])
                continue
            others=[other for other in curve_ids if other!=cid and len(coords[other])]
            other_keys=set().union(*(keysets[o] for o in others)) if others else set()
            exact=np.asarray([key in other_keys for key in keys[cid]],dtype=bool)
            other_edges=set().union(*(edges[o] for o in others)) if others else set()
            shared_edges=np.asarray([_edge_key(a,b) in other_edges and a!=b for a,b in zip(keys[cid],keys[cid][1:])],dtype=bool)
            shared_segment_fraction=float(np.count_nonzero(shared_edges)/max(1,n-1))
            near=np.zeros(n,dtype=bool)
            for other in others:
                target=coords[other]
                for start in range(0,n,256):
                    distance=np.linalg.norm(coords[cid][start:start+256,None,:]-target[None,:,:],axis=2)
                    near[start:start+256] |= np.min(distance,axis=1) <= near_tol
            near_fraction=float(np.count_nonzero(near)/n)
            warnings=[]
            if shared_segment_fraction > shared_limit or near_fraction > near_limit:
                warnings.append("shared_path_contamination_warning")
            excluded=np.zeros(n,dtype=bool); unresolved=0
            # A crossing creates no sustained shared edge run and remains accepted.
            for start,end in _true_runs(shared_edges):
                if end-start >= minimum_run:
                    excluded[start:end+1]=True; unresolved+=1
                    run_edges={_edge_key(a,b) for a,b in zip(keys[cid][start:end+1],keys[cid][start+1:end+2]) if a!=b}
                    competitors=[other for other in others if run_edges & edges[other]]
                    diagnostic_index+=1
                    diagnostics.append(_diagnostic(curve_map[cid],f"{cid}_unresolved_{diagnostic_index:03d}",
                        'shared_path_candidate_collision',points[start:end+1],coords[cid][start:end+1],competitors,
                        'source_intrinsic_or_identity_unresolved','Candidate/component ownership is required to distinguish true overlap from reuse.'))
            segments=_split_contiguous(points,~excluded,coords[cid],jump_limit)
            jump_splits=max(0,len(segments)-max(1,len(_true_runs(~excluded))))
            if jump_splits:
                warnings.append("abrupt_path_jump_warning"); unresolved+=jump_splits
                base_runs=_true_runs(~excluded)
                for run_start,run_end in base_runs:
                    run=list(range(run_start,run_end))
                    local=np.linalg.norm(np.diff(coords[cid][run],axis=0),axis=1) if len(run)>1 else np.asarray([])
                    typical=float(np.median(local[local>0])) if np.any(local>0) else 0.0
                    threshold=max(jump_limit,typical*12)
                    for a,b in zip(run,run[1:]):
                        if float(np.linalg.norm(coords[cid][b]-coords[cid][a])) > threshold:
                            diagnostic_index+=1
                            diagnostics.append(_diagnostic(curve_map[cid],f"{cid}_unresolved_{diagnostic_index:03d}",
                                'abrupt_path_discontinuity',[points[a],points[b]],coords[cid][[a,b]],[],
                                'algorithmically_resolvable','Use graph/path continuity; do not bridge this gap.'))
            segments,foreign=_remove_foreign_islands(segments,coords[cid],jump_limit,minimum_segment)
            if foreign:
                excluded[foreign]=True; warnings.append("foreign_path_excursion_warning"); unresolved+=1
                diagnostic_index+=1
                diagnostics.append(_diagnostic(curve_map[cid],f"{cid}_unresolved_{diagnostic_index:03d}",
                    'shared_path_candidate_collision',[points[i] for i in foreign],coords[cid][foreign],[],
                    'algorithmically_resolvable','Short foreign excursion reconnects to the local path.'))
            segments,overlap_removed,overlap_unresolved=_remove_overlapping_candidates(
                segments,coords[cid],separation,support_ratio)
            if overlap_removed:
                excluded[overlap_removed]=True
                warnings.append("multimodal_path_candidate_warning")
                unresolved+=overlap_unresolved
                # One diagnostic per unresolved decision; exact sub-path identity is unavailable in legacy raw data.
                for _ in range(overlap_unresolved):
                    diagnostic_index+=1
                    subset=overlap_removed[:max(2,min(len(overlap_removed),minimum_segment*4))]
                    diagnostics.append(_diagnostic(curve_map[cid],f"{cid}_unresolved_{diagnostic_index:03d}",
                        'multimodal_candidate_set',[points[i] for i in subset],coords[cid][subset],[],
                        'algorithmically_resolvable','Legacy x-overlap/support-count decision requires 2-D candidate graph resolution.'))
            kept=[]
            for segment in segments:
                if len(segment)<minimum_segment:
                    excluded[segment]=True; unresolved+=1
                    diagnostic_index+=1
                    diagnostics.append(_diagnostic(curve_map[cid],f"{cid}_unresolved_{diagnostic_index:03d}",
                        'insufficient_local_geometry',[points[i] for i in segment],coords[cid][segment],[],
                        'source_intrinsic_ambiguity','Too few local candidates remain after conservative exclusion.'))
                else:
                    kept.append([points[i] for i in segment])
            accepted_count=sum(len(s) for s in kept)
            coverage=_domain_fraction(kept,bounds)
            if excluded.any() and "shared_path_contamination_warning" not in warnings:
                warnings.append("curve_local_geometry_excluded")
            if not accepted_count:
                status="failed"
            elif excluded.any() or unresolved:
                status="partial"
                warnings.append("unresolved_curve_isolation")
            elif warnings:
                status="review_required"
            else:
                status="pass"
            results[cid]=dict(segments=kept,curve_isolation_status=status,
                accepted_raw_point_count=accepted_count,
                excluded_contaminated_point_count=int(np.count_nonzero(excluded)),
                unresolved_segment_count=unresolved,
                shared_exact_coordinate_count=int(np.count_nonzero(exact)),
                shared_near_coordinate_fraction=near_fraction,
                shared_segment_fraction=shared_segment_fraction,
                trace_domain_coverage_fraction=coverage,accepted_domain_fraction=coverage,
                unresolved_domain_fraction=max(0.0,1.0-coverage),
                isolation_warning_codes=list(dict.fromkeys(warnings)),segment_diagnostics=diagnostics)
    return results
