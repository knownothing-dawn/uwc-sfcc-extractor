"""Scientific preparation and conservative database-readiness gates."""
import copy
import math
from collections import defaultdict

from manifest import build_manifest, point_coverage, branch_key, settings, dataset_identity
from sources import resolve_variables, load_datasets, recover_missing, validate_anchors, VARIABLES, comparison_fingerprint
from semantics import semantic_errors, numerical_expected, data_semantics, representation, point_expectations, point_set, review_status


ISOLATION_REVIEW_WARNINGS = {
    'shared_path_contamination_warning', 'unresolved_curve_isolation',
    'multimodal_path_candidate_warning', 'abrupt_path_jump_warning',
    'foreign_path_excursion_warning', 'curve_local_geometry_excluded',
    'insufficient_curve_local_geometry',
    'large_same_x_extent_requires_segment_review',
}


def trace_review_text(trace):
    """Describe the failed trace stage without mislabeling it reconstruction."""
    warnings = set(trace.get('warnings', [])) | set(trace.get('isolation_warning_codes', []))
    tolerance = trace.get('simplification_tolerance_normalized')
    error = trace.get('max_normalized_reconstruction_error')
    reconstruction = ('raw_trace_exported_unsimplified' in warnings or
        (error is not None and tolerance is not None and error > tolerance + 1e-12))
    isolation = (trace.get('curve_isolation_status') in ('partial', 'review_required', 'failed') or
                 trace.get('unresolved_segment_count', 0) > 0 or bool(warnings & ISOLATION_REVIEW_WARNINGS))
    fidelity = ('centerline_fidelity_warning' in warnings or
        (trace.get('raw_to_centerline_p95_normalized_error') is not None and
         trace.get('centerline_fidelity_p95_threshold_normalized') is not None and
         trace['raw_to_centerline_p95_normalized_error'] >
         trace['centerline_fidelity_p95_threshold_normalized'] + 1e-12))
    if reconstruction and not (isolation or fidelity):
        return ('Continuous measured trace did not pass scientific-curve reconstruction QA.',
                'Review scientific-curve simplification and reconstruction error before autonomous import.')
    if isolation and fidelity and not reconstruction:
        return ('Continuous measured trace contains unresolved curve-isolation segments and raw-to-centerline fidelity concerns.',
                'Review the affected intervals before autonomous import.')
    if isolation and not reconstruction:
        return ('Continuous measured trace contains unresolved curve-isolation segments.',
                'Review the unresolved intervals before autonomous import.')
    if fidelity and not reconstruction:
        return ('Continuous measured trace did not pass raw-to-centerline fidelity QA.',
                'Review accepted trace geometry before autonomous import.')
    if reconstruction:
        return ('Continuous measured trace did not pass scientific-curve reconstruction QA and has additional trace-isolation or fidelity concerns.',
                'Review reconstruction error and the affected trace intervals before autonomous import.')
    return ('Continuous measured trace contains unresolved trace-processing issues.',
            'Review trace-processing warnings before autonomous import.')


def prepare_scientific(package, artifact_root):
    """Prepare privately; the caller runs full schema/reference QA before writing."""
    try:
        return _prepare_scientific(package, artifact_root)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        from quality import VALIDATOR
        errors = list(VALIDATOR.iter_errors(package))
        if errors: raise ValueError('; '.join(e.message for e in errors[:8])) from exc
        raise


def _prepare_scientific(package, artifact_root):
    from conversion import convert_preferred
    from trace_processing import process_continuous_traces
    # Output summaries are recomputed, so do not repeatedly validate stale summaries.
    computed = {'coverage', 'point_coverage', 'qa_gates', 'anchor_summary', 'source_failures'}
    source = {k:v for k,v in package.items() if k not in computed}
    result = copy.deepcopy(source)
    # Stale output fields never grant readiness to changed data.
    result['paper']['database_ready'] = False
    ids = {result['paper']['paper_id']}
    for field, key in [('samples','sample_id'),('conditions','condition_id'),('curves','curve_id'),('uwc_points','point_id'),
                       ('soil_properties','property_id'),('evidence','evidence_id'),('models','model_id'),('derivations','derivation_id')]:
        ids.update(row[key] for row in result[field])
    result['review_queue'] = [r for r in result['review_queue'] if r['generated_by']!='validator' or r['object_id'] in ids]
    errors = extra_issues(dict(result, reference_points=[], observation_selections=[], anchor_checks=[]))
    if errors: raise ValueError('; '.join(errors))
    resolve_variables(result)
    for row in result['curves'] + result.get('numerical_datasets', []):
        row.setdefault('data_semantics', data_semantics(row))
        row.setdefault('representation', representation(row))
    build_manifest(result)
    datasets = load_datasets(result, artifact_root)
    # Verified full numerical rows establish a hard denominator; sparse anchors do not.
    from coverage import condition_keys
    from sources import source_verified
    keys = condition_keys(result)
    evidence = {e['evidence_id']: e for e in result['evidence']}
    curves_by_identity = defaultdict(list)
    for curve in result['curves']:
        curves_by_identity[dataset_identity(curve, keys)].append(curve)
    for expected in result['expected_datasets']:
        expected.setdefault('data_semantics', data_semantics(expected))
        expected.setdefault('representation', representation(expected))
        expected.setdefault('target_quantity_status', 'unknown')
        expected.setdefault('availability_status', 'available')
        candidates = [d for d in datasets if d['coverage_role']=='full_series' and d['observations'] and
            dataset_identity(d, keys)==dataset_identity(expected, keys) and source_verified(d, evidence)]
        info = expected['expected_point_information']
        matches = curves_by_identity[dataset_identity(expected, keys)]
        if matches:
            candidates = [d for d in candidates if len(matches)==1 and all(
                d[k] == matches[0].get(k) for k in ('method', 'data_origin', 'uwc_basis', 'raw_variable'))]
        parts = point_expectations(info, matches[0] if len(matches)==1 else None)
        info.update(parts)
        if numerical_expected(expected) and len(candidates)==1 and parts['reported_expected']['count'] is None and not parts['reported_expected']['temperatures_celsius']:
            from science import convert_value
            source = candidates[0]
            parts['reported_expected'] = point_set(len(source['observations']),
                [convert_value(p['temperature'], p['temperature_unit'], 'degree_celsius') for p in source['observations']], source['evidence_ids'])
            info.update(parts)
    recover_missing(result, datasets, artifact_root)
    process_continuous_traces(result)
    convert_preferred(result, copy_package=False)
    validate_anchors(result, datasets)
    return result


def extra_issues(package):
    from science import convert_value
    from coverage import condition_keys
    from sources import PRIORITY
    errors = semantic_errors(package)
    evidence = {e['evidence_id']: e for e in package['evidence']}
    conditions = {c['condition_id']: c for c in package['conditions']}
    curves = {c['curve_id']: c for c in package['curves']}
    points = {p['point_id']: p for p in package['uwc_points']}
    references = {p['point_id']: p for p in package.get('reference_points', [])}
    datasets = {d['dataset_id']: d for d in package.get('numerical_datasets', [])}
    keys = condition_keys(package)
    identifiers = set()
    for item in package.get('expected_datasets', []) + package.get('numerical_datasets', []):
        identifier = item.get('expected_curve_id', item.get('dataset_id'))
        if identifier in identifiers: errors.append('Duplicate manifest/numerical dataset ID: ' + identifier)
        identifiers.add(identifier)
        condition = conditions.get(item['condition_id'])
        if not condition or condition['sample_id'] != item['sample_id']:
            errors.append(identifier + ': wrong sample/condition binding')
        if 'cycle_number' in item and condition and item['cycle_number'] != condition['cycle_number']:
            errors.append(identifier + ': wrong cycle binding')
        if item.get('measurement_status') == 'explicitly_not_measured':
            quote = item.get('exclusion_reason_reported')
            cited = [evidence.get(e, {}) for e in item['exclusion_evidence_ids']]
            if not quote or not cited or not all(e.get('transcription_status') == 'verified' for e in cited) or not any(
                    quote in (e.get('quoted_evidence') or '') for e in cited):
                errors.append(identifier + ': excluding an unmeasured condition requires the explicit verified source statement')
    limits = settings(package)
    if limits['volumetric_strong_threshold'] < limits['volumetric_warning_threshold']:
        errors.append('Strong anchor threshold must be at least the warning threshold')
    selections = set()
    for curve in package['curves']:
        if curve.get('plotted_uwc_axis_span') is not None and (curve['plotted_uwc_axis_span'] <= 0 or not curve.get('plotted_uwc_axis_unit')):
            errors.append('Plotted UWC span requires a positive value and explicit unit')
    for item in package.get('expected_datasets', []):
        for field in ('expected_source_ids', 'exclusion_evidence_ids'):
            if any(e not in evidence for e in item[field]): errors.append('Manifest refers to missing source evidence')
        info = item['expected_point_information']
        if any(e not in evidence for e in info.get('resolution_evidence_ids', [])): errors.append('Point-gap resolution refers to missing evidence')
    for choice in package.get('observation_selections', []):
        point, reference = points.get(choice['point_id']), references.get(choice['reference_point_id'])
        if choice['point_id'] in selections: errors.append('Multiple selected references for one graphical observation')
        selections.add(choice['point_id'])
        if not point or not reference or point['curve_id'] != reference['curve_id']:
            errors.append('Anchor selection has a missing or incorrect curve/point binding');continue
        if point['uwc_original_basis'] != reference['uwc_original_basis'] or abs(point['temperature_celsius']-reference['temperature_celsius']) > limits['temperature_match_tolerance_celsius']:
            errors.append('Anchor selection changes the scientific variable or temperature identity')
        if not any(c['selected'] and c['point_id'] == point['point_id'] and c['reference_point_id'] == reference['point_id']
                   for c in package.get('anchor_checks', [])):
            errors.append('Selected exact observation lacks its numerical comparison')
    for check in package.get('anchor_checks', []):
        if check['point_id'] and check['point_id'] not in points: errors.append('Anchor check references a missing graphical point')
        if check['reference_point_id'] and check['reference_point_id'] not in references: errors.append('Anchor check references a missing exact observation')
        point, reference = points.get(check['point_id']), references.get(check['reference_point_id'])
        source = datasets.get(check['dataset_id'])
        if not source: errors.append('Anchor comparison refers to a missing numerical dataset');continue
        if not point or not reference: continue
        curve = curves.get(point['curve_id'])
        if not curve or reference['curve_id'] != point['curve_id'] or dataset_identity(curve, keys) != dataset_identity(source, keys):
            errors.append('Anchor comparison changes the source/curve identity');continue
        unit = check['comparison_unit']
        try:
            a, b = (point['uwc_preferred_value'], reference['uwc_preferred_value']) if unit=='cubic_meter_per_cubic_meter' else (
                convert_value(point['uwc_original_value'],point['uwc_original_unit'],unit,curve['uwc_basis']),
                convert_value(reference['uwc_original_value'],reference['uwc_original_unit'],unit,curve['uwc_basis']))
            error = abs(a-b)
            if check['absolute_error'] is None or not math.isclose(error,check['absolute_error'],abs_tol=1e-12):
                errors.append('Stale anchor discrepancy; recompute the numerical comparison')
            if unit=='cubic_meter_per_cubic_meter' and error>limits['volumetric_strong_threshold']+1e-12 and check['status'] not in ('strong_warning','conflicting_references'):
                errors.append('A strong numerical discrepancy cannot be downgraded without source resolution')
            if check['selected']:
                candidates=[datasets[c['dataset_id']] for c in package.get('anchor_checks',[]) if c['point_id']==point['point_id'] and c['reference_point_id'] and c['dataset_id'] in datasets]
                if any(PRIORITY[d['source_kind']] < PRIORITY[source['source_kind']] for d in candidates):
                    errors.append('Selected numerical source violates source priority')
        except (ValueError,TypeError): errors.append('Anchor comparison has incompatible or missing numerical quantities')
    for point in references.values():
        curve = curves.get(point['curve_id'])
        if not curve or curve['uwc_basis'] != point['uwc_original_basis']:
            errors.append('Reference observation has an incorrect variable binding')
    return errors


def finalize_qa(package, warn):
    """Called after base QA so gates use current facts, never persisted approval flags."""
    from quality import review_severity
    from science import property_role, experiment_role_compatible
    from coverage import curve_coverage, condition_keys
    resolve_variables(package)
    if not package.get('expected_datasets'): build_manifest(package)
    coverage = curve_coverage(package)
    package['coverage'] = coverage
    expected = package.get('expected_datasets', [])
    active = [m for m in expected if numerical_expected(m)]
    keys = condition_keys(package)
    missing = {dataset_identity(m, keys) for m in coverage['missing_conditions']}
    coverage.update(curve_coverage_percentage=coverage['coverage_percentage'],
        missing_curves=[m['expected_curve_id'] for m in active if dataset_identity(m, keys) in missing],
        unexpected_curves=[c['curve_id'] for c in package['curves'] if any(dataset_identity(c, keys) == dataset_identity(x, keys) for x in coverage['unexpected_conditions'])],
        ambiguous_curves=[c['curve_id'] for c in package['curves'] if c['branch'] in ('unknown', 'other') or c['confidence'] == 'low'])
    pc = point_coverage(package);package['point_coverage'] = pc
    for row in pc['curves']:
        if row['status'] == 'missing_point_or_not_reported':
            warn('curve' if row['curve_id'] else 'paper', row['curve_id'] or package['paper']['paper_id'],
                'missing_point_or_not_reported', f"{row['missing_count']} reported or source-identifiable observations remain unextracted; no values were interpolated.",
                action='Revisit the bound source and record recovered observations or an evidence-backed explanation.')
    resolutions = {r['check_id']: r for r in package.get('anchor_resolutions', [])}
    evidence = {e['evidence_id']: e for e in package['evidence']}
    def resolved(check):
        r = resolutions.get(check['check_id'])
        return bool(r and r['neighbor_points_checked'] and r['explanation'] and r['evidence_ids'] and
                    r.get('comparison_fingerprint') == comparison_fingerprint(check, graphical.get(check['point_id']), exact.get(check['reference_point_id'])) and
                    all(evidence.get(e, {}).get('transcription_status') == 'verified' for e in r['evidence_ids']))
    checks = package.get('anchor_checks', [])
    graphical = {p['point_id']: p for p in package['uwc_points']}
    exact = {p['point_id']: p for p in package.get('reference_points', [])}
    critical_statuses = {'strong_warning', 'ambiguous', 'incompatible_variable', 'conflicting_references', 'unmatched'}
    unresolved = [c for c in checks if c['status'] in critical_statuses and not resolved(c)]
    grouped = defaultdict(list)
    for c in checks:
        if c['status'] != 'within_tolerance' and not resolved(c): grouped[c['curve_id']].append(c)
    for cid, group in grouped.items():
        critical = any(c in unresolved for c in group)
        largest = max((c['absolute_error'] or 0 for c in group), default=0)
        warn('curve' if cid else 'paper', cid or package['paper']['paper_id'], 'anchor_conflict',
            f"{len(group)} cross-source comparison(s) require review; maximum absolute discrepancy {largest:.4g}.",
            'critical' if critical else 'important',
            'Resolve the cited source discrepancy after checking identity and neighboring points.')
    for failure in package.get('source_failures', []):
        warn('paper', package['paper']['paper_id'], 'source_verification_required', 'Bound numerical source is unavailable or changed: ' + failure['message'])
    units = {c['comparison_unit'] for c in checks if c['absolute_error'] is not None}
    numeric = [c['absolute_error'] for c in checks if c['absolute_error'] is not None]
    package['anchor_summary'] = dict(checked_count=len(numeric), within_tolerance_count=sum(c['status']=='within_tolerance' for c in checks),
        warning_count=sum(c['status']=='warning' for c in checks), strong_warning_count=sum(c['status']=='strong_warning' for c in checks),
        unresolved_count=len(unresolved), selected_count=sum(c['selected'] for c in checks),
        maximum_absolute_error=max(numeric) if numeric and len(units)==1 else None,
        mean_absolute_error=sum(numeric)/len(numeric) if numeric and len(units)==1 else None,
        comparison_unit=next(iter(units)) if len(units)==1 else None)
    inspection = package.get('source_inspection', {})
    inspected_evidence = inspection.get('evidence_ids', [])
    if not inspected_evidence or not all(evidence.get(e,{}).get('transcription_status')=='verified' for e in inspected_evidence):
        inspection = {}
    variable_ok = bool(package['curves']) and all(c.get('variable_definition_verified') and
        VARIABLES.get(c['uwc_basis']) == c.get('raw_variable') and c['uwc_basis'] not in ('unknown', 'other') for c in package['curves'])
    for c in package['curves']:
        variable_verified = (c.get('variable_definition_verified') and VARIABLES.get(c['uwc_basis']) == c.get('raw_variable') and
                             c['uwc_basis'] not in ('unknown', 'other'))
        if not variable_verified and not any(r['object_id']==c['curve_id'] and r['issue_type']=='uwc_definition_uncertain' and
                                             r['status']=='open' for r in package['review_queue']):
            warn('curve', c['curve_id'], 'uwc_definition_uncertain', 'Original UWC variable definition has not been verified against source evidence.')
    paper = package['paper']
    basic_metadata_ok = (all(paper.get(k) for k in ('paper_title', 'authors', 'publication_year')) and package['samples'] and
        all(s['sample_name_reported'] or s['soil_type_reported'] for s in package['samples']) and package['conditions'] and
        all(c['condition_label_reported'] or any(p['condition_id']==c['condition_id'] for p in package['soil_properties']) for c in package['conditions']))
    incomplete_curves = [c for c in package['curves'] if c['method']=='unknown' or c['branch'] in ('unknown', 'other') or not c['evidence_ids']]
    metadata_ok = basic_metadata_ok and not incomplete_curves
    if not basic_metadata_ok and paper['extraction_status'] != 'not_relevant':
        warn('paper', paper['paper_id'], 'metadata_incomplete', 'Minimum paper/material/method/condition/source identification is incomplete.')
    for c in incomplete_curves:
        if not any(r['object_id']==c['curve_id'] and r['issue_type']=='curve_identity_uncertain' and r['status']=='open' for r in package['review_queue']):
            warn('curve', c['curve_id'], 'metadata_incomplete', 'Curve method, branch or source identification is incomplete.')
    unavailable_targets = coverage['unavailable_target_dataset_ids']
    if unavailable_targets:
        warn('paper', paper['paper_id'], 'extraction_incomplete',
            f'{len(unavailable_targets)} documented target dataset(s) have no available numerical series; excluded from the extraction denominator, retained in the design inventory.',
            'important', 'Review the documented source availability before importing a partial experimental design.')
    raw_curve_ids = {p['curve_id'] for p in package.get('raw_trace_points', [])}
    continuous = [c for c in package['curves'] if representation(c) == 'continuous_measured_trace' and
                  (c.get('trace_geometry') is not None or c['curve_id'] in raw_curve_ids)]
    trace_ok = not continuous or all(c.get('trace_processing', {}).get('status') == 'pass' for c in continuous)
    for curve in continuous:
        if curve.get('trace_processing', {}).get('status') != 'pass':
            description, action = trace_review_text(curve.get('trace_processing', {}))
            diagnostics=[d for d in package.get('trace_diagnostics',[]) if d['curve_id']==curve['curve_id'] and d['status']=='unresolved']
            if diagnostics:
                low=min(d['temperature_range'][0] for d in diagnostics);high=max(d['temperature_range'][1] for d in diagnostics)
                description += f" {len(diagnostics)} trace diagnostic segment(s), approximately {low:.3g} to {high:.3g} °C; internal IDs {diagnostics[0]['segment_id']}" + (f"–{diagnostics[-1]['segment_id']}." if len(diagnostics)>1 else ".")
            warn('curve', curve['curve_id'], 'trace_processing_review',
                 description, 'critical', action)
    physical = [d for d in package['derivations'] if d['derivation_type']=='physical_relation' and
                d['derived_variable'] in ('volumetric_unfrozen_water_content','volumetric_unfrozen_water_content_from_saturation')]
    properties = {p['property_id']: p for p in package['soil_properties']}
    curves = {c['curve_id']: c for c in package['curves']}
    targets = {p.get('uwc_derivation_id'): p for p in package['uwc_points'] if p.get('uwc_derivation_id')}
    for derivation in physical:
        if derivation.get('scope_verified'):
            continue
        target = targets.get(derivation['derivation_id'])
        curve = curves.get(target.get('curve_id')) if target else None
        source_properties = [properties[i['source_id']] for i in derivation['input_variables'] if i.get('source_id') in properties]
        dry = [p for p in source_properties if p['property']=='dry_density']
        compatible = bool(curve and all(p['sample_id']==curve['sample_id'] and
            p.get('condition_id') in (None,curve['condition_id']) for p in source_properties))
        compatible &= all(property_role(p)=='test_dry_density' and experiment_role_compatible(p,curve) for p in dry)
        if compatible:
            role = next((p.get('experiment_role') for p in source_properties if p.get('experiment_role') in
                         ('uwc_measurement','uwc_nmr','uwc_dsc')), 'uwc_measurement')
            derivation.update(sample_id=curve['sample_id'], condition_id=curve['condition_id'], specimen_role=role,
                applicability_evidence_ids=list(dict.fromkeys(e for p in source_properties for e in
                    p.get('applicability_evidence_ids',p['evidence_ids']))), scope_verified=True)
    conversion_curves = {c['curve_id'] for c in package['curves'] if c.get('conversion_property_ids')}
    unconverted = [p for p in package['uwc_points'] if p['curve_id'] in conversion_curves and p['uwc_original_basis'] in
                   ('gravimetric_dry_mass','unfrozen_water_saturation','liquid_water_saturation') and
                   p['uwc_preferred_value'] is None]
    derivation_ok = not unconverted and all(d.get('scope_verified') and d.get('sample_id') and d.get('condition_id') and
                        d.get('specimen_role') in ('uwc_measurement','uwc_nmr','uwc_dsc') and
                        d.get('applicability_evidence_ids') for d in physical)
    for derivation in physical:
        if not (derivation.get('scope_verified') and derivation.get('specimen_role') in ('uwc_measurement','uwc_nmr','uwc_dsc')):
            warn('derivation', derivation['derivation_id'], 'formula_uncertain',
                 'Physical UWC derivation lacks verified specimen/test applicability.', 'critical',
                 'Bind every input to the UWC specimen and cited experimental role, or retain the original variable only.')
    strict_vnext = tuple(map(int, package.get('schema_version', '1.0.0').split('.'))) >= (1, 6, 0)
    from numerical_qa import assess, gate_status
    numerical = assess(package, __import__('manifest').settings(package))
    package['numerical_quality'] = numerical
    numerical_gates = gate_status(numerical, strict_vnext)
    for metric in numerical['axis_metrics']:
        if strict_vnext and metric['status'] not in ('pass', 'not_applicable'):
            warn('curve', metric['curve_id'], 'axis_anchor_unverified',
                 f"Explicit axis anchors could not be independently verified (x={metric['x_anchor_count']}, y={metric['y_anchor_count']}).",
                 'critical', 'Record at least three independent labelled ticks per axis and re-run calibration.')
    for metric in numerical['curve_metrics']:
        if strict_vnext and metric['severe_reverse_jump_count']:
            warn('curve', metric['curve_id'], 'severe_reverse_jump',
                 f"{metric['severe_reverse_jump_count']} severe reverse jump(s); maximum decrease {metric['maximum_reverse_jump']:.4g} m³/m³.",
                 'critical', 'Revisit the raw observations and branch continuity; do not smooth or interpolate the error away.')
        if strict_vnext and metric['severe_above_initial_count']:
            warn('curve', metric['curve_id'], 'initial_water_content_exceeded',
                 f"{metric['severe_above_initial_count']} point(s) exceed condition initial volumetric water content by more than the strong tolerance; maximum {metric['maximum_above_initial']:.4g} m³/m³.",
                 'critical', 'Verify curve identity, axis mapping and initial-condition binding.')
        if strict_vnext and not metric['raw_observations_retained']:
            warn('curve', metric['curve_id'], 'raw_observation_missing',
                 'Digitized scientific points have no retained raw observation layer.', 'critical',
                 'Retain raw detected coordinates before normalization, filtering or simplification.')
    for pair in numerical['pair_metrics']:
        target = pair['freezing_curve_id']
        if strict_vnext and pair['possible_copied_or_shared_candidates']:
            warn('curve', target, 'possible_curve_duplication',
                 f"Freezing/thawing pair shares {pair['exact_duplicate_count']}/{pair['matched_temperature_count']} exactly equal matched values.",
                 'critical', 'Re-run pair-aware tracking from raw candidates and verify independent branch identity.')
        if strict_vnext and pair['possible_branch_switch']:
            warn('curve', target, 'branch_identity_switch',
                 f"Freezing/thawing relative order switches {pair['branch_order_switch_count']} times.",
                 'critical', 'Inspect branch seeds and continuity through the transition zone.')
    gates = dict(
        curve_completeness='pass' if paper['coverage_verified'] and coverage['inventory_available'] and coverage['coverage_percentage']==100 and
            coverage['expected_curve_count']==coverage['extracted_curve_count'] and not coverage['unexpected_conditions'] and
            not coverage['ambiguous_curves'] and not any(not d['identical'] for d in coverage['duplicate_conditions']) and not unavailable_targets else 'fail',
        point_source_completeness='fail' if pc['unexplained_gap_count'] else 'pass' if inspection.get('point_inventory_checked') and
            pc['assessed_curve_count'] and not pc['not_checked_curve_count'] and
            not any(m.get('availability_status')=='partially_available' for m in active) else 'not_checked',
        source_priority_validation='fail' if unresolved or package.get('source_failures') else 'pass' if inspection.get('anchor_search_completed') else 'not_checked',
        scientific_variable_correctness='pass' if variable_ok else 'fail',
        minimum_metadata_completeness='fail' if not metadata_ok else 'pass' if inspection.get('property_pass_completed') else 'not_checked',
        continuous_trace_processing='pass' if trace_ok else 'fail',
        derivation_provenance='pass' if derivation_ok else 'fail')
    gates['detection_completeness'] = gates['curve_completeness']
    if strict_vnext:
        gates.update(numerical_gates)
    critical = [r for r in package['review_queue'] if r['status']=='open' and review_severity(r)=='critical']
    if any(r['issue_type'] in ('physical_conflict', 'formula_uncertain', 'uwc_definition_uncertain', 'conflicting_values') for r in critical):
        gates['scientific_variable_correctness'] = 'fail'
    package['qa_gates'] = gates
    paper['database_ready'] = all(g=='pass' for g in gates.values()) and not critical and paper['extraction_status'] != 'not_relevant'
    if paper['extraction_status'] != 'not_relevant':
        if not package['uwc_points']: paper['extraction_status'] = 'metadata_only'
        elif critical:
            paper['extraction_status'] = 'partial' if all(r['issue_type']=='extraction_incomplete' for r in critical) else 'manual_review_required'
        else: paper['extraction_status'] = 'complete' if paper['database_ready'] else 'partial'
    targets = {r['object_id'] for r in critical}
    curve_targets = defaultdict(set)
    for point in package['uwc_points'] + package.get('reference_points', []):
        curve_targets[point['curve_id']].update([point['point_id'], *point['evidence_ids']])
    for curve in package['curves']:
        curve['needs_manual_review'] = bool(({paper['paper_id'], curve['curve_id'], curve['sample_id'], curve['condition_id'],
                                             *curve['evidence_ids']} | curve_targets[curve['curve_id']]) & targets)
    paper['review_status'] = review_status(package, critical)
    return package
