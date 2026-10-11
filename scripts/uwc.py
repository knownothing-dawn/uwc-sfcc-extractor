"""UWC-first preparation and compact per-paper production export."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from quality import SCHEMA, qa, read_json, review_severity
from presentation import workbook
from reporting import markdown_report
from conversion import convert_preferred
from hardening import prepare_scientific

UWC_TERMS = re.compile(r"unfrozen\s+water|\buwc\b|\bsfcc\b|soil\s+freezing\s+characteristic|freezing\s+characteristic|liquid\s+water|未冻水|冻结特征", re.I)
CONTEXT_TERMS = re.compile(r"materials?\s+and\s+methods?|experimental|freezing|thawing|试验|冻结|融化", re.I)
PROPERTY_TERMS = re.compile(r"density|porosity|void ratio|specific (?:gravity|surface)|liquid limit|plastic limit|salt content|specimen|sample preparation|密度|孔隙|液限|塑限|比表面积|含盐|试样", re.I)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def empty_package(paper_id, filename, source_sha256):
    paper = {key: None for key in SCHEMA["$defs"]["paper"]["properties"]}
    paper.update(paper_id=paper_id, authors=[], pdf_filename=filename, source_sha256=source_sha256,
                 extraction_status="partial", review_status="insufficient", coverage_verified=False,
                 evidence_ids=[], confidence="low", database_ready=False)
    # Existing producers remain on the compatible 1.5 contract until they
    # explicitly opt in to v1.6's strict raw/axis/numerical gates.
    return {"schema_version": "1.5.0", "vocabulary_version": "1.5.0", "paper": paper,
            **{name: [] for name in ("samples", "conditions", "soil_properties", "curves", "uwc_points", "models",
                                    "evidence", "derivations", "review_queue", "display_translations", "raw_trace_points")}}


def geometry_json(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {key: geometry_json(child) for key, child in value.items()}
    return [geometry_json(child) for child in value]


def prepare(pdf, paper_id, out, mode="production"):
    import pymupdf as fitz
    pdf, out = Path(pdf).resolve(), Path(out).resolve()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", paper_id):
        raise ValueError("Invalid paper_id")
    if mode not in ("production", "benchmark") or not pdf.is_file():
        raise ValueError("A readable PDF and production/benchmark mode are required")
    target = out / paper_id
    if target.exists():
        raise ValueError("Paper directory already exists; use another output root or paper ID")
    with fitz.open(pdf) as doc:
        if doc.needs_pass or not doc.page_count:
            raise ValueError("Source PDF must have accessible pages")
        internal = target / ".internal"
        internal.mkdir(parents=True)
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        package = empty_package(paper_id, pdf.name, digest)
        candidates = {"source_pdf": str(pdf), "source_sha256": digest, "page_count": doc.page_count,
                      "metadata_candidates": {k + "_reported": doc.metadata.get(k) for k in ("title", "author", "subject", "keywords")}, "pages": []}
        # Retain all page text; keyword absence never proves absence of UWC data.
        for index, page in enumerate(doc):
            text = page.get_text("text", sort=True)
            candidates["pages"].append({"page": index + 1, "text_reported": text,
                "uwc_keyword_hit": bool(UWC_TERMS.search(text)), "context_keyword_hit": bool(CONTEXT_TERMS.search(text)),
                "property_keyword_hit": bool(PROPERTY_TERMS.search(text)),
                "numerical_source_candidate": bool(UWC_TERMS.search(text) and re.search(r"\d|table|supplement|data availability|表|数据", text, re.I)),
                "requires_visual_or_ocr_review": not bool(text.strip())})
        write_json(internal / "candidates.json", candidates)
        write_json(internal / f"{paper_id}_UWC.json", package)
    if mode == "benchmark":
        inspect_pages(target, range(1, candidates["page_count"] + 1), tables=True, vectors=True, render=True)
    return target


def inspect_pages(package_dir, pages, tables=False, vectors=False, render=False):
    """Restrict the existing expensive PDF operations to explicitly selected pages."""
    import pymupdf as fitz
    internal = Path(package_dir).resolve() / ".internal"
    candidates = read_json(internal / "candidates.json")
    source = Path(candidates["source_pdf"])
    if hashlib.sha256(source.read_bytes()).hexdigest() != candidates["source_sha256"]:
        raise ValueError("Source PDF changed since preparation")
    pages = sorted(set(pages))
    if not pages or min(pages) < 1 or max(pages) > candidates["page_count"]:
        raise ValueError("Selected page indices are outside the PDF")
    out = internal / "pages"
    out.mkdir(exist_ok=True)
    with fitz.open(source) as doc:
        for number in pages:
            page = doc[number - 1]
            rotation = page.rotation
            page.set_rotation(0)
            prefix = f"page_{number:04d}"
            if vectors:
                paths = [{"path_index": i, "items": geometry_json(raw.get("items", [])),
                          "stroke_color": geometry_json(raw.get("color")), "fill_color": geometry_json(raw.get("fill")),
                          "line_width": raw.get("width"), "dash_pattern_reported": raw.get("dashes"),
                          "bbox": geometry_json(raw.get("rect")), "closed": raw.get("closePath")}
                         for i, raw in enumerate(page.get_drawings())]
                write_json(out / f"{prefix}_vectors.json", paths)
            if tables:
                finder = page.find_tables()
                write_json(out / f"{prefix}_tables.json", [{"table_index": i, "bbox": list(t.bbox), "cells_reported": t.extract()} for i, t in enumerate(finder.tables)])
            if render:
                page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(out / f"{prefix}.png")
            write_json(out / f"{prefix}_coordinates.json", {"page": number, "original_rotation_degrees": rotation,
                       "coordinate_system": "unrotated_pdf_points", "page_bounds": list(page.rect),
                       "render_pixels_per_pdf_point": 2 if render else None})
    return out


def export(package, out, mode="production"):
    target = Path(out).resolve()
    pid = package['paper']['paper_id']
    # Detect an open/locked workbook before changing its companion scientific record.
    for path in (target / f'{pid}_UWC.xlsx', target / f'{pid}_report.md', target / '.internal' / f'{pid}_UWC.json'):
        if path.exists():
            with path.open('r+b'): pass
    # Conversion already owns a private copy; avoid copying the full dataset twice.
    result = qa(prepare_scientific(package, target), target, mode, copy_package=False)
    internal = target / ".internal"
    internal.mkdir(parents=True, exist_ok=True)
    pid = result["paper"]["paper_id"]
    report = markdown_report(result)
    workbook(result, target / f"{pid}_UWC.xlsx")
    (target / f"{pid}_report.md").write_text(report, encoding="utf-8")
    write_json(internal / f"{pid}_UWC.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    for flag in ("pdf", "paper-id", "out"):
        p.add_argument("--" + flag, required=True)
    p.add_argument("--mode", choices=("production", "benchmark"), default="production")
    p = commands.add_parser("inspect")
    p.add_argument("package")
    p.add_argument("--pages", nargs="+", type=int, required=True)
    for flag in ("tables", "vectors", "render"):
        p.add_argument("--" + flag, action="store_true")
    for command in ("validate", "export", "recover"):
        p = commands.add_parser(command)
        p.add_argument("dataset")
        if command == "export":
            p.add_argument("--out", required=True)
        p.add_argument("--mode", choices=("production", "benchmark"), default="production")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            print(prepare(args.pdf, args.paper_id, args.out, args.mode))
        elif args.command == "inspect":
            print(inspect_pages(args.package, args.pages, args.tables, args.vectors, args.render))
        else:
            package = read_json(args.dataset)
            package_root = Path(args.dataset).resolve().parent
            if package_root.name == '.internal': package_root = package_root.parent
            if args.command == 'export': result = export(package, args.out, args.mode)
            elif args.command == 'recover':
                result = qa(prepare_scientific(package, package_root), package_root, args.mode, copy_package=False)
                write_json(args.dataset, result)
            else: result = qa(prepare_scientific(package, package_root), package_root, args.mode, copy_package=False)
            reviews = [r for r in result["review_queue"] if r["status"] == "open"]
            print(json.dumps({"paper_id": result["paper"]["paper_id"], "extraction_status": result["paper"]["extraction_status"],
                              "database_ready": result['paper'].get('database_ready', False),
                              "critical_issues": sum(review_severity(r) == "critical" for r in reviews),
                              "important_issues": sum(review_severity(r) == "important" for r in reviews)}))
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
