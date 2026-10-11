"""Evidence-led expectations and point-level accounting, independent of export."""
import copy
import hashlib
from collections import defaultdict
from semantics import data_semantics, numerical_expected, point_expectations, point_set, representation

DEFAULT_SETTINGS = {'temperature_match_tolerance_celsius': .15,
    'volumetric_warning_threshold': .003, 'volumetric_strong_threshold': .010,
    'normalized_warning_threshold': .01,
    'trace_simplification_tolerance_normalized': .005,
    'trace_x_tolerance_normalized': .00075,
    'trace_denoise_tolerance_normalized': .001,
    'trace_transition_tolerance_factor': .35,
    'trace_centerline_fidelity_p95_threshold_normalized': .01,
    'trace_shared_coordinate_tolerance_normalized': .00001,
    'trace_shared_near_tolerance_normalized': .0015,
    'trace_shared_path_fraction_threshold': .05,
    'trace_shared_near_fraction_threshold': .65,
    'trace_shared_run_min_points': 5,
    'trace_local_jump_threshold_normalized': .08,
    'trace_isolation_min_segment_points': 3,
    'trace_multimodal_y_separation_normalized': .03,
    'trace_candidate_support_ratio': 1.25,
    'trace_oversampled_absolute_count': 250,
    'trace_oversampled_fraction': .35,
    'axis_anchor_residual_tolerance': .25,
    'reverse_jump_warning': .003,
    'reverse_jump_severe': .010,
    'initial_theta_warning': .003,
    'initial_theta_severe': .010,
    'branch_exact_value_tolerance': 1e-12,
    'branch_near_value_tolerance': .001,
    'branch_duplicate_fraction_threshold': .5,
    'branch_order_switch_threshold': 2}
DEFAULT_SETTINGS['trace_enforce_segment_fidelity'] = 0


def settings(package):
    return {**DEFAULT_SETTINGS, **package.get('qa_settings', {})}


def branch_key(branch):
    return {'cooling': 'freezing', 'warming': 'thawing'}.get(branch, branch)


def dataset_identity(item, keys):
    return keys[item['condition_id']], branch_key(item['branch']), data_semantics(item), item.get('series_variant_reported')


def series_key(package, condition_id, branch, kind):
    from coverage import condition_keys
    return condition_keys(package)[condition_id], branch_key(branch), data_semantics({'curve_data_type': kind})


def unknown_points():
    return dict(count=None, temperatures_celsius=[], information_type='unspecified',
        evidence_ids=[], source_points_verified=False, gap_resolution='unresolved',
        resolution_evidence_ids=[], explanation=None)


def build_manifest(package):
    """Expand independent design/evidence; never enumerate recovered curves."""
    from coverage import condition_keys
    keys = condition_keys(package)
    existing = {dataset_identity(m, keys): copy.deepcopy(m)
                for m in package.get('expected_datasets', [])}
    conditions = {c['condition_id']: c for c in package['conditions']}
    planned = {}
    def add(cid, branch, kind, evidence_ids, factor='none', variant=None, semantics=None, representation=None):
        source = dict(condition_id=cid, branch=branch, curve_data_type=kind, series_variant_reported=variant)
        if semantics: source['data_semantics'] = semantics
        key = dataset_identity(source, keys)
        if key not in planned:
            base = existing.get(key)
            if base is None:
                base = dict(expected_curve_id='expected_' + hashlib.sha256(repr(key).encode()).hexdigest()[:20],
                    sample_id=conditions[cid]['sample_id'], condition_id=cid, experimental_factors=[],
                    condition_values=[dict(property=p['property'], value=p['value'], unit=p['unit'], evidence_ids=p['evidence_ids'])
                        for p in package['soil_properties'] if p['condition_id'] == cid],
                    branch=branch, curve_data_type=kind, expected_source_ids=[], evidence_ids=[],
                    measurement_status='expected', exclusion_evidence_ids=[], expected_point_information=unknown_points())
            planned[key] = base
            if variant is not None: base['series_variant_reported'] = variant
        item = planned[key]
        if semantics: item['data_semantics'] = semantics
        if representation: item['representation'] = representation
        for field in ('expected_source_ids', 'evidence_ids'):
            item[field] = list(dict.fromkeys(item[field] + list(evidence_ids)))
        if factor != 'none' and factor not in item['experimental_factors']:
            item['experimental_factors'].append(factor)
    if package.get('experimental_cases'):
        for case in package['experimental_cases']:
            for cid in case['condition_ids']:
                for branch in case['branches']:
                    for kind in case['curve_data_types']:
                        add(cid, branch, kind, case['evidence_ids'], case['varying_property'])
    else:
        for evidence in package['evidence']:
            for item in evidence.get('expected_series', []):
                add(item['condition_id'], item['branch'], item['curve_data_type'], [evidence['evidence_id']], variant=item.get('series_variant_reported'),
                    semantics=item.get('data_semantics'), representation=item.get('representation'))
    # A manually evidence-backed manifest is also a valid independent inventory.
    for key, item in existing.items():
        planned.setdefault(key, item)
    package['expected_datasets'] = list(planned.values())
    return package['expected_datasets']


def point_coverage(package):
    from coverage import condition_keys
    keys = condition_keys(package)
    points = defaultdict(list)
    for point in package['uwc_points']:
        points[point['curve_id']].append(point)
    curves = defaultdict(list)
    for c in package['curves']:
        if points[c['curve_id']]:
            curves[dataset_identity(c, keys)].append(c)
    rows = []
    tolerance = settings(package)['temperature_match_tolerance_celsius']
    for expected in package.get('expected_datasets', []):
        if not numerical_expected(expected):
            continue
        info = expected['expected_point_information']
        matching = curves.get(dataset_identity(expected, keys), [])
        visible = set(package.get('coverage', {}).get('unique_curve_ids', [c['curve_id'] for c in matching]))
        matching = [c for c in matching if c['curve_id'] in visible]
        curve = matching[0] if len(matching) == 1 else None
        observations = points[curve['curve_id']] if curve else []
        expectations = point_expectations(info, curve)
        continuous = representation(curve or expected) == 'continuous_measured_trace'
        if continuous:
            # Raster/vector coordinates and simplified vertices describe one
            # continuous observation. They are never a hard point denominator.
            status = 'complete' if curve and observations else 'not_checked'
            rows.append(dict(expected_curve_id=expected['expected_curve_id'],
                curve_id=curve['curve_id'] if curve else None, expected_count=None,
                extracted_count=len(observations), missing_count=0,
                missing_temperatures_celsius=[], status=status,
                explanation=info.get('explanation'), **expectations,
                protocol_difference_count=0, protocol_missing_temperatures_celsius=[],
                reported_missing_count=0, observable_missing_count=0))
            continue
        def compare(spec):
            unused = list(range(len(observations)))
            missing_temperatures = []
            for temperature in spec['temperatures_celsius']:
                candidates = [(abs(observations[i]['temperature_celsius'] - temperature), i) for i in unused]
                if candidates and min(candidates)[0] <= tolerance:
                    unused.remove(min(candidates)[1])
                else:
                    missing_temperatures.append(temperature)
            count = spec['count'] if spec['count'] is not None else len(spec['temperatures_celsius']) or None
            return count, max(len(missing_temperatures), (count or 0)-len(observations)), missing_temperatures
        count, reported_missing, missing_temperatures = compare(expectations['reported_expected'])
        _, protocol_missing, protocol_temperatures = compare(expectations['protocol_expected'])
        _, observable_missing, observable_temperatures = compare(expectations['source_observable'])
        if info.get('protocol_applies_to_output'):
            protocol_count = compare(expectations['protocol_expected'])[0]
            count = max(count or 0, protocol_count or 0) or None
            reported_missing = max(reported_missing, protocol_missing)
            missing_temperatures = list(dict.fromkeys(missing_temperatures + protocol_temperatures))
        missing = max(reported_missing, observable_missing)
        missing_temperatures = list(dict.fromkeys(missing_temperatures + observable_temperatures))
        complete_source = expectations['source_observable']['completeness'] == 'complete'
        status = ('missing_point_or_not_reported' if missing else 'complete' if curve and
            (count is not None or complete_source) and expectations['source_observable']['completeness'] != 'partial' else 'not_checked')
        rows.append(dict(expected_curve_id=expected['expected_curve_id'], curve_id=curve['curve_id'] if curve else None,
            expected_count=count, extracted_count=len(observations), missing_count=missing,
            missing_temperatures_celsius=missing_temperatures, status=status, explanation=info.get('explanation'),
            **expectations, protocol_difference_count=protocol_missing, protocol_missing_temperatures_celsius=protocol_temperatures,
            reported_missing_count=reported_missing, observable_missing_count=observable_missing))
    return dict(extracted_point_count=sum(len(points[cid]) for cid in package.get('coverage', {}).get('unique_curve_ids', points)),
        known_expected_point_count=sum(r['expected_count'] or 0 for r in rows),
        assessed_curve_count=sum(r['status'] != 'not_checked' for r in rows),
        unexplained_gap_count=sum(r['missing_count'] for r in rows if r['status'] == 'missing_point_or_not_reported'),
        explained_gap_count=0,
        protocol_expected_point_count=sum(r['protocol_expected']['count'] or len(r['protocol_expected']['temperatures_celsius']) for r in rows),
        reported_expected_point_count=sum(r['expected_count'] or 0 for r in rows),
        source_observable_point_count=sum(r['source_observable']['count'] or len(r['source_observable']['temperatures_celsius']) for r in rows),
        protocol_difference_count=sum(r['protocol_difference_count'] for r in rows),
        observable_missing_count=sum(r['observable_missing_count'] for r in rows),
        not_checked_curve_count=sum(r['status'] == 'not_checked' for r in rows), curves=rows)
