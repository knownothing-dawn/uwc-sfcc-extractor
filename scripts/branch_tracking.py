"""Curve-aware two-branch tracking for already detected, same-style marker candidates."""
import math
import heapq


def track_two_branches(columns, seeds, continuity_weight=1.0, slope_weight=.35, crossing_penalty=4.0):
    """Track two branches with dynamic programming; never invents or interpolates candidates.

    ``columns`` is an ordered list of ``[(x, y, raw_id), ...]`` candidate groups.
    ``seeds`` gives the expected y for branch A/B in the first column. Ambiguous
    columns are returned unresolved instead of being force-assigned.
    """
    if len(seeds) != 2 or not columns or any(len(c) < 2 for c in columns):
        raise ValueError("Two branch seeds and at least two candidates per column are required")
    states = []
    for column in columns:
        pairs = [(i, j) for i in range(len(column)) for j in range(len(column)) if i != j]
        states.append(pairs)
    costs = {}
    back = []
    first = columns[0]
    for state in states[0]:
        costs[state] = abs(first[state[0]][1] - seeds[0]) + abs(first[state[1]][1] - seeds[1])
    for index in range(1, len(columns)):
        current, previous = {}, {}
        for state in states[index]:
            xa, ya, _ = columns[index][state[0]]; xb, yb, _ = columns[index][state[1]]
            options = []
            for old, old_cost in costs.items():
                pxa, pya, _ = columns[index-1][old[0]]; pxb, pyb, _ = columns[index-1][old[1]]
                continuity = abs(ya-pya) + abs(yb-pyb)
                slope = abs((ya-pya)/max(abs(xa-pxa), 1e-12)) + abs((yb-pyb)/max(abs(xb-pxb), 1e-12))
                crossed = (pya-pyb) * (ya-yb) < 0
                options.append((old_cost + continuity_weight*continuity + slope_weight*slope + crossing_penalty*crossed, old))
            current[state], previous[state] = min(options)
        costs, back = current, back + [previous]
    state = min(costs, key=costs.get)
    chosen = [state]
    for previous in reversed(back):
        state = previous[state]; chosen.append(state)
    chosen.reverse()
    tracks = [[], []]
    unresolved = []
    for i, state in enumerate(chosen):
        a, b = columns[i][state[0]], columns[i][state[1]]
        tracks[0].append(a); tracks[1].append(b)
        if math.isclose(a[1], b[1], rel_tol=0, abs_tol=1e-6):
            unresolved.append(i)
    return {"tracks": tracks, "unresolved_columns": unresolved, "total_cost": costs[chosen[-1]]}


def _shortest_graph_path(nodes, spec, max_edge_distance, forbidden=frozenset()):
    by_id = {n['candidate_id']: n for n in nodes}
    start, end = spec['start_id'], spec['end_id']
    if start not in by_id or end not in by_id:
        return None
    ordered = sorted(nodes, key=lambda n: (n['path_order'], n['candidate_id']))
    distance = {start: 0.0}; previous = {}
    for current in ordered:
        cid = current['candidate_id']
        if cid not in distance or cid in forbidden and cid not in (start,end):
            continue
        for nxt in ordered:
            nid = nxt['candidate_id']
            if nxt['path_order'] <= current['path_order'] or nid in forbidden and nid != end:
                continue
            step = math.hypot(nxt['x']-current['x'], nxt['y']-current['y'])
            if step > max_edge_distance:
                continue
            component_penalty = 0.0 if nxt.get('component_id') in (None, spec.get('seed_component')) else max_edge_distance
            marker_penalty = 0.0 if nxt.get('marker_identity') in (None, spec.get('seed_component')) else max_edge_distance*.5
            cost = distance[cid] + step + component_penalty + marker_penalty
            if cost < distance.get(nid, math.inf):
                distance[nid] = cost; previous[nid] = cid
    if end not in distance:
        return None
    path=[end]
    while path[-1] != start:
        if path[-1] not in previous: return None
        path.append(previous[path[-1]])
    return list(reversed(path)), distance[end]


def _segments(path, by_id):
    return [(by_id[a],by_id[b]) for a,b in zip(path[:-1],path[1:])]


def _proper_intersection(a,b,c,d,eps=1e-9):
    def orient(p,q,r): return (q['x']-p['x'])*(r['y']-p['y'])-(q['y']-p['y'])*(r['x']-p['x'])
    o1,o2,o3,o4=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
    return o1*o2 <= eps and o3*o4 <= eps and max(min(a['x'],b['x']),min(c['x'],d['x'])) <= min(max(a['x'],b['x']),max(c['x'],d['x']))+eps


def joint_track_candidate_graph(candidates, branch_specs, max_edge_distance):
    """Jointly assign two graph paths without requiring x columns.

    Candidate reuse is forbidden unless ``confirmed_shared`` is explicit. If no
    disjoint evidence-backed solution exists, conflicts remain unresolved and no
    gap is bridged.
    """
    if set(branch_specs) != {'freezing','thawing'} or max_edge_distance <= 0:
        raise ValueError('A freezing/thawing pair and positive edge limit are required')
    ids=[n['candidate_id'] for n in candidates]
    if len(ids)!=len(set(ids)):
        raise ValueError('candidate_id must be unique')
    confirmed={n['candidate_id'] for n in candidates if n.get('confirmed_shared')}
    options=[]
    for first,second in (('freezing','thawing'),('thawing','freezing')):
        one=_shortest_graph_path(candidates,branch_specs[first],max_edge_distance)
        if not one: continue
        occupied=set(one[0])-confirmed
        two=_shortest_graph_path(candidates,branch_specs[second],max_edge_distance,occupied)
        if two:
            paths={first:one[0],second:two[0]};options.append((one[1]+two[1],paths))
    unresolved=[]
    if options:
        _,paths=min(options,key=lambda item:item[0])
    else:
        independent={b:_shortest_graph_path(candidates,s,max_edge_distance) for b,s in branch_specs.items()}
        if any(v is None for v in independent.values()):
            return {'status':'unresolved','paths':{b:(v[0] if v else []) for b,v in independent.items()},
                    'candidate_assignments':{},'confirmed_shared_ids':sorted(confirmed),
                    'unresolved_candidate_ids':[], 'true_crossing_count':0,'identity_switch_count':0,'bridged':False}
        paths={b:v[0] for b,v in independent.items()}
        unresolved=sorted((set(paths['freezing']) & set(paths['thawing']))-confirmed)
    assignments={}
    for branch,path in paths.items():
        for cid in path: assignments.setdefault(cid,[]).append(branch)
    by_id={n['candidate_id']:n for n in candidates}
    switches=0
    for branch,path in paths.items():
        seed=branch_specs[branch].get('seed_component')
        switches += sum(by_id[cid].get('component_id') not in (None,seed) and cid not in confirmed for cid in path)
    coincident={(round(by_id[a]['x'],9),round(by_id[a]['y'],9)) for a in paths['freezing'] for b in paths['thawing']
                if a!=b and math.isclose(by_id[a]['x'],by_id[b]['x'],abs_tol=1e-9) and math.isclose(by_id[a]['y'],by_id[b]['y'],abs_tol=1e-9)}
    crossings=len(coincident)
    for a,b in _segments(paths['freezing'],by_id):
        for c,d in _segments(paths['thawing'],by_id):
            if {a['candidate_id'],b['candidate_id']} & {c['candidate_id'],d['candidate_id']}:
                continue
            if any((round(p['x'],9),round(p['y'],9)) in coincident for p in (a,b,c,d)):
                continue
            if _proper_intersection(a,b,c,d): crossings+=1
    return {'status':'unresolved' if unresolved else 'pass','paths':paths,'candidate_assignments':assignments,
            'confirmed_shared_ids':sorted(confirmed & set(assignments)),
            'unresolved_candidate_ids':unresolved,'true_crossing_count':crossings,
            'identity_switch_count':switches,'bridged':False}
