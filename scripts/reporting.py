"""A short provenance and action report; detailed records stay in JSON."""
from pathlib import PurePosixPath
from coverage import curve_coverage
from science import convert_value


def location(evidence):
    parts=[]
    for key,prefix in (("figure_number","Fig."),("table_number","Table"),("equation_number","Eq.")):
        if evidence.get(key):
            parts.append(f"{prefix} {evidence[key]}" + (evidence.get("figure_panel") or "" if key=="figure_number" else ""))
    if evidence.get("page"):parts.append(f"p. {evidence['page']}")
    return ", ".join(parts) or evidence.get("section_reported") or PurePosixPath(evidence["source_file"].replace("\\","/")).name


def markdown_report(package):
    from quality import review_severity
    paper=package["paper"]
    coverage=package.get("coverage") or curve_coverage(package)
    samples={s["sample_id"]:s["sample_name_reported"] or s["soil_type_reported"] or s["soil_type_normalized"] for s in package["samples"]}
    conditions={c["condition_id"]:c for c in package["conditions"]}
    evidence={e["evidence_id"]:e for e in package["evidence"]}
    unique=set(coverage["unique_curve_ids"])
    points=[p for p in package["uwc_points"] if p["curve_id"] in unique]
    percentage=f"{coverage['coverage_percentage']:.2f}%" if coverage["coverage_percentage"] is not None else "not inventoried"
    methods=list(dict.fromkeys("NMR" if c["method"]=="nuclear_magnetic_resonance" else c["method_reported"] or c["method"] for c in package["curves"]))
    lines=["# UWC Extraction Report","","## Paper","",paper["paper_title"] or "Title not identified",
           "; ".join(paper["authors"]),f"Year: {paper['publication_year'] or 'unknown'} · DOI: {paper['doi'] or 'not reported'}",
           "","## Extraction Summary","",f"- Materials: {'; '.join(samples.values())}",f"- Method: {'; '.join(methods)}",
           "- Branch: "+"; ".join(dict.fromkeys(c["branch"] for c in package["curves"])),
           f"- Unique curves: {coverage['extracted_curve_count']} · Points: {len(points)}",
           f"- Coverage: {coverage['matched_curve_count']}/{coverage['expected_curve_count']} expected curves ({percentage})",
           f"- Extraction status: {paper['extraction_status']}",
           f"- Database ready: {'yes' if paper.get('database_ready') else 'no'}",
           f"- Human review usability: {paper.get('review_status', 'insufficient')}"]
    if coverage.get('documented_unavailable_dataset_ids'):
        lines.append(f"- Design inventory: {coverage['design_dataset_count']} datasets; {len(coverage['proxy_dataset_ids'])} proxy-only and "
                     f"{len(coverage['unavailable_target_dataset_ids'])} numerically unavailable target datasets documented outside the extraction denominator.")
        for m in package.get('expected_datasets', []):
            if m['expected_curve_id'] in coverage['documented_unavailable_dataset_ids'] and m.get('availability_explanation'):
                note = m['availability_explanation']
                text = '- Source availability: ' + note
                if text not in lines: lines.append(text)
    pc=package.get('point_coverage', {})
    traces=[c for c in package['curves'] if c.get('trace_processing')]
    if pc:
        if traces:
            if pc['known_expected_point_count']==0 and pc['unexplained_gap_count']==0:
                lines.append("- Reported-point completeness: no hard expected discrete observations are missing.")
            else:
                lines.append(f"- Reported-point completeness: {pc['known_expected_point_count']} hard expected observations; "
                             f"{pc['unexplained_gap_count']} unextracted reported/source-identifiable observations.")
        else:
            lines.append(f"- Point/source completeness: {pc['known_expected_point_count']} hard expected observations; {pc['unexplained_gap_count']} unextracted reported/source-identifiable observations; "
                         f"{pc['not_checked_curve_count']} series not fully assessed.")
        if pc.get('protocol_expected_point_count'):
            lines.append(f"- Protocol provenance: {pc['protocol_expected_point_count']} planned observations; {pc.get('protocol_difference_count',0)} unmatched protocol targets. "
                         "Protocol differences alone are informational, unless explicitly required in this output series.")
    if traces:
        raw=sum(c['trace_processing']['raw_point_count'] for c in traces)
        accepted=sum(c['trace_processing'].get('accepted_raw_point_count',c['trace_processing']['raw_point_count']) for c in traces)
        excluded=sum(c['trace_processing'].get('excluded_contaminated_point_count',0) for c in traces)
        unresolved=sum(c['trace_processing'].get('unresolved_segment_count',0) for c in traces)
        center=sum(c['trace_processing']['centerline_point_count'] for c in traces)
        exported=sum(c['trace_processing']['exported_point_count'] for c in traces)
        maximum=max((c['trace_processing']['max_normalized_reconstruction_error'] or 0) for c in traces)
        fidelity=max((c['trace_processing'].get('raw_to_centerline_p95_normalized_error') or 0) for c in traces)
        lines.append(f"- Continuous-trace geometry: {raw} raw candidate coordinates retained internally; {accepted} accepted and {excluded} excluded/ambiguous; "
                     f"{unresolved} unresolved segment(s); {center} centerline points; "
                     f"{exported} scientific curve points exported; worst raw-to-centerline P95 normalized error {fidelity:.4g}; "
                     f"maximum centerline-to-scientific reconstruction error {maximum:.4g}.")
    diagnostics=package.get('trace_diagnostics',[])
    if diagnostics:
        lines.extend(["","## Trace Diagnosis Summary",""])
        for curve in package['curves']:
            items=[d for d in diagnostics if d['curve_id']==curve['curve_id'] and d['status']=='unresolved']
            if not items: continue
            counts={reason:sum(d['failure_reason']==reason for d in items) for reason in dict.fromkeys(d['failure_reason'] for d in items)}
            low=min(d['temperature_range'][0] for d in items);high=max(d['temperature_range'][1] for d in items)
            identity=curve.get('legend_label') or curve['curve_id']
            lines.append(f"- **{identity}; {curve['branch']}** — {len(items)} affected segment(s), approximately {low:.3g}–{high:.3g} °C; "
                         +", ".join(f"{k}: {v}" for k,v in counts.items())+f". Review `.internal` trace IDs {items[0]['segment_id']}"+
                         (f"–{items[-1]['segment_id']}." if len(items)>1 else "."))
    nq=package.get('numerical_quality', {})
    if nq:
        cm=nq.get('curve_metrics', [])
        pm=nq.get('pair_metrics', [])
        am=nq.get('axis_metrics', [])
        lines.append(f"- Numerical QA: {sum(m['reverse_jump_count'] for m in cm)} reverse jumps "
                     f"({sum(m['severe_reverse_jump_count'] for m in cm)} severe); "
                     f"{sum(m['above_initial_count'] for m in cm)} initial-water upper-bound warnings; "
                     f"{sum(p['exact_duplicate_count'] for p in pm)} exact paired duplicates; "
                     f"{sum(p.get('same_candidate_reuse_count',0) for p in pm)} same-candidate reuses "
                     f"({sum(p.get('suspicious_shared_assignment_count',0) for p in pm)} suspicious); "
                     f"{sum(p.get('true_crossing_count',0) for p in pm)} confirmed/geometry-supported crossings, "
                     f"{sum(p.get('identity_switch_count',0) for p in pm)} identity switches and "
                     f"{sum(p.get('unclassified_order_crossing_count',0) for p in pm)} unclassified order crossings.")
        lines.append(f"- Axis anchors: {sum(m['x_anchor_count']+m['y_anchor_count'] for m in am)} explicit tick anchors; "
                     f"{sum(m['status']=='pass' for m in am)}/{len(am)} curve mappings independently re-fitted.")
    pending=[k.replace('_',' ') for k,v in package.get('qa_gates',{}).items() if v!='pass']
    if pending:lines.append('- Gates requiring attention: '+ '; '.join(pending)+'.')
    lines.extend(["","## UWC/SFCC Sources",""])
    seen=set()
    for e in evidence.values():
        if not (e.get("source_role")=="primary_uwc" or e.get("figure_number") or e.get("table_number")):
            continue
        key=(e["source_file"],e.get("figure_number"),e.get("figure_panel"),e.get("table_number"),e.get("page"))
        if key in seen:continue
        seen.add(key)
        role={"primary_uwc":"primary measured UWC source", "validation":"numerical/figure validation source",
              "supporting":"material properties / experimental design","sfcc_model":"SFCC model"}.get(e.get("source_role"),"source role unresolved")
        loc=location(e)
        if e["source_file"].startswith("https://"):
            loc=f"[{loc}]({e['source_file']})"
        lines.append(f"- **{loc}** — Role: {role}.")
        caption=e.get("figure_caption") or e.get("table_caption")
        if caption:lines.append("  "+caption.replace("\n","\n  "))
    lines.extend(["","## Variable Handling",""])
    bases=set(c["uwc_basis"] for c in package["curves"])
    relations=set(d["derived_variable"] for d in package["derivations"])
    if "unfrozen_water_saturation" in bases:
        lines.append("- Original variable: unfrozen water saturation Su (pore-volume fraction), distinct from volumetric UWC θu.")
    if "volumetric_unfrozen_water_content_from_saturation" in relations:
        used={i["source_id"] for d in package["derivations"] if d["derived_variable"]=="volumetric_unfrozen_water_content_from_saturation"
              for i in d["input_variables"] if i["variable"]=="porosity"}
        porosity=[f"{samples[p['sample_id']]} φ={p['value']:.3f} ({'; '.join(location(evidence[e]) for e in p['evidence_ids'])})"
                  for p in package["soil_properties"] if p["property_id"] in used]
        lines.append("- Derived θu = φ × Su (m³/m³), using "+"; ".join(porosity)+". Original Su and all input bindings remain in JSON.")
    if "volumetric_unfrozen_water_content" in relations:
        lines.append("- Derived θu = wu × ρd / ρw, using matched specimen dry density; maximum dry density is not substituted.")
    if bases=={"volumetric"}:
        lines.append("- Reported volumetric UWC is retained; any vol.% values are scaled to m³/m³ without a physical derivation.")
    for note in dict.fromkeys(a["description"] for d in package["derivations"] for a in d["assumptions"]):
        lines.append("- "+note)
    if any(p["temperature_original_unit"]=="kelvin" for p in points):
        lines.append("- Temperature: T(°C) = T(K) − 273.15. Original Kelvin observations remain stored.")
    if any(p["uwc_preferred_value"] is None for p in points):
        lines.append("- Where conversion is unsupported, each Excel block retains the original physical variable and an explicit unit; no θu is assumed.")
    if any(t["translation_status"]=="uncertain" for t in package["display_translations"]):
        lines.append("- An optional display translation is uncertain; original evidence is retained and authoritative.")
    small_overshoot=0
    for p in points:
        if p["uwc_original_basis"] in ("unfrozen_water_saturation","liquid_water_saturation"):
            try:value=convert_value(p["uwc_original_value"],p["uwc_original_unit"],"fraction")
            except ValueError:continue
            small_overshoot+=int(-.01<=value<0 or 1<value<=1.01)
    lines.extend(["","## Cross-source Validation",""])
    anchors=package.get('anchor_summary', {})
    if anchors and anchors['checked_count']:
        lines.append(f"- {anchors['checked_count']} numerical anchors checked; {anchors['selected_count']} selected for output; "
                     f"{anchors['warning_count']} warnings and {anchors['strong_warning_count']} strong warnings; "
                     f"{anchors['unresolved_count']} unresolved blocking comparisons.")
        if anchors['maximum_absolute_error'] is not None:
            unit='m³/m³' if anchors['comparison_unit']=='cubic_meter_per_cubic_meter' else anchors['comparison_unit']
            lines.append(f"- Original graph versus explicit source: maximum absolute difference {anchors['maximum_absolute_error']:.4g}; "
                         f"mean {anchors['mean_absolute_error']:.4g} {unit}.")
        lines.append('- Higher-priority exact observations control corresponding Excel values. All original graphical observations remain in the internal dataset; no averaging or interpolation is applied.')
    elif package.get('source_inspection',{}).get('anchor_search_completed'):
        lines.append('- Relevant numerical sources inspected. No separate comparable graphical/numerical anchors were available; direct primary numbers, where present, were retained.')
    else:lines.append('- Numerical anchor search has not been completed; source-priority validation is not checked.')
    if package.get('anchor_resolutions'):
        for note in dict.fromkeys(r['explanation'] for r in package['anchor_resolutions']):lines.append('- '+note)
    lines.extend(["","## Notes",""])
    if small_overshoot:lines.append(f"- {small_overshoot} saturation values have a small graphical overshoot (≤0.01). Retained without clipping.")
    repeated=coverage["source_occurrence_count"]-coverage["extracted_curve_count"]
    if repeated:lines.append(f"- {repeated} repeated source occurrences are retained internally; visible datasets are not repeated. Source conflicts are listed below.")
    notes=[r for r in package["review_queue"] if r["status"]=="resolved" and r["generated_by"]!="validator"]
    lines.extend("- "+r["description"] for r in notes)
    for prop in package['soil_properties']:
        if (prop['definition_status']!='explicit' or prop['property'] in ('sample_height','sample_diameter','total_soluble_salt_content') or
                prop.get('property_role') in ('test_dry_density','maximum_dry_density','natural_bulk_density','wet_bulk_density',
                                              'dry_density_reported_unspecified_context','average_density_basis_unspecified')):
            label=prop['property_reported'] or prop['property'].replace('_',' ')
            value=prop.get('value_reported') or str(prop['original_value'])
            unit=prop.get('unit_reported') or prop['original_unit']
            scope='; basis unspecified; excluded from conversion' if prop['definition_status']!='explicit' else ''
            role=('; role '+prop['property_role'].replace('_',' ') if prop.get('property_role') else '')
            if prop.get('experiment_role') in ('uwc_measurement','uwc_nmr','uwc_dsc'):
                role += '; UWC measurement specimen'
            lines.append(f"- {samples[prop['sample_id']]}: {label} = {value} {unit}{scope}{role}.")
    for curve in traces:
        trace=curve['trace_processing']
        if trace['status']!='pass' or trace['warnings']:
            lines.append(f"- {curve['legend_label'] or curve['curve_id']}: continuous-trace processing {trace['status']}; "
                         + (", ".join(trace['warnings']) if trace['warnings'] else "review reconstruction QA" ) +
                         f" Accepted {trace.get('accepted_raw_point_count',trace['raw_point_count'])}/{trace['raw_point_count']} raw candidates; "
                         f"unresolved segments {trace.get('unresolved_segment_count',0)}.")
    for note in dict.fromkeys(r['explanation'] for r in pc.get('curves',[]) if r['explanation']):lines.append('- '+note)
    if not small_overshoot and not repeated and not notes:lines.append("- No additional numerical transformations beyond the handling described above.")
    lines.extend(["","## Manual Review",""])
    labels={paper["paper_id"]:"Paper",**samples,**{eid:location(e) for eid,e in evidence.items()}}
    for cid,c in conditions.items():labels[cid]=samples[c["sample_id"]]+"; "+(c["condition_label_reported"] or "Condition")
    for curve in package["curves"]:labels[curve["curve_id"]]=labels[curve["condition_id"]]+"; "+curve["branch"]
    for prop in package["soil_properties"]:labels[prop["property_id"]]=prop["property_reported"] or prop["property"].replace("_"," ")
    for p in points:labels[p["point_id"]]=labels[p["curve_id"]]
    reviews=[r for r in package["review_queue"] if r["status"]=="open" and review_severity(r)!="note"]
    for severity in ("critical","important"):
        group=[r for r in reviews if review_severity(r)==severity]
        if group:
            lines.append(severity.capitalize()+":")
            lines.extend(f"- {labels.get(r['object_id'],r['object_type'])}: {r['description']} {r['recommended_action']}" for r in group)
    if not reviews:lines.append("No actionable review items recorded.")
    return "\n".join(lines)+"\n"
