"""Small display tables and factor groups driven by evidence-backed cases."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from coverage import STATE_PROPERTIES
from science import convert_value

BASIC = [
    ("liquid_limit", "LL (%)", "percent"), ("plastic_limit", "PL (%)", "percent"),
    ("plasticity_index", "PI (%)", "percent"), ("optimum_water_content", "Optimum water content (%)", "percent"),
    ("maximum_dry_density", "Maximum dry density (g/cm³)", "gram_per_cubic_centimeter"),
    ("specific_gravity", "Specific gravity (-)", "dimensionless"), ("porosity", "Porosity (-)", "fraction"),
    ("specific_surface_area", "SSA (m²/g)", "square_meter_per_gram"),
    ("sand_fraction", "Sand (%)", "percent"), ("silt_fraction", "Silt (%)", "percent"),
    ("clay_fraction", "Clay (%)", "percent"), ("void_ratio", "Void ratio (-)", "dimensionless"),
]
STATE = {
    "cycle_number": ("Freeze–thaw cycle", "dimensionless", "Cycle"),
    "dry_density": ("Test dry density (g/cm³)", "gram_per_cubic_centimeter", "Test dry density"),
    "initial_water_saturation": ("Initial water saturation (-)", "fraction", "Sw0"),
    "degree_of_saturation": ("Initial water saturation (-)", "fraction", "Sw0"),
    "initial_ionic_concentration": ("Initial ionic concentration (mol/L)", "mole_per_liter", "C0"),
    "solution_concentration": ("Initial ionic concentration (mol/L)", "mole_per_liter", "C0"),
    "initial_volumetric_water_content": ("Initial θ (m³/m³)", "cubic_meter_per_cubic_meter", "θini"),
    "initial_gravimetric_water_content": ("Initial w (kg/kg)", "kilogram_per_kilogram", "wini"),
    "matric_suction": ("Initial matric suction (kPa)", "kilopascal", "Initial matric suction"),
    "pressure": ("Pressure (kPa)", "kilopascal", "Pressure"),
}
REPORTED_FACTOR_LABEL = {
    "initial_volumetric_water_content": "Wv",
    "initial_gravimetric_water_content": "wini",
}

def soil_name(sample):
    return sample["sample_name_reported"] or sample["soil_type_reported"] or sample["soil_type_normalized"]

def scaled(value, source, target, key):
    basis = "volumetric" if "volumetric" in key else "gravimetric_dry_mass" if "gravimetric" in key else None
    return convert_value(value, source, target, basis)

def property_cell(rows, key, unit):
    values=[]
    for row in rows:
        if row["definition_status"] != "explicit":return "See report"
        try: value=scaled(row["value"],row["unit"],unit,key)
        except ValueError:return "See report"
        if not any(abs(value-v)<1e-12 for v in values):values.append(value)
    return values[0] if len(values)==1 else "Conflict; see report" if values else None

def basic_soil_table(package):
    props=defaultdict(list)
    for p in package["soil_properties"]:
        if p["condition_id"] is None and p.get("property_scope") != "test_state":
            props[(p["sample_id"],p["property"])].append(p)
    columns=[c for c in BASIC if any(key==c[0] for _,key in props)][:11]
    return (["Soil"]+[c[1] for c in columns],
            [[soil_name(s)]+[property_cell(props[(s["sample_id"],c[0])],c[0],c[2]) for c in columns] for s in package["samples"]])

def case_label(case):
    return case["factor_label_reported"] or case["varying_property"].replace("_"," ").capitalize()

def format_value(value, key, precision=None, reported=None):
    if reported not in (None, ""):
        return str(reported)
    if precision is not None:
        return f"{value:.{precision}f}"
    return f"{value:.3f}" if key not in ("pressure","matric_suction","cycle_number") else f"{value:g}"

def decimal_precision(value):
    try:
        # Keep explicit trailing zeroes in source strings while removing
        # binary floating-point artefacts from normalized numeric values.
        text = str(value).strip() if isinstance(value, str) else format(float(value), ".12f").rstrip("0").rstrip(".")
        return max(0,-Decimal(text).as_tuple().exponent)
    except (InvalidOperation,ValueError):
        return None

def normalized_precision(prop):
    if prop.get("original_unit")==prop.get("unit") and prop.get("value_reported") not in (None,""):
        try:
            if abs(float(prop["value_reported"])-float(prop["value"]))<1e-12:
                return prop.get("reported_precision") if prop.get("reported_precision") is not None else decimal_precision(prop["value_reported"])
        except ValueError:
            pass
    return decimal_precision(prop["value"])

def design_cases(package):
    if package.get("experimental_cases"):
        return package["experimental_cases"]
    # Legacy fallback uses actual scoped properties. No default θini or salinity assumption.
    cases=[]
    for sample in package["samples"]:
        conditions=[c for c in package["conditions"] if c["sample_id"]==sample["sample_id"]]
        values=defaultdict(list)
        units={}
        precisions=defaultdict(list)
        cycles=list(dict.fromkeys(c["cycle_number"] for c in conditions if c["cycle_number"] is not None))
        if len(cycles)>1:
            values["cycle_number"],units["cycle_number"]=cycles,"dimensionless"
        for prop in package["soil_properties"]:
            if prop["sample_id"]==sample["sample_id"] and prop["property"] in STATE_PROPERTIES:
                if prop["value"] not in values[prop["property"]]:
                    values[prop["property"]].append(prop["value"])
                    target=STATE.get(prop["property"],(None,prop["unit"],None))[1]
                    precisions[prop["property"]].append(normalized_precision(prop) if prop["unit"]==target else None)
                units[prop["property"]]=prop["unit"]
        varied=[k for k,v in values.items() if len(v)>1]
        factor=varied[0] if len(varied)==1 else "none"
        cases.append({"case_id":sample["sample_id"],"sample_id":sample["sample_id"],"case_label_reported":"",
                      "varying_property":factor,"factor_label_reported":None,
                      "variables":[{"property":k,"values":v,"unit":units[k],"reported_precisions":precisions[k]} for k,v in values.items()],
                      "condition_ids":[c["condition_id"] for c in conditions],"temperature_range_celsius":None})
    return cases

def test_condition_table(package):
    cases=design_cases(package)
    samples={s["sample_id"]:soil_name(s) for s in package["samples"]}
    keys=list(dict.fromkeys(v["property"] for c in cases for v in c["variables"]))
    has_range=any(c.get("temperature_range_celsius") for c in cases)
    headers=["Case","Soil"]+[STATE.get(k,(k.replace('_',' ').capitalize(),None,None))[0] for k in keys]
    if has_range:headers.append("Temperature range (°C)")
    rows=[]
    for c in cases:
        variables={v["property"]:v for v in c["variables"]}
        row=[c["case_label_reported"],samples[c["sample_id"]]]
        for key in keys:
            v=variables.get(key)
            if v is None:row.append(None);continue
            target=STATE.get(key,(None,v['unit'],None))[1]
            try: converted=[scaled(n,v["unit"],target,key) for n in v["values"]]
            except ValueError:row.append("See report");continue
            reported=v.get("values_reported", [])
            precisions=v.get("reported_precisions", [])
            shown=[format_value(n,key,precisions[i] if i<len(precisions) else None,
                                reported[i] if i<len(reported) else None) for i,n in enumerate(converted)]
            row.append(converted[0] if len(converted)==1 and not reported and not precisions else shown[0] if len(shown)==1 else ", ".join(shown))
        if has_range:
            limits=c.get("temperature_range_celsius")
            row.append(" to ".join(f"{t:.2f}" for t in limits) if limits else None)
        rows.append(row)
    return headers,rows

# Public production helper; its established name would otherwise make pytest
# collect it when test modules import it directly.
test_condition_table.__test__ = False

def factor_value(package, condition_id, factor):
    if factor=="cycle_number":
        condition=next(c for c in package["conditions"] if c["condition_id"]==condition_id)
        return (condition["cycle_number"],"dimensionless",0,str(condition["cycle_number"])) if condition["cycle_number"] is not None else None
    found=[p for p in package["soil_properties"] if p["condition_id"]==condition_id and p["property"]==factor]
    if len(found)==1:
        p=found[0];target=STATE.get(factor,(None,p["unit"],None))[1]
        if (p.get("value_reported") not in (None,"") and p.get("original_value") is not None and
                p.get("original_unit") not in (None,"unknown","other")):
            precision=p.get("reported_precision")
            if precision is None:precision=decimal_precision(p["value_reported"])
            return p["original_value"],p["original_unit"],precision,p["value_reported"],"reported",p.get("unit_reported")
        try:return scaled(p["value"],p["unit"],target,factor),target,p.get("reported_precision"),None,"normalized",None
        except ValueError:return None
    return None

def factor_caption(factor,value,unit,precision=None,reported=None,representation="normalized",reported_unit=None):
    label=(REPORTED_FACTOR_LABEL.get(factor) if representation=="reported" else None) or STATE.get(factor,(None,None,factor.replace('_',' ').capitalize()))[2]
    symbol={"gram_per_cubic_centimeter":"g/cm³","mole_per_liter":"mol/L","kilopascal":"kPa",
            "cubic_meter_per_cubic_meter":"m³/m³","kilogram_per_kilogram":"kg/kg","percent":"%",
            "fraction":"-","dimensionless":""}.get(unit,reported_unit or "")
    separator = "" if symbol == "%" else " "
    return f"{label} = {format_value(value,factor,precision,reported)}" + (separator+symbol if symbol else "")
