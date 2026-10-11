"""Scientific meaning, source availability and point expectations; no paper rules."""

LEGACY_SEMANTICS = {'measured_point': 'measured', 'fitted_curve': 'fitted',
                    'predicted_curve': 'predicted', 'derived_curve': 'derived'}
UNAVAILABLE = {'reported_but_not_numerically_available', 'not_found_in_source', 'not_applicable'}


def data_semantics(item):
    return item.get('data_semantics') or LEGACY_SEMANTICS.get(item.get('curve_data_type'), 'unknown')


def representation(item):
    if item.get('representation'):
        return item['representation']
    method = item.get('extraction_method')
    if method in ('table_direct', 'supplementary_direct') or item.get('source_kind') in ('table', 'structured_data'):
        return 'tabulated_points'
    if method == 'raster_marker':
        return 'discrete_markers'
    if item.get('source_kind') == 'numerical_label':
        return 'explicit_numeric_labels'
    if item.get('curve_data_type') == 'measured_point':
        return 'discrete_markers'
    if data_semantics(item) in ('fitted', 'predicted'):
        return 'continuous_model_curve'
    return 'unknown'


def numerical_expected(item):
    return (item.get('measurement_status', 'expected') == 'expected'
            and item.get('target_quantity_status', 'unknown') != 'proxy_signal_only'
            and item.get('availability_status', 'available') not in UNAVAILABLE)


def point_set(count=None, temperatures=(), evidence_ids=()):
    return dict(count=count, temperatures_celsius=list(temperatures), evidence_ids=list(evidence_ids))


def point_expectations(info, curve=None):
    """Read both contracts without overwriting legacy/source evidence."""
    explicit = any(k in info for k in ('protocol_expected', 'reported_expected', 'source_observable'))
    result = {k: dict(info.get(k, point_set())) for k in ('protocol_expected', 'reported_expected', 'source_observable')}
    if not explicit:
        target = {'reported_targets': 'protocol_expected', 'reported_observations': 'reported_expected',
                  'visible_markers': 'source_observable'}.get(info.get('information_type'))
        if target:
            result[target] = point_set(info.get('count'), info.get('temperatures_celsius', []), info.get('evidence_ids', []))
    observable = result['source_observable']
    if 'completeness' not in observable:
        observable['completeness'] = ('complete' if info.get('source_points_verified') or
            curve and curve.get('source_points_verified') else 'unknown') if not explicit else 'unknown'
    if not explicit and not observable['evidence_ids']:
        observable['evidence_ids'] = list(info.get('evidence_ids') or (curve or {}).get('evidence_ids', []))
    return result


def semantic_errors(package):
    errors = []
    evidence = {e['evidence_id']: e for e in package['evidence']}
    def verified(ids):
        return bool(ids) and all(evidence.get(e, {}).get('transcription_status') == 'verified' for e in ids)
    rows = package['curves'] + package.get('expected_datasets', []) + package.get('numerical_datasets', [])
    rows += [s for e in package['evidence'] for s in e.get('expected_series', [])]
    for row in rows:
        sem, rep = data_semantics(row), representation(row)
        legacy = LEGACY_SEMANTICS.get(row.get('curve_data_type'))
        if legacy and row.get('data_semantics') and legacy != sem:
            errors.append('Scientific data semantics conflict with the legacy curve type')
        if rep == 'continuous_measured_trace' and sem != 'measured':
            errors.append('A continuous measured trace requires measured data semantics')
        if rep == 'continuous_model_curve' and sem not in ('fitted', 'predicted', 'derived'):
            errors.append('A continuous model curve requires fitted, predicted or derived semantics')
    for row in package.get('expected_datasets', []):
        special = (row.get('target_quantity_status') == 'proxy_signal_only' or row.get('availability_status') in UNAVAILABLE)
        if special and (not verified(row.get('availability_evidence_ids')) or not row.get('availability_explanation')):
            errors.append('Target quantity/availability exclusion requires verified evidence and an explanation')
        info = row['expected_point_information']
        for name in ('protocol_expected', 'reported_expected', 'source_observable'):
            item = info.get(name, {})
            if (item.get('count') is not None or item.get('temperatures_celsius') or item.get('completeness') == 'complete') and not verified(item.get('evidence_ids')):
                errors.append(name + ' requires verified source evidence')
            if item.get('count') is not None and len(item.get('temperatures_celsius', [])) > item['count']:
                errors.append(name + ' temperature count exceeds the declared point count')
        if info.get('protocol_applies_to_output'):
            ids = info.get('protocol_output_evidence_ids', [])
            quote = info.get('protocol_output_statement_reported')
            if not verified(ids) or not quote or not any(quote in (evidence.get(e, {}).get('quoted_evidence') or '') for e in ids):
                errors.append('A protocol hard denominator requires an explicit verified output-series statement')
    return errors


def review_status(package, critical):
    paper = package['paper']
    if paper['database_ready']:
        return 'database_ready'
    populated = {p['curve_id'] for p in package['uwc_points']}
    useful = any(c['branch'] not in ('unknown', 'other') and c['uwc_basis'] not in ('unknown', 'other')
        and data_semantics(c) != 'unknown' and c['evidence_ids']
        and c['curve_id'] in populated for c in package['curves'])
    if not useful or paper['extraction_status'] == 'not_relevant':
        return 'insufficient'
    pc = package['point_coverage']
    unavailable_targets = any(m.get('target_quantity_status') != 'proxy_signal_only' and
        m.get('availability_status') in UNAVAILABLE - {'not_applicable'} for m in package.get('expected_datasets', []))
    partial_sources = (any(r['source_observable']['completeness'] == 'partial' for r in pc['curves']) or
        any(m.get('availability_status')=='partially_available' for m in package.get('expected_datasets', []) if numerical_expected(m)))
    if (package['coverage']['missing_conditions'] or pc['unexplained_gap_count'] or unavailable_targets or
            partial_sources or not paper['coverage_verified']):
        return 'partial'
    return 'usable_with_review'
