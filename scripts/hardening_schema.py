"""Backward-compatible scientific contracts; benchmark facts stay outside code."""


def extend(result, defs, obj, arr, ref, nullable, enum, S, N, B, ID, IDS, UNIT):
    number = nullable(N)
    count = {"type": "integer", "minimum": 0}
    text = nullable(S)
    defs['point_expectation'] = obj({
        'count': nullable(count), 'temperatures_celsius': arr(N),
        'information_type': {'enum': ['reported_targets', 'reported_observations', 'visible_markers', 'unspecified']},
        'evidence_ids': IDS, 'source_points_verified': B,
        'gap_resolution': {'enum': ['unresolved', 'not_reported_in_source', 'explicitly_not_measured']},
        'resolution_evidence_ids': IDS, 'explanation': text})
    defs['expected_dataset'] = obj({
        'expected_curve_id': ID, 'sample_id': ID, 'condition_id': ID,
        'experimental_factors': arr(enum('experimental_factor')),
        'condition_values': arr(obj({'property': enum('experimental_factor'), 'value': N, 'unit': UNIT, 'evidence_ids': IDS})),
        'branch': enum('branch'), 'curve_data_type': enum('curve_data_type'),
        'expected_source_ids': IDS, 'evidence_ids': IDS,
        'measurement_status': {'enum': ['expected', 'explicitly_not_measured']},
        'exclusion_evidence_ids': IDS, 'expected_point_information': ref('point_expectation')})
    defs['numerical_observation'] = obj({'temperature': N, 'temperature_unit': UNIT,
        'value': N, 'unit': UNIT, 'temperature_reported': text, 'value_reported': text})
    defs['numerical_dataset'] = obj({
        'dataset_id': ID, 'sample_id': ID, 'condition_id': ID, 'branch': enum('branch'),
        'cycle_number': nullable(count), 'method': enum('measurement_method'),
        'curve_data_type': enum('curve_data_type'), 'data_origin': enum('data_origin'),
        'raw_variable': enum('uwc_variable'), 'uwc_basis': enum('uwc_basis'),
        'variable_definition_verified': B,
        'source_kind': {'enum': ['structured_data', 'table', 'numerical_label', 'numerical_text']},
        'coverage_role': {'enum': ['full_series', 'anchors_only']},
        'evidence_ids': IDS, 'source_locator': S, 'observations': arr(ref('numerical_observation'))})
    defs['numerical_dataset']['properties']['table_binding'] = obj({
        'path': S, 'sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
        'sheet': text, 'row_start': {'type': 'integer', 'minimum': 1},
        'row_end': {'type': 'integer', 'minimum': 1},
        'temperature_column': {'type': 'integer', 'minimum': 1}, 'value_column': {'type': 'integer', 'minimum': 1},
        'temperature_unit': UNIT, 'unit': UNIT})
    defs['numerical_dataset']['properties'].update(variable_definition_reported=text, original_citation_reported=text)
    defs['expected_dataset']['properties']['exclusion_reason_reported'] = text
    for name in ('expected_dataset', 'numerical_dataset', 'curve', 'coverage_series'):
        defs[name]['properties']['series_variant_reported'] = text
    defs['evidence']['properties']['expected_series']['items']['properties']['series_variant_reported'] = text
    defs['recovery_attempt'] = obj({'expected_curve_id': ID, 'input_fingerprint': S,
        'status': {'enum': ['recovered', 'not_found', 'ambiguous', 'source_unavailable', 'targeted_review_required']},
        'source_ids': IDS, 'target_pages': arr({'type': 'integer', 'minimum': 1}),
        'search_terms': arr(S), 'source_hits': arr(S), 'detail': S})
    defs['anchor_check'] = obj({'check_id': ID, 'dataset_id': ID, 'observation_index': count,
        'curve_id': nullable(ID), 'point_id': nullable(ID), 'reference_point_id': nullable(ID),
        'absolute_error': number, 'normalized_error': number,
        'comparison_unit': nullable(UNIT), 'temperature_error_celsius': number,
        'status': {'enum': ['within_tolerance', 'warning', 'strong_warning', 'ambiguous', 'unmatched', 'incompatible_variable', 'conflicting_references']},
        'selected': B, 'detail': S})
    defs['anchor_resolution'] = obj({'check_id': ID, 'neighbor_points_checked': B,
        'resolution': {'enum': ['verified_source_choice', 'recalibrated']}, 'evidence_ids': IDS, 'explanation': S})
    defs['anchor_resolution']['properties']['comparison_fingerprint'] = S
    defs['point_coverage_row'] = obj({'expected_curve_id': ID, 'curve_id': nullable(ID),
        'expected_count': nullable(count), 'extracted_count': count, 'missing_count': count,
        'missing_temperatures_celsius': arr(N),
        'status': {'enum': ['complete', 'missing_point_or_not_reported', 'explained_source_gap', 'not_checked']},
        'explanation': text})
    defs['point_coverage'] = obj({'extracted_point_count': count, 'known_expected_point_count': count,
        'assessed_curve_count': count, 'unexplained_gap_count': count, 'explained_gap_count': count,
        'not_checked_curve_count': count, 'curves': arr(ref('point_coverage_row'))})
    result['properties'].update(
        expected_datasets=arr(ref('expected_dataset')), numerical_datasets=arr(ref('numerical_dataset')),
        reference_points=arr(ref('point')), observation_selections=arr(obj({'point_id': ID, 'reference_point_id': ID})),
        recovery_attempts=arr(ref('recovery_attempt')), anchor_checks=arr(ref('anchor_check')),
        source_failures=arr(obj({'dataset_id': ID, 'message': S})),
        anchor_resolutions=arr(ref('anchor_resolution')), point_coverage=ref('point_coverage'),
        anchor_summary=obj({'checked_count': count, 'within_tolerance_count': count, 'warning_count': count,
            'strong_warning_count': count, 'unresolved_count': count, 'selected_count': count,
            'maximum_absolute_error': number, 'mean_absolute_error': number, 'comparison_unit': nullable(UNIT)}),
        source_inspection=obj({'point_inventory_checked': B, 'anchor_search_completed': B,
            'property_pass_completed': B, 'evidence_ids': IDS}),
        qa_gates=obj({k: {'enum': ['pass', 'fail', 'not_checked']} for k in (
            'curve_completeness', 'point_source_completeness', 'source_priority_validation',
            'scientific_variable_correctness', 'minimum_metadata_completeness',
            'continuous_trace_processing', 'derivation_provenance', 'axis_anchor_validation',
            'detection_completeness', 'numerical_quality', 'physical_quality')}, required=[]),
        qa_settings=obj({k: {'type': 'number', 'minimum': 0} for k in (
            'temperature_match_tolerance_celsius', 'volumetric_warning_threshold',
            'volumetric_strong_threshold', 'normalized_warning_threshold',
            'trace_simplification_tolerance_normalized', 'trace_x_tolerance_normalized',
            'trace_denoise_tolerance_normalized', 'trace_transition_tolerance_factor',
            'trace_centerline_fidelity_p95_threshold_normalized',
            'trace_shared_coordinate_tolerance_normalized', 'trace_shared_near_tolerance_normalized',
            'trace_shared_path_fraction_threshold', 'trace_shared_near_fraction_threshold',
            'trace_shared_run_min_points', 'trace_local_jump_threshold_normalized',
            'trace_isolation_min_segment_points', 'trace_multimodal_y_separation_normalized',
            'trace_candidate_support_ratio',
            'trace_oversampled_absolute_count', 'trace_oversampled_fraction',
            'axis_anchor_residual_tolerance', 'reverse_jump_warning', 'reverse_jump_severe',
            'initial_theta_warning', 'initial_theta_severe', 'branch_exact_value_tolerance',
            'branch_near_value_tolerance', 'branch_duplicate_fraction_threshold',
            'branch_order_switch_threshold', 'trace_enforce_segment_fidelity')}, required=[]))
    metric = obj({'curve_id': ID, 'point_count': count, 'temperature_min': number, 'temperature_max': number,
        'uwc_min': number, 'uwc_max': number, 'reverse_jump_count': count, 'severe_reverse_jump_count': count,
        'maximum_reverse_jump': N, 'maximum_absolute_slope': number, 'initial_water_content': number,
        'above_initial_count': count, 'severe_above_initial_count': count, 'maximum_above_initial': N,
        'raw_observations_retained': B})
    pair = obj({'freezing_curve_id': ID, 'thawing_curve_id': ID, 'matched_temperature_count': count,
        'exact_duplicate_count': count, 'exact_duplicate_fraction': N, 'near_duplicate_count': count,
        'near_duplicate_fraction': N, 'branch_order_switch_count': count,
        'candidate_identity_status': {'enum':['checked','not_checked']},'same_candidate_reuse_count': count,
        'confirmed_shared_count': count,'suspicious_shared_assignment_count': count,
        'true_crossing_count': count,'identity_switch_count': count,'unclassified_order_crossing_count': count,
        'possible_copied_or_shared_candidates': B, 'possible_branch_switch': B})
    axis = obj({'curve_id': ID, 'status': {'enum': ['pass','fail','not_checked','not_applicable']},
        'x_anchor_count': count, 'y_anchor_count': count, 'x_max_residual': number, 'y_max_residual': number})
    result['properties']['numerical_quality'] = obj({'curve_metrics': arr(metric), 'pair_metrics': arr(pair), 'axis_metrics': arr(axis)})
    defs['paper']['properties']['database_ready'] = B
    defs['paper']['properties']['legacy_review_status'] = nullable({'enum': ['pending', 'approved', 'rejected']})
    defs['curve']['properties'].update(source_points_verified=B, plotted_uwc_axis_span=number, plotted_uwc_axis_unit=UNIT,
        trace_geometry=enum('trace_geometry'),
        trace_processing=obj({
            'algorithm': S, 'status': enum('trace_processing_status'),
            'raw_point_count': count, 'centerline_point_count': count, 'exported_point_count': count,
            'max_normalized_reconstruction_error': number, 'mean_normalized_reconstruction_error': number,
            'raw_to_centerline_median_normalized_error': number,
            'raw_to_centerline_p95_normalized_error': number,
            'raw_to_centerline_max_normalized_error': number,
            'raw_to_centerline_mean_normalized_error': number,
            'reduction_ratio': N, 'transition_point_count': count, 'segment_count': count,
            'monotonicity_checked_on': {'const': 'scientific_curve_points'},
            'monotonicity_violation_count': count, 'warnings': arr(S),
            'simplification_tolerance_normalized': N, 'x_tolerance_normalized': N,
            'denoise_tolerance_normalized': N, 'centerline_fidelity_p95_threshold_normalized': N}))
    defs['curve']['properties']['trace_processing']['properties'].update(
        curve_isolation_status={'enum': ['pass','partial','review_required','failed']},
        accepted_raw_point_count=count, excluded_contaminated_point_count=count,
        unresolved_segment_count=count, shared_exact_coordinate_count=count,
        shared_near_coordinate_fraction=N, shared_segment_fraction=N,
        trace_domain_coverage_fraction=N, accepted_domain_fraction=N,
        unresolved_domain_fraction=N, isolation_warning_codes=arr(S))
    defs['curve']['properties']['trace_processing']['properties']['fidelity_excluded_raw_point_count'] = count
    defs['property']['properties'].update(experiment_role=enum('experiment_role'), property_role=enum('property_role'),
        applicability_evidence_ids=IDS, reported_precision=nullable({'type': 'integer', 'minimum': 0}))
    defs['point']['properties'].update(trace_order={'type': 'integer', 'minimum': 1}, raw_pixel_x=number, raw_pixel_y=number,
        trace_segment=nullable({'type': 'integer', 'minimum': 1}), observation_quality=enum('observation_quality'))
    defs['point']['properties'].update(candidate_id=nullable(ID), component_id=nullable(ID), path_position=number,
        candidate_assignment=nullable({'enum':['freezing','thawing','confirmed_shared','unresolved','rejected']}),
        confirmed_shared=B, near_vertical=B)
    defs['derivation']['properties'].update(sample_id=nullable(ID), condition_id=nullable(ID),
        specimen_role=nullable(enum('experiment_role')), applicability_evidence_ids=IDS, scope_verified=B)
    result['properties']['raw_trace_points'] = arr(ref('point'))
    defs['trace_diagnostic'] = obj({'segment_id': ID,'curve_id': ID,'condition_id': ID,'branch': enum('branch'),
        'status': {'enum':['selected','rejected','unresolved']},
        'failure_reason': {'enum':['shared_path_true_overlap','shared_path_candidate_collision','insufficient_local_geometry',
            'near_vertical_ambiguity','multimodal_candidate_set','abrupt_path_discontinuity','marker_occlusion',
            'branch_identity_ambiguous','centerline_fidelity_failure','raster_vector_resolution_limit','unknown']},
        'resolution_class': {'enum':['algorithmically_resolvable','source_intrinsic_ambiguity','source_intrinsic_or_identity_unresolved','unknown']},
        'start_candidate': nullable(ID),'end_candidate': nullable(ID),'candidate_ids': IDS,
        'pixel_coordinates': nullable(arr(arr(number))),'mapped_coordinates': arr(arr(N)),
        'local_tangent': nullable(arr(N)),'local_curvature': number,'competing_paths': IDS,
        'competing_branch_ids': IDS,'component_ids': IDS,'shared_candidate_ids': IDS,
        'local_confidence': enum('confidence'),'diagnostic_note': text,
        'temperature_range': arr(N),'uwc_range': arr(N)})
    result['properties']['trace_diagnostics'] = arr(ref('trace_diagnostic'))
    defs['branch_tracking_spec'] = obj({'condition_id': ID,'freezing_curve_id': ID,'thawing_curve_id': ID,
        'freezing_start_candidate': ID,'freezing_end_candidate': ID,'thawing_start_candidate': ID,
        'thawing_end_candidate': ID,'freezing_component_id': nullable(ID),'thawing_component_id': nullable(ID),
        'max_edge_distance_normalized': {'type':'number','exclusiveMinimum':0},'evidence_ids': IDS})
    result['properties']['branch_tracking_specs'] = arr(ref('branch_tracking_spec'))
    defs['branch_tracking_result'] = obj({'condition_id': ID,'status': {'enum':['pass','unresolved']},
        'paths': obj({'freezing': IDS,'thawing': IDS}),'candidate_assignments': {'type':'object'},
        'confirmed_shared_ids': IDS,'unresolved_candidate_ids': IDS,'true_crossing_count': count,
        'identity_switch_count': count,'bridged': B},required=['condition_id','status','paths','candidate_assignments',
            'confirmed_shared_ids','unresolved_candidate_ids','true_crossing_count','identity_switch_count','bridged'])
    result['properties']['branch_tracking_results'] = arr(ref('branch_tracking_result'))
    defs['coverage']['properties'].update(curve_coverage_percentage=number,
        missing_curves=IDS, unexpected_curves=IDS, ambiguous_curves=IDS)
    point_set = obj({'count': nullable(count), 'temperatures_celsius': arr(N), 'evidence_ids': IDS})
    observable = obj({**point_set['properties'], 'completeness': {'enum': ['complete', 'partial', 'unknown']}})
    info = defs['point_expectation']
    legacy_required = info.pop('required')
    info['anyOf'] = [{'required': legacy_required}, {'required': ['protocol_expected', 'reported_expected', 'source_observable']}]
    info['properties'].update(protocol_expected=point_set, reported_expected=point_set, source_observable=observable,
        protocol_applies_to_output=B, protocol_output_evidence_ids=IDS, protocol_output_statement_reported=text)
    semantic_fields = {'data_semantics': enum('data_semantics'), 'representation': enum('representation')}
    for name in ('curve', 'expected_dataset', 'numerical_dataset', 'coverage_series'):
        defs[name]['properties'].update(semantic_fields)
    defs['evidence']['properties']['expected_series']['items']['properties'].update(semantic_fields)
    defs['expected_dataset']['properties'].update(target_quantity_status=enum('target_quantity_status'),
        availability_status=enum('availability_status'), availability_evidence_ids=IDS, availability_explanation=text)
    defs['point_coverage_row']['properties'].update(protocol_expected=point_set, reported_expected=point_set,
        source_observable=observable, protocol_difference_count=count, protocol_missing_temperatures_celsius=arr(N),
        reported_missing_count=count, observable_missing_count=count)
    defs['point_coverage']['properties'].update(protocol_expected_point_count=count, reported_expected_point_count=count,
        source_observable_point_count=count, protocol_difference_count=count, observable_missing_count=count)
    defs['coverage']['properties'].update(design_dataset_count=count, documented_unavailable_dataset_ids=IDS,
        proxy_dataset_ids=IDS, unavailable_target_dataset_ids=IDS)
    defs['case_variable']['properties'].update(
        value_reported_text=arr(S), value_reported_numeric=arr(N), reported_unit=nullable(UNIT),
        reported_basis=nullable(enum('uwc_basis')),
        reported_precisions=arr(nullable({'type': 'integer', 'minimum': 0})),
        normalized_values=arr(N), normalized_unit=nullable(UNIT),
        normalized_basis=nullable(enum('uwc_basis')),
        normalization_type=nullable({'enum': ['none','unit_scaling','physical_conversion']}))
