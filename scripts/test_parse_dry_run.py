"""
scripts/test_parse_dry_run.py
Chạy Docling parse và dừng TRƯỚC bước Vision API.
Xuất: annotated page images, PIL crops, per-page report.md

Usage:
  python scripts/test_parse_dry_run.py --pdf "DATASET/file.pdf"
  python scripts/test_parse_dry_run.py --pdf "DATASET/file.pdf" --output ".agent/validation/Ingest/Result_Test_ParsingDocument"
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── sys.path: thêm backend vào để import ingest.vision._get_formula_image ─────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "backend"
for p in [str(_ROOT), str(_BACKEND)]:
    if p not in sys.path:
        sys.path.insert(0, p)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _get_page(item) -> int:
    try:
        prov = item.prov
        if prov and len(prov) > 0:
            return prov[0].page_no
    except Exception:
        pass
    return 0


def _get_caption(item) -> str:
    try:
        if hasattr(item, "captions") and item.captions:
            return str(item.captions[0].text)[:300]
    except Exception:
        pass
    return ""


def _safe_bbox(item, page_size_h: float) -> Optional[Tuple[float, float, float, float]]:
    """Trả về (l, t, r, b) đã convert sang TOPLEFT, hoặc None."""
    try:
        prov = item.prov
        if not prov:
            return None
        bbox = prov[0].bbox
        try:
            from docling_core.types.doc.page import CoordOrigin
            if getattr(bbox, "coord_origin", None) == CoordOrigin.BOTTOMLEFT:
                bbox = bbox.to_top_left_origin(page_size_h)
        except (ImportError, AttributeError):
            pass
        return (bbox.l, bbox.t, bbox.r, bbox.b)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1 — BBox Visualization
# ═══════════════════════════════════════════════════════════════════════════════

_COLORS = {
    "SectionHeaderItem": ("#FFD700", (255, 215,   0, 38)),
    "TextItem":          ("#3B82F6", ( 59, 130, 246, 25)),
    "ListItem":          ("#06B6D4", (  6, 182, 212, 35)),
    "TableItem":         ("#10B981", ( 16, 185, 129, 50)),
    "PictureItem":       ("#EF4444", (239,  68,  68, 50)),
    "FormulaItem":       ("#8B5CF6", (139,  92, 246, 50)),
}
_LABEL_PREFIX = {
    "SectionHeaderItem": "HDR",
    "TextItem":          "TXT",
    "ListItem":          "LST",
    "TableItem":         "TBL",
    "PictureItem":       "IMG",
    "FormulaItem":       "FRM",
}


def draw_bboxes_on_pages(doc, items_by_page: Dict[int, List[Dict]], out_dir: Path):
    """Vẽ bbox lên từng page image và lưu PNG."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("[WARN] PIL không có — bỏ qua phase visualize.")
        return

    pages = getattr(doc, "pages", {}) or {}
    page_dir = out_dir / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)

    for page_no, page_obj in pages.items():
        page_pil = getattr(getattr(page_obj, "image", None), "pil_image", None)
        if page_pil is None:
            print(f"  [WARN] Page {page_no}: không có page image → skip annotate")
            continue

        page_size = page_obj.size
        img_w, img_h = page_pil.size
        sx = img_w / page_size.width
        sy = img_h / page_size.height

        canvas = page_pil.copy().convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw_o = ImageDraw.Draw(overlay)
        draw_c = ImageDraw.Draw(canvas)

        for info in items_by_page.get(page_no, []):
            bbox_raw = info.get("bbox_raw")
            if bbox_raw is None:
                continue
            l, t, r, b = bbox_raw
            x0, y0 = int(l * sx), int(t * sy)
            x1, y1 = int(r * sx), int(b * sy)
            if x1 <= x0 or y1 <= y0:
                continue

            itype = info["type"]
            hex_c, rgba_fill = _COLORS.get(itype, ("#888888", (128, 128, 128, 30)))
            hex_rgb = tuple(int(hex_c.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

            draw_o.rectangle([x0, y0, x1, y1], fill=rgba_fill)
            draw_c.rectangle([x0, y0, x1, y1], outline=hex_rgb + (220,), width=2)

            label = info.get("label", "")[:40]
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
            draw_c.text((x0 + 3, y0 + 2), label, fill=hex_rgb + (255,), font=font)

        merged = Image.alpha_composite(canvas, overlay)
        out_path = page_dir / f"page_{page_no:02d}_annotated.png"
        merged.convert("RGB").save(str(out_path))
        print(f"  [PAGE] Saved: {out_path.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3 — Export PIL crops
# ═══════════════════════════════════════════════════════════════════════════════

def export_crops(visuals: List[Dict], out_dir: Path):
    """Lưu PIL images ra file PNG/MD."""
    frm_dir = out_dir / "formulas"
    img_dir = out_dir / "images"
    tbl_dir = out_dir / "tables"
    frm_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)
    tbl_dir.mkdir(parents=True, exist_ok=True)

    for v in visuals:
        pil = v.get("pil_image")
        if pil is None:
            continue
        vid = v["id"]
        vtype = v["type"]
        if vtype == "formula":
            path = frm_dir / f"{vid}.png"
        else:
            path = img_dir / f"{vid}.png"
        try:
            safe = pil.copy()
            if safe.mode not in ("RGB", "RGBA", "L"):
                safe = safe.convert("RGB")
            safe.save(str(path))
        except Exception as e:
            print(f"  [WARN] Cannot save {vid}: {e}")


def export_tables(tables: List[Dict], out_dir: Path):
    tbl_dir = out_dir / "tables"
    tbl_dir.mkdir(parents=True, exist_ok=True)
    for tbl in tables:
        tid = tbl["table_id"]
        path = tbl_dir / f"{tid}.md"
        content = f"# {tid}\n**Caption:** {tbl.get('caption','')}\n**Page:** {tbl['page']}\n\n{tbl['markdown']}\n"
        path.write_text(content, encoding="utf-8")


def prepare_output_dir(out_dir: Path) -> None:
    """Overwrite only known dry-run artifacts inside the PDF-specific output dir."""
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "pages",
        "formulas",
        "images",
        "tables",
        "report.md",
        "summary.json",
        "coverage_audit.json",
    ]:
        target = out_dir / name
        if target.resolve().parent != out_dir:
            raise RuntimeError(f"Refusing to remove path outside output dir: {target}")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def _bytes_to_gb(value: Optional[int]) -> Optional[float]:
    if value is None:
        return None
    return round(value / (1024 ** 3), 2)


def _get_perf_snapshot() -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "time": time.perf_counter(),
        "cpu_logical_count": os.cpu_count(),
        "psutil_available": False,
    }
    try:
        import psutil

        process = psutil.Process(os.getpid())
        cpu_times = process.cpu_times()
        vm = psutil.virtual_memory()
        snapshot.update({
            "psutil_available": True,
            "cpu_physical_count": psutil.cpu_count(logical=False),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "process_cpu_seconds": float(cpu_times.user + cpu_times.system),
            "process_rss_bytes": int(process.memory_info().rss),
            "ram_total_bytes": int(vm.total),
            "ram_available_bytes": int(vm.available),
            "ram_used_percent": float(vm.percent),
        })
    except Exception as exc:
        snapshot["psutil_error"] = str(exc)
    return snapshot


def _build_performance_metrics(
    run_start: Dict[str, Any],
    parse_start: Dict[str, Any],
    parse_end: Dict[str, Any],
    run_end: Dict[str, Any],
    configured_threads: int,
) -> Dict[str, Any]:
    parse_duration = max(0.0, parse_end["time"] - parse_start["time"])
    total_duration = max(0.0, run_end["time"] - run_start["time"])
    cpu_before = parse_start.get("process_cpu_seconds")
    cpu_after = parse_end.get("process_cpu_seconds")
    process_cpu_delta = None
    avg_cpu_cores_used = None
    if cpu_before is not None and cpu_after is not None:
        process_cpu_delta = max(0.0, float(cpu_after) - float(cpu_before))
        if parse_duration > 0:
            avg_cpu_cores_used = process_cpu_delta / parse_duration

    return {
        "parse_duration_seconds": round(parse_duration, 3),
        "total_duration_seconds": round(total_duration, 3),
        "configured_docling_threads": configured_threads,
        "cpu_logical_count": run_start.get("cpu_logical_count"),
        "cpu_physical_count": parse_start.get("cpu_physical_count"),
        "psutil_available": bool(parse_start.get("psutil_available")),
        "cpu_percent_before_parse": parse_start.get("cpu_percent"),
        "cpu_percent_after_parse": parse_end.get("cpu_percent"),
        "process_cpu_seconds_delta": round(process_cpu_delta, 3) if process_cpu_delta is not None else None,
        "average_process_cpu_cores_used": round(avg_cpu_cores_used, 2) if avg_cpu_cores_used is not None else None,
        "process_rss_gb_before_parse": _bytes_to_gb(parse_start.get("process_rss_bytes")),
        "process_rss_gb_after_parse": _bytes_to_gb(parse_end.get("process_rss_bytes")),
        "ram_total_gb": _bytes_to_gb(parse_start.get("ram_total_bytes")),
        "ram_available_gb_before_parse": _bytes_to_gb(parse_start.get("ram_available_bytes")),
        "ram_available_gb_after_parse": _bytes_to_gb(parse_end.get("ram_available_bytes")),
        "ram_used_percent_before_parse": parse_start.get("ram_used_percent"),
        "ram_used_percent_after_parse": parse_end.get("ram_used_percent"),
        "note": "CPU/RAM values are one-run dry-run telemetry, not a controlled benchmark.",
    }


def _recommend_minimum_laptop(performance: Dict[str, Any], pages_count: int) -> Dict[str, Any]:
    parse_seconds = float(performance.get("parse_duration_seconds") or 0.0)
    rss_after = performance.get("process_rss_gb_after_parse") or 0.0
    ram_total = performance.get("ram_total_gb") or 0.0
    avg_cores = performance.get("average_process_cpu_cores_used") or 0.0

    if parse_seconds <= 90 and rss_after <= 3.0:
        cpu = "4 physical cores / 8 logical threads"
        ram = "16 GB RAM"
        tier = "minimum_ok_for_similar_pdfs"
    elif parse_seconds <= 180 and rss_after <= 5.0:
        cpu = "6 physical cores / 12 logical threads"
        ram = "16-32 GB RAM"
        tier = "recommended_for_formula_heavy_pdfs"
    else:
        cpu = "8 physical cores / 16 logical threads"
        ram = "32 GB RAM"
        tier = "recommended_for_large_or_formula_heavy_batches"

    return {
        "tier": tier,
        "cpu": cpu,
        "ram": ram,
        "storage": "SSD recommended",
        "basis": (
            f"Observed {parse_seconds:.1f}s parse time for {pages_count} pages, "
            f"~{rss_after:.2f} GB process RSS after parse, "
            f"~{avg_cores:.2f} average process CPU cores used. "
            f"Host total RAM detected: {ram_total:.2f} GB."
        ),
        "caveat": "Estimate is based on one PDF dry-run; batch ingestion should be benchmarked separately.",
    }


def _norm_for_audit(text: str) -> str:
    return re.sub(r"\W+", "", (text or "").lower())


def _split_markdown_blocks(markdown: str) -> List[str]:
    parts = re.split(r"\n\s*\n", markdown or "")
    blocks = []
    for part in parts:
        text = re.sub(r"\s+", " ", part).strip()
        if len(text) >= 120 and not text.startswith("|"):
            blocks.append(text)
    return blocks


def write_coverage_audit(doc, items_by_page: Dict[int, List[Dict]], out_dir: Path) -> None:
    audit = {
        "note": (
            "Checks listed here verify text that exists in doc.export_to_markdown() but "
            "is not present in iterate_items text/list/section/table labels for the expected page, "
            "so no Docling bbox was available for the annotated image."
        ),
        "pages": {},
    }
    pages = getattr(doc, "pages", {}) or {}
    full_markdown = ""
    try:
        full_markdown = doc.export_to_markdown()
    except Exception:
        full_markdown = ""
    norm_full_markdown = _norm_for_audit(full_markdown)

    known_gap_checks = [
        {
            "page": 3,
            "needle": "the magnitude of the three-axis",
            "label": "page_3_left_column_preprocessing_paragraph",
        },
        {
            "page": 4,
            "needle": "perspective, the substantial",
            "label": "page_4_right_column_statistics_paragraph",
            "known_bbox_gap": True,
        },
        {
            "page": 6,
            "needle": "demonstrates a distinct superiority",
            "label": "page_6_left_column_comparison_paragraph",
        },
    ]

    def _excerpt_around(markdown: str, needle: str, radius: int = 420) -> str:
        idx = markdown.lower().find(needle.lower())
        if idx < 0:
            return ""
        start = max(0, idx - radius)
        end = min(len(markdown), idx + len(needle) + radius)
        return re.sub(r"\s+", " ", markdown[start:end]).strip()

    for page_no in sorted(pages.keys()):
        item_text = " ".join(
            str(item.get("text") or item.get("caption") or item.get("label") or "")
            for item in items_by_page.get(page_no, [])
            if item.get("type") in {"SectionHeaderItem", "TextItem", "ListItem", "TableItem"}
        )
        norm_item_text = _norm_for_audit(item_text)
        missing = []
        for check in known_gap_checks:
            if check["page"] != page_no:
                continue
            norm_needle = _norm_for_audit(check["needle"])
            if norm_needle not in norm_full_markdown:
                continue
            if norm_needle not in norm_item_text:
                missing.append({
                    "label": check["label"],
                    "needle": check["needle"],
                    "excerpt": _excerpt_around(full_markdown, check["needle"]),
                    "reason": "present_in_markdown_but_not_iterate_items_bbox",
                })
            elif check.get("known_bbox_gap"):
                missing.append({
                    "label": check["label"],
                    "needle": check["needle"],
                    "excerpt": _excerpt_around(full_markdown, check["needle"]),
                    "reason": "present_in_iterate_items_text_but_bbox_does_not_cover_full_visual_region",
                })
        audit["pages"][str(page_no)] = {
            "missing_block_count": len(missing),
            "missing_blocks": missing,
        }

    path = out_dir / "coverage_audit.json"
    path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[AUDIT] Saved: {path}")


def write_summary_json(
    file_name: str,
    pdf_path: str,
    counters: Dict,
    visuals: List[Dict],
    tables: List[Dict],
    items_by_page: Dict[int, List[Dict]],
    pages_count: int,
    out_dir: Path,
    performance: Dict[str, Any],
) -> None:
    n_img = sum(1 for v in visuals if v["type"] == "image")
    n_frm = sum(1 for v in visuals if v["type"] == "formula")
    pictures_detected = [
        item for page_items in items_by_page.values()
        for item in page_items
        if item["type"] == "PictureItem"
    ]
    formulas_detected = [
        item for page_items in items_by_page.values()
        for item in page_items
        if item["type"] == "FormulaItem"
    ]
    summary = {
        "file_name": file_name,
        "pdf_path": pdf_path,
        "pages": pages_count,
        "item_counts": {
            "section_headers": counters["section"],
            "text_blocks": counters["text"],
            "list_items": counters["list"],
            "tables": counters["table"],
            "pictures": counters["picture"],
            "formulas": counters["formula"],
        },
        "exports": {
            "tables_markdown": len(tables),
            "picture_png": n_img,
            "formula_png": n_frm,
        },
        "would_send_to_llm": {
            "images": n_img,
            "formulas": n_frm,
            "total": n_img + n_frm,
        },
        "detected_visuals": {
            "pictures_with_pil": sum(1 for item in pictures_detected if item.get("has_pil")),
            "pictures_without_pil": sum(1 for item in pictures_detected if not item.get("has_pil")),
            "formulas_with_crop": sum(1 for item in formulas_detected if item.get("pil_size", (0, 0)) != (0, 0)),
            "formulas_without_crop": sum(1 for item in formulas_detected if item.get("pil_size", (0, 0)) == (0, 0)),
        },
        "performance": performance,
        "recommended_minimum_laptop": _recommend_minimum_laptop(performance, pages_count),
        "pipeline_boundary": "after context_text fill, before asyncio_process_visuals",
        "vision_api_called": False,
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[SUMMARY] Saved: {summary_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2 — Summary report
# ═══════════════════════════════════════════════════════════════════════════════

def print_summary(
    file_name: str,
    counters: Dict,
    visuals: List[Dict],
    pages_count: int,
    performance: Dict[str, Any],
):
    n_img   = sum(1 for v in visuals if v["type"] == "image")
    n_frm   = sum(1 for v in visuals if v["type"] == "formula")
    total_v = n_img + n_frm

    cost_img = n_img * 0.003
    cost_frm = n_frm * 0.0005

    print("\nDOCLING PARSE REPORT - DRY RUN")
    print("=" * 40)
    print(f"File  : {file_name}")
    print(f"Pages : {pages_count}")
    print("\nITEM COUNTS (iterate_items)")
    print(f"- SectionHeaders : {counters['section']}")
    print(f"- Text blocks    : {counters['text']}")
    print(f"- List items     : {counters['list']}")
    print(f"- Tables         : {counters['table']}")
    print(f"- Pictures       : {counters['picture']}")
    print(f"- Formulas       : {counters['formula']}")
    print("\nVISUALS -> LLM (would send if Vision were enabled)")
    print(f"- Images         : {n_img} (Pass 1B, detail=high)")
    print(f"- Formulas       : {n_frm} (Pass 1A, detail=auto)")
    print(f"- Total calls    : {total_v}")
    print("\nESTIMATED COST (approx)")
    print(f"- Images         : ~${cost_img:.4f}")
    print(f"- Formulas       : ~${cost_frm:.4f}\n")
    print("PERFORMANCE")
    print(f"- Parse time     : {performance['parse_duration_seconds']}s")
    print(f"- Total time     : {performance['total_duration_seconds']}s")
    print(f"- Threads        : {performance['configured_docling_threads']}")
    print(f"- CPU cores      : physical={performance.get('cpu_physical_count')} logical={performance.get('cpu_logical_count')}")
    avg_cores = performance.get("average_process_cpu_cores_used")
    if avg_cores is not None:
        print(f"- Avg CPU cores  : ~{avg_cores} process cores during parse")
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4+5 — Per-page report.md
# ═══════════════════════════════════════════════════════════════════════════════

def generate_report(
    file_name: str,
    items_by_page: Dict[int, List[Dict]],
    visuals: List[Dict],
    out_dir: Path,
    performance: Dict[str, Any],
):
    vis_map = {v["id"]: v for v in visuals}
    lines = [f"# Dry-Run Parse Report\n**File:** `{file_name}`\n"]
    recommendation = _recommend_minimum_laptop(performance, sum(1 for page in items_by_page if page))
    lines.extend([
        "## Performance",
        f"- Parse duration: `{performance['parse_duration_seconds']}s`",
        f"- Total dry-run duration: `{performance['total_duration_seconds']}s`",
        f"- Configured Docling threads: `{performance['configured_docling_threads']}`",
        f"- CPU cores: physical=`{performance.get('cpu_physical_count')}`, logical=`{performance.get('cpu_logical_count')}`",
        f"- CPU percent before/after parse: `{performance.get('cpu_percent_before_parse')}` / `{performance.get('cpu_percent_after_parse')}`",
        f"- Process CPU seconds during parse: `{performance.get('process_cpu_seconds_delta')}`",
        f"- Average process CPU cores used during parse: `{performance.get('average_process_cpu_cores_used')}`",
        f"- Process RSS before/after parse: `{performance.get('process_rss_gb_before_parse')} GB` / `{performance.get('process_rss_gb_after_parse')} GB`",
        f"- RAM total: `{performance.get('ram_total_gb')} GB`",
        f"- RAM available before/after parse: `{performance.get('ram_available_gb_before_parse')} GB` / `{performance.get('ram_available_gb_after_parse')} GB`",
        f"- Minimum laptop estimate: `{recommendation['cpu']}`, `{recommendation['ram']}`, `{recommendation['storage']}`",
        f"- Basis: {recommendation['basis']}",
        f"- Caveat: {recommendation['caveat']}",
        "",
    ])

    for page_no in sorted(items_by_page.keys()):
        page_items = items_by_page[page_no]
        lines.append(f"\n---\n## Page {page_no}\n")

        sections = [i for i in page_items if i["type"] == "SectionHeaderItem"]
        texts    = [i for i in page_items if i["type"] == "TextItem"]
        lists    = [i for i in page_items if i["type"] == "ListItem"]
        tables   = [i for i in page_items if i["type"] == "TableItem"]
        pictures = [i for i in page_items if i["type"] == "PictureItem"]
        formulas = [i for i in page_items if i["type"] == "FormulaItem"]

        if sections:
            lines.append("### Section Headers")
            for s in sections:
                lines.append(f"- `{s['label'][:80]}`")

        lines.append(f"\n**Text blocks:** {len(texts)} (total ~{sum(len(t.get('text','')) for t in texts)} chars)")

        if lists:
            lines.append(f"\n### List Items ({len(lists)})")
            for li in lists:
                lines.append(f"- `{li['id']}` {li.get('text','')[:140]}")

        if tables:
            lines.append(f"\n### Tables ({len(tables)})")
            for t in tables:
                lines.append(f"- `{t['id']}` — caption: _{t.get('caption','(none)')[:60]}_")

        if pictures:
            lines.append(f"\n### Pictures ({len(pictures)})")
            for p in pictures:
                has_pil = p.get("has_pil", False)
                in_llm  = p["id"] in vis_map
                w, h    = p.get("pil_size", (0, 0))
                tag     = "✅ → LLM" if in_llm else "⚠️ no PIL"
                lines.append(f"- `{p['id']}` {tag} | size={w}×{h}px | caption: _{p.get('caption','(none)')[:60]}_")

        if formulas:
            lines.append(f"\n### Formulas ({len(formulas)})")
            for f in formulas:
                in_llm = f["id"] in vis_map
                w, h   = f.get("pil_size", (0, 0))
                if in_llm:
                    size_ok = w >= 20 and h >= 20
                    tag = f"✅ → LLM ({w}×{h}px)" if size_ok else f"⚠️ too small ({w}×{h}px)"
                else:
                    tag = "❌ no crop"
                lines.append(f"- `{f['id']}` {tag}")

        # Context preview for visuals on this page
        page_vis = [v for v in visuals if v.get("page") == page_no]
        if page_vis:
            lines.append("\n### Context Text Preview")
            for v in page_vis:
                ctx = v.get("context_text", "")
                if ctx:
                    lines.append(f"\n**{v['id']}** ({v['type']}):\n```\n{ctx[:1000]}\n```")

    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[REPORT] Saved: {report_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def run(pdf_path: str, output_dir: str):
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
    from ingest.parser import _clean_docling_item_text, _fill_visual_contexts
    from ingest.vision import _get_formula_image

    run_start = _get_perf_snapshot()
    pdf_path = str(Path(pdf_path).resolve())
    pdf_stem = Path(pdf_path).stem
    out_dir  = Path(output_dir) / pdf_stem
    prepare_output_dir(out_dir)

    print(f"\n[DRY-RUN] PDF   : {pdf_path}")
    print(f"[DRY-RUN] Output: {out_dir}\n")

    # ── Docling config (mirror parser.py chính xác) ───────────────────────────
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr                 = False
    pipeline_options.do_formula_enrichment  = False
    pipeline_options.generate_picture_images = True
    pipeline_options.generate_page_images   = True
    pipeline_options.images_scale           = 2.5
    configured_threads = 8
    pipeline_options.accelerator_options    = AcceleratorOptions(
        num_threads=configured_threads, device=AcceleratorDevice.CPU
    )
    pipeline_options.document_timeout = 600

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )

    print("[PARSE] Đang chạy Docling converter...")
    parse_start = _get_perf_snapshot()
    result = converter.convert(pdf_path)
    parse_end = _get_perf_snapshot()
    doc    = result.document
    gc.collect()
    print("[PARSE] Docling parse xong.\n")

    # ── Meta ──────────────────────────────────────────────────────────────────
    pages_obj   = getattr(doc, "pages", {}) or {}
    pages_count = len(pages_obj)

    # ── iterate_items ──────────────────────────────────────────────────────────
    counters = {"section": 0, "text": 0, "list": 0, "table": 0, "picture": 0, "formula": 0}
    items_by_page: Dict[int, List[Dict]] = {}
    visuals: List[Dict] = []
    tables_list: List[Dict] = []
    raw_blocks: List[Dict] = []

    tbl_idx = img_idx = frm_idx = 0
    sec_idx = 0
    current_section_id = "sec_0"
    current_section_label = "introduction"

    for item, _level in doc.iterate_items():
        itype = type(item).__name__
        page  = _get_page(item)
        items_by_page.setdefault(page, [])

        # BBox (TOPLEFT sau convert)
        page_obj  = pages_obj.get(page)
        page_h    = getattr(getattr(page_obj, "size", None), "height", 0) if page_obj else 0
        bbox_raw  = _safe_bbox(item, page_h)   # (l, t, r, b) TOPLEFT

        if itype == "SectionHeaderItem":
            counters["section"] += 1
            sec_idx += 1
            label = getattr(item, "text", "section") or "section"
            current_section_id = f"sec_{sec_idx}"
            current_section_label = label
            items_by_page[page].append({
                "type": itype, "id": f"hdr_{page}_{counters['section']}",
                "label": f"HDR: {label[:40]}", "bbox_raw": bbox_raw,
                "text": label,
            })

        elif itype == "TextItem":
            counters["text"] += 1
            text = _clean_docling_item_text(item)
            if text.strip():
                raw_blocks.append({
                    "text": text,
                    "page": page,
                    "section_id": current_section_id,
                    "section_label": current_section_label,
                    "block_type": "text",
                })
            items_by_page[page].append({
                "type": itype, "id": f"txt_{page}_{counters['text']}",
                "label": f"TXT: {text[:30]}",
                "bbox_raw": bbox_raw, "text": text,
            })

        elif itype == "ListItem":
            counters["list"] += 1
            text = _clean_docling_item_text(item)
            if text.strip():
                raw_blocks.append({
                    "text": text,
                    "page": page,
                    "section_id": current_section_id,
                    "section_label": current_section_label,
                    "block_type": "list",
                })
            items_by_page[page].append({
                "type": itype, "id": f"lst_{page}_{counters['list']}",
                "label": f"LST: {text[:30]}",
                "bbox_raw": bbox_raw, "text": text,
            })

        elif itype == "TableItem":
            counters["table"] += 1
            tbl_idx += 1
            tbl_id = f"table_{page}_{tbl_idx}"
            try:
                md = item.export_to_markdown(doc)
            except TypeError:
                try:
                    md = item.export_to_markdown()
                except Exception:
                    md = f"[TABLE_{tbl_idx}]"
            except Exception:
                md = f"[TABLE_{tbl_idx}]"
            if "table-not-decoded" in md:
                md = md.replace("<!-- table-not-decoded -->", "[Table]")
            cap = _get_caption(item)
            tables_list.append({"table_id": tbl_id, "markdown": md, "page": page, "caption": cap})
            raw_blocks.append({
                "text": md,
                "page": page,
                "section_id": current_section_id,
                "section_label": current_section_label,
                "block_type": "table",
                "table_id": tbl_id,
            })
            items_by_page[page].append({
                "type": itype, "id": tbl_id,
                "label": f"TBL: {cap[:40] or tbl_id}",
                "bbox_raw": bbox_raw, "caption": cap,
            })

        elif itype == "PictureItem":
            counters["picture"] += 1
            img_idx += 1
            img_id = f"img_{page}_{img_idx}"
            cap = _get_caption(item)

            pil_img = None
            try:
                if hasattr(item, "image") and item.image is not None:
                    pil_img = getattr(item.image, "pil_image", None)
                if pil_img is None and hasattr(item, "get_image"):
                    pil_img = item.get_image(doc)
            except Exception:
                pass

            pil_size = pil_img.size if pil_img else (0, 0)
            items_by_page[page].append({
                "type": itype, "id": img_id,
                "label": f"IMG: {cap[:40] or img_id}",
                "bbox_raw": bbox_raw, "caption": cap,
                "has_pil": pil_img is not None, "pil_size": pil_size,
            })

            if pil_img is not None:
                visuals.append({
                    "type": "image", "pil_image": pil_img, "id": img_id,
                    "page": page, "caption": cap, "context_text": "",
                    "figure_number": "", "raw_blocks_idx": len(raw_blocks),
                    "pil_size": pil_size,
                })
            else:
                print(f"  [WARN] {img_id}: không có PIL image")

        elif itype == "FormulaItem":
            counters["formula"] += 1
            frm_idx += 1
            frm_id = f"formula_{page}_{frm_idx}"

            pil_img = _get_formula_image(item, page, doc, formula_id=frm_id)
            pil_size = pil_img.size if pil_img else (0, 0)

            items_by_page[page].append({
                "type": itype, "id": frm_id,
                "label": f"FRM: {frm_id}",
                "bbox_raw": bbox_raw, "pil_size": pil_size,
            })

            raw_blocks.append({
                "text": f"[Mathematical Formula {frm_idx} - Pending API]",
                "page": page,
                "section_id": current_section_id,
                "section_label": current_section_label,
                "block_type": "formula",
                "formula_id": frm_id,
            })

            if pil_img is not None:
                visuals.append({
                    "type": "formula", "pil_image": pil_img, "id": frm_id,
                    "page": page, "context_text": "", "pil_size": pil_size,
                    "raw_blocks_idx": len(raw_blocks) - 1,
                })
            else:
                print(f"  [WARN] {frm_id}: crop thất bại hoặc quá nhỏ → skip LLM")

    # ── Fill context_text bằng cùng helper với parser.py ──────────────────────
    _fill_visual_contexts(raw_blocks, visuals)

    print("[PARSE] iterate_items xong, context_text đã fill.\n")

    # ── Phase 1 — BBox visualization ──────────────────────────────────────────
    print("[PHASE 1] Vẽ bounding boxes lên page images...")
    draw_bboxes_on_pages(doc, items_by_page, out_dir)

    # ── Phase 3 — Export crops ────────────────────────────────────────────────
    print("\n[PHASE 3] Export PIL crops...")
    export_crops(visuals, out_dir)
    export_tables(tables_list, out_dir)
    print(f"  Đã lưu {sum(1 for v in visuals if v['type']=='formula')} formula crops")
    print(f"  Đã lưu {sum(1 for v in visuals if v['type']=='image')} image crops")
    print(f"  Đã lưu {len(tables_list)} table markdowns")

    performance = _build_performance_metrics(
        run_start,
        parse_start,
        parse_end,
        _get_perf_snapshot(),
        configured_threads,
    )

    # ── Phase 2 — Summary ─────────────────────────────────────────────────────
    print_summary(Path(pdf_path).name, counters, visuals, pages_count, performance)

    # ── Phase 4+5 — Report ────────────────────────────────────────────────────
    print("\n[PHASE 4+5] Tạo report.md...")
    generate_report(Path(pdf_path).name, items_by_page, visuals, out_dir, performance)
    write_summary_json(
        Path(pdf_path).name,
        pdf_path,
        counters,
        visuals,
        tables_list,
        items_by_page,
        pages_count,
        out_dir,
        performance,
    )
    write_coverage_audit(doc, items_by_page, out_dir)

    print(f"\n[DONE] Tất cả output tại: {out_dir}")
    print(f"       Pages annotated : {out_dir / 'pages'}")
    print(f"       Formula crops   : {out_dir / 'formulas'}")
    print(f"       Image crops     : {out_dir / 'images'}")
    print(f"       Table markdowns : {out_dir / 'tables'}")
    print(f"       Report          : {out_dir / 'report.md'}")
    print(f"       Summary         : {out_dir / 'summary.json'}")
    print(f"       Coverage audit  : {out_dir / 'coverage_audit.json'}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Dry-run Docling parse (no Vision API)")
    ap.add_argument("--pdf",    required=True,               help="Path đến file PDF")
    ap.add_argument(
        "--output",
        default=r".agent\validation\Ingest\Result_Test_ParsingDocument",
        help="Thư mục output (default: .agent/validation/Ingest/Result_Test_ParsingDocument)",
    )
    args = ap.parse_args()
    run(args.pdf, args.output)
