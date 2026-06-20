"""
ingest/parser.py — parse_document() và helpers: find_documents, utilities.
"""

from __future__ import annotations

import gc
import hashlib
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ingest.config import (
    DATA_DIR, SUPPORTED_EXTS, IMAGE_VLM_MODEL, VECTOR_DIR,
)
from ingest.models import ParsedDocument
from ingest.analysis import ensure_analysis_short
from ingest.vision import (
    _get_formula_image, _clean_latex_output,
    asyncio_process_visuals, _run_async_in_new_loop,
)


# ── Utilities ─────────────────────────────────────────────────────────────────

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def calculate_file_hash(file_path: str) -> str:
    """SHA256 của binary content file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            sha256.update(block)
    return sha256.hexdigest()


def normalize_text(text: str) -> str:
    """Lowercase, strip, collapse whitespace, remove diacritics nhẹ."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text


def detect_language(text: str) -> str:
    """Heuristic đơn giản: kiểm tra ký tự tiếng Việt."""
    vi_pattern = re.compile(
        r"[àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]",
        re.I,
    )
    if vi_pattern.search(text[:500]):
        return "vi"
    ascii_ratio = sum(1 for c in text[:500] if ord(c) < 128) / max(len(text[:500]), 1)
    return "en" if ascii_ratio > 0.85 else "unknown"


# ── Docling text artifact cleaner ─────────────────────────────────────────────

# R3 fix: pattern matches 2+ consecutive space-separated uppercase letters
# e.g. "I E E E" (4 chars), "I E E" (3 chars), "A I" (2 chars) → all normalized
_DOCLING_TEXT_FIXES = [
    (re.compile(r'\b[A-Z](?: [A-Z])+\b'),               lambda m: m.group(0).replace(' ', '')),
    (re.compile(r'/floorleft\s*'),                       r'⌊'),
    (re.compile(r'/floorright\s*\d?'),                   r'⌋'),
    (re.compile(r'/negationslash'),                      r'≠'),
    (re.compile(r'/epsilon(\d)'),                        lambda m: f'ε_{m.group(1)}'),   # CHANGED: thêm _
    (re.compile(r'/epsilon'),                            r'ε'),
    (re.compile(r'ε_(\d)\s+([A-Za-z])(?=[\s,.\)]|$)'),  lambda m: f'ε_{{{m.group(1)},{m.group(2)}}}'),  # NEW
    (re.compile(r',\s{2,}'),                             r', '),
]


def _post_clean_docling_text(text: str) -> str:
    """Post-process text từ Docling để fix artifacts phổ biến."""
    for pattern, replacement in _DOCLING_TEXT_FIXES:
        if callable(replacement):
            text = pattern.sub(replacement, text)
        else:
            text = pattern.sub(replacement, text)
    return text


# ── Find documents ────────────────────────────────────────────────────────────

def find_documents(data_dir: str = DATA_DIR) -> List[str]:
    """Tìm tất cả file được hỗ trợ trong data_dir, sorted."""
    if not os.path.exists(data_dir):
        raise FileNotFoundError(f"[FIND] Thư mục không tồn tại: {data_dir}")

    results = []
    for root, _dirs, files in os.walk(data_dir):
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext in SUPPORTED_EXTS:
                results.append(os.path.join(root, fname))
    return sorted(results)


# ── Docling item helpers ──────────────────────────────────────────────────────

def _get_page(item) -> int:
    """Lấy page number an toàn từ Docling item."""
    try:
        prov = item.prov
        if prov and len(prov) > 0:
            return prov[0].page_no
    except (AttributeError, IndexError, TypeError):
        pass
    return 0


def _get_caption(item, doc) -> str:
    """Lấy caption của table/image nếu có."""
    try:
        if hasattr(item, "captions") and item.captions:
            caps = item.captions
            if caps:
                return str(caps[0].text)[:300]
    except Exception:
        pass
    return ""


def _clean_docling_item_text(item) -> str:
    """Return cleaned text for text-like Docling items."""
    text_val = getattr(item, "text", "") or ""
    if "formula-not-decoded" in text_val:
        text_val = text_val.replace(
            "<!-- formula-not-decoded -->",
            "[Mathematical Formula - Not Decoded]",
        )
    return _post_clean_docling_text(text_val)


def _is_context_block(block: Dict[str, Any]) -> bool:
    return block.get("block_type") in {"text", "list"}


def _join_context(parts: List[str], limit: int) -> str:
    cleaned: List[str] = []
    seen = set()
    for part in parts:
        text = re.sub(r"\s+", " ", (part or "")).strip()
        if not text:
            continue
        key = normalize_text(text)[:120]
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return " ".join(cleaned)[:limit]


def _looks_like_caption(text: str) -> bool:
    return bool(re.match(r"(?i)^\s*(?:fig(?:ure)?\.?|table)\s*\d+\s*[:.-]", text or ""))


def _looks_like_continuation(text: str) -> bool:
    stripped = (text or "").lstrip()
    return bool(stripped) and stripped[0].islower()


def _extract_figure_number(caption: str) -> str:
    if not caption:
        return ""
    m = re.search(r"[Ff]ig(?:ure|\.)?\s*\.?\s*(\d+)", caption)
    return f"Fig. {m.group(1)}" if m else ""


# ── Table caption helpers ─────────────────────────────────────────────────────

# Khớp: "Table 1:", "Table II.", "TABLE 3 –", "Table 4 -", v.v.
_TABLE_CAPTION_RE = re.compile(
    r"(?i)^\s*table\s+[\dIVXivx]+[\s:.\-\u2013\u2014]",
)


def _looks_like_table_caption(text: str) -> bool:
    """True nếu text là caption bảng dạng 'Table N: ...' hoặc 'Table IV. ...'."""
    return bool(_TABLE_CAPTION_RE.match(text or ""))


def _extract_table_caption_from_markdown(md: str) -> str:
    """Lấy caption từ dòng đầu tiên của tbl_md.

    Docling embed caption vào dòng đầu export_to_markdown() thay vì item.captions[].
    Xác nhận qua test thực tế: tất cả 9 table.md đều có dòng đầu dạng
    'Table N: <nội dung caption đầy đủ>'.

    Returns: caption string (≤300 chars) hoặc "" nếu không phát hiện.
    """
    first_line = (md or "").strip().split("\n")[0].strip()
    return first_line[:300] if _looks_like_table_caption(first_line) else ""


def _get_item_self_ref(item) -> str:
    """Return a stable Docling self_ref/get_ref string when available."""
    try:
        self_ref = str(getattr(item, "self_ref", "") or "").strip()
        if self_ref:
            return self_ref
    except Exception:
        pass
    try:
        ref = item.get_ref()
        cref = str(getattr(ref, "cref", "") or "").strip()
        if cref:
            return cref
    except Exception:
        pass
    return ""


def _save_pil_asset(pil_image, file_hash: str, kind: str, asset_id: str) -> str:
    """Persist a visual asset under backend/db/assets and return project-relative path."""
    if pil_image is None:
        return ""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.dirname(backend_dir)
    asset_dir = os.path.join(VECTOR_DIR, "assets", file_hash, kind)
    os.makedirs(asset_dir, exist_ok=True)
    abs_path = os.path.join(asset_dir, f"{asset_id}.png")
    try:
        safe_img = pil_image.copy()
        if safe_img.mode not in ("RGB", "RGBA", "L"):
            safe_img = safe_img.convert("RGBA")
        safe_img.save(abs_path, format="PNG")
    except Exception as e:
        print(f"[PARSE][WARN] Không lưu được visual asset {asset_id}: {e}")
        return ""
    return os.path.relpath(abs_path, project_root).replace("\\", "/")


def _build_formula_context(raw_blocks: List[Dict[str, Any]], idx: int, page: int) -> str:
    """Build local context around a formula, prioritizing following Symbols/Where lists."""
    before: List[str] = []
    for j in range(idx - 1, -1, -1):
        block = raw_blocks[j]
        if block.get("page") != page:
            continue
        if block.get("block_type") in {"formula", "table"}:
            break
        if _is_context_block(block):
            text = block.get("text", "")
            # Keep only the closest short lead-in before the formula. The
            # definition list after the formula is usually more useful.
            before.append(text[-320:])
            break

    after: List[str] = []
    in_definition_group = False
    for j in range(idx + 1, len(raw_blocks)):
        block = raw_blocks[j]
        if block.get("page") != page:
            continue
        block_type = block.get("block_type")
        if block_type in {"formula", "table"}:
            break
        if not _is_context_block(block):
            continue

        text = block.get("text", "")
        is_definition_label = bool(re.match(r"(?i)^\s*(symbols?|where)\s*:?\s*$", text.strip()))
        if is_definition_label:
            in_definition_group = True
            after.append(text)
            continue
        if block_type == "list" and not after and not in_definition_group:
            section_label = (block.get("section_label") or "").strip()
            if re.match(r"(?i)^\s*(symbols?|where)\s*:?\s*$", section_label):
                in_definition_group = True
                after.append(section_label)
                after.append(text)
                continue
        if in_definition_group and block_type == "list":
            after.append(text)
            continue
        if in_definition_group:
            break
        # If no Symbols/Where block exists, keep one short local text block after the formula.
        if len(after) < 1:
            after.append(text)
            continue
        break

    return _join_context(list(reversed(before)) + after, 1100)


def _build_image_context(raw_blocks: List[Dict[str, Any]], idx: int, page: int) -> Tuple[str, str, str]:
    """Build image context from the figure caption only."""
    caption = ""
    for block in raw_blocks[idx : idx + 20]:
        if block.get("page") != page:
            continue
        if block.get("block_type") != "text":
            continue
        text = block.get("text", "")
        if _looks_like_caption(text):
            if not caption:
                caption = text.strip()[:300]
            break
    return caption, caption, _extract_figure_number(caption)


def _build_table_context(raw_blocks: List[Dict[str, Any]], idx: int, page: int) -> str:
    """Build table context from nearby caption/lead-in text above the table."""
    before: List[str] = []
    for j in range(idx - 1, -1, -1):
        block = raw_blocks[j]
        if block.get("page") != page:
            continue
        if block.get("block_type") in {"table", "formula"}:
            break
        if _is_context_block(block):
            before.append(block.get("text", "")[-500:])
            break
    return _join_context(list(reversed(before)), 600)


def _fill_visual_contexts(raw_blocks: List[Dict[str, Any]], visuals: List[Dict[str, Any]]) -> None:
    """Mutate visual records with improved local context before Vision API.

    Table: context_text đã được set = caption tại Phase 3 (iterate_items).
    Không cần scan raw_blocks vì caption đã đầy đủ từ tbl_md dòng đầu.
    Formula và Image vẫn cần scan raw_blocks để build context.
    """
    for visual in visuals:
        idx  = visual.get("raw_blocks_idx", len(raw_blocks))
        page = visual.get("page", 0)
        vtype = visual.get("type")

        if vtype == "formula":
            visual["context_text"] = _build_formula_context(raw_blocks, idx, page)

        elif vtype == "image":
            context_text, caption, figure_number = _build_image_context(raw_blocks, idx, page)
            visual["context_text"] = context_text
            if (not visual.get("caption") or len(visual.get("caption", "")) < 10) and caption:
                visual["caption"] = caption
            visual["figure_number"] = figure_number or _extract_figure_number(visual.get("caption", ""))

        elif vtype == "table":
            context_text = _build_table_context(raw_blocks, idx, page)
            if context_text and context_text != visual.get("caption", ""):
                visual["context_text"] = context_text


# ── Main parse function ───────────────────────────────────────────────────────

def _configure_pdf_pipeline_options(pipeline_options, skip_visual_analysis: bool) -> None:
    """Configure Docling PDF parsing for either text-fast or visual-rich ingest."""
    pipeline_options.do_ocr = False
    pipeline_options.do_formula_enrichment = False
    pipeline_options.generate_picture_images = not skip_visual_analysis
    pipeline_options.generate_page_images = not skip_visual_analysis
    pipeline_options.images_scale = 1.0 if skip_visual_analysis else 2.5


def parse_document(
    file_path: str,
    skip_visual_analysis: bool = False,
) -> Optional[Tuple[ParsedDocument, Any]]:
    """
    Parse một file bằng Docling.
    Trả về (ParsedDocument, doc_obj) hoặc None nếu fail.
    """
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
    except ImportError:
        print("[PARSE][ERR] docling chưa được cài. Chạy: pip install docling")
        return None

    print(f"[PARSE] Đang parse: {file_path}")

    try:
        pipeline_options = PdfPipelineOptions()
        _configure_pdf_pipeline_options(pipeline_options, skip_visual_analysis)

        safe_threads = 8  # Chỉ định cứng 8 luồng cho việc parsing
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=safe_threads,
            device=AcceleratorDevice.CPU,
        )
        pipeline_options.document_timeout = 600

        image_state = "DISABLED" if skip_visual_analysis else "ENABLED"
        print(
            "[PARSE] Formula VLM: DISABLED | "
            f"Picture images: {image_state} "
            f"(scale={pipeline_options.images_scale}, threads={safe_threads}) | PyMuPDF: DISABLED"
        )

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        try:
            result = converter.convert(file_path)
            doc = result.document
        except Exception as e:
            print(f"[PARSE][WARN] Không parse được {file_path}: {e}")
            return None
        finally:
            gc.collect()

    except Exception as e:
        print(f"[PARSE][WARN] Không parse được {file_path}: {e}")
        return None


    file_name = os.path.basename(file_path)
    file_hash = calculate_file_hash(file_path)
    ext = Path(file_path).suffix.lower().lstrip(".")
    doc_type = ext if ext in {"pdf", "docx", "pptx", "html", "htm"} else "unknown"

    # --- Metadata ---
    meta: Dict[str, Any] = {}
    try:
        if hasattr(doc, "metadata") and doc.metadata:
            dm = doc.metadata
            meta["title"]       = getattr(dm, "title", "") or ""
            meta["authors"]     = str(getattr(dm, "authors", "") or "")
            meta["total_pages"] = getattr(dm, "page_count", 0) or 0
    except Exception:
        pass

    # --- Duyệt cấu trúc document ---
    sections:   List[Dict[str, Any]] = []
    tables:     List[Dict[str, Any]] = []
    images:     List[Dict[str, Any]] = []
    formulas:   List[Dict[str, Any]] = []
    raw_blocks: List[Dict[str, Any]] = []

    current_section_id    = "sec_0"
    current_section_label = "introduction"
    sec_idx     = 0
    tbl_idx     = 0
    img_idx     = 0
    formula_idx = 0

    visuals_to_process: List[Dict[str, Any]] = []

    try:
        for item, _level in doc.iterate_items():
            item_type = type(item).__name__
            page = _get_page(item)

            if item_type == "SectionHeaderItem":
                sec_idx += 1
                current_section_id    = f"sec_{sec_idx}"
                current_section_label = getattr(item, "text", "section") or "section"
                sections.append({
                    "section_id": current_section_id,
                    "label":      current_section_label,
                    "text":       current_section_label,
                    "page":       page,
                    "level":      _level,
                })

            elif item_type == "TextItem":
                text_val = _clean_docling_item_text(item)
                if text_val.strip():
                    raw_blocks.append({
                        "text":       text_val,
                        "page":       page,
                        "section_id": current_section_id,
                        "section_label": current_section_label,
                        "block_type": "text",
                    })

            elif item_type == "ListItem":
                text_val = _clean_docling_item_text(item)
                if text_val.strip():
                    raw_blocks.append({
                        "text":       text_val,
                        "page":       page,
                        "section_id": current_section_id,
                        "section_label": current_section_label,
                        "block_type": "list",
                    })

            elif item_type == "TableItem":
                tbl_idx += 1
                tbl_md = ""
                try:
                    tbl_md = item.export_to_markdown(doc)
                except TypeError:
                    try:
                        tbl_md = item.export_to_markdown()
                    except Exception:
                        tbl_md = f"[TABLE_{tbl_idx}]"
                except Exception:
                    tbl_md = f"[TABLE_{tbl_idx}]"

                if "table-not-decoded" in tbl_md:
                    tbl_md = tbl_md.replace("<!-- table-not-decoded -->", "[Table]")

                # Ưu tiên 1: caption từ Docling item.captions[] (thường rỗng với IEEE/ACM)
                caption = _get_caption(item, doc)

                # Ưu tiên 2: caption embed trong dòng đầu tbl_md (phổ biến nhất)
                # Xác nhận qua test: 7/9 table có caption ở đây
                if not caption:
                    caption = _extract_table_caption_from_markdown(tbl_md)

                # Ưu tiên 3: SectionHeaderItem ngay trước table bị Docling parse nhầm
                # thành section (edge case page 11: "Table 8: Full results...")
                if not caption and _looks_like_table_caption(current_section_label):
                    caption = current_section_label

                tbl_id = f"table_{page}_{tbl_idx}"
                table_self_ref = _get_item_self_ref(item)
                tables.append({
                    "table_id":          tbl_id,
                    "markdown":          tbl_md,
                    "page":              page,
                    "caption":           caption,
                    "context_text":      caption,
                    "analysis_markdown": "",
                    "self_ref":          table_self_ref,
                })
                raw_blocks.append({
                    "text":       tbl_md,
                    "page":       page,
                    "section_id": current_section_id,
                    "section_label": current_section_label,
                    "block_type": "table",
                    "table_id":   tbl_id,
                })

                # Đưa vào queue LLM analysis (text-only, không có pil_image)
                if tbl_md.strip() and not tbl_md.startswith("[TABLE_"):
                    visuals_to_process.append({
                        "type":           "table",
                        "id":             tbl_id,
                        "page":           page,
                        "markdown":       tbl_md,
                        "caption":        caption,
                        "context_text":   caption,
                        "raw_blocks_idx": len(raw_blocks) - 1,
                        "self_ref":       table_self_ref,
                    })

            elif item_type == "PictureItem":
                img_idx += 1
                caption = _get_caption(item, doc)
                img_id  = f"img_{page}_{img_idx}"
                image_self_ref = _get_item_self_ref(item)

                pil_img = None
                if not skip_visual_analysis:
                    try:
                        if hasattr(item, "image") and item.image is not None:
                            pil_img = getattr(item.image, "pil_image", None)
                        if pil_img is None and hasattr(item, "get_image"):
                            pil_img = item.get_image(doc)
                    except Exception as e_pic:
                        print(f"[PARSE][WARN] Không lấy được PIL image cho {img_id}: {e_pic}")

                asset_path = _save_pil_asset(pil_img, file_hash, "images", img_id) if pil_img is not None else ""
                images.append({
                    "image_id":          img_id,
                    "page":              page,
                    "caption":           caption,
                    "path":              asset_path,
                    "asset_path":        asset_path,
                    "self_ref":          image_self_ref,
                    "analysis_markdown": "",
                    "pil_image":         pil_img,
                })

                if pil_img is not None:
                    visuals_to_process.append({
                        "type":          "image",
                        "pil_image":     pil_img,
                        "id":            img_id,
                        "page":          page,
                        "caption":       caption or "",
                        "context_text":  "",
                        "figure_number": "",
                        "asset_path":     asset_path,
                        "self_ref":       image_self_ref,
                        "raw_blocks_idx": len(raw_blocks)
                    })
                else:
                    print(f"[PARSE][WARN] {img_id}: khong co PIL image → bo qua Vision API")

            elif item_type == "FormulaItem":
                formula_idx += 1
                formula_id = f"formula_{page}_{formula_idx}"

                pil_img = None if skip_visual_analysis else _get_formula_image(item, page, doc, formula_id=formula_id)
                formula_self_ref = _get_item_self_ref(item)
                asset_path = _save_pil_asset(pil_img, file_hash, "formulas", formula_id) if pil_img is not None else ""

                formulas.append({
                    "formula_id":        formula_id,
                    "latex_string":      f"[Mathematical Formula {formula_idx} - Pending API]",
                    "analysis_markdown": "",
                    "page":              page,
                    "caption":           "",
                    "is_decoded":        False,
                    "self_ref":          formula_self_ref,
                    "asset_path":        asset_path,
                    "pil_image":         pil_img,
                })

                raw_blocks.append({
                    "text":       f"[Mathematical Formula {formula_idx} - Pending API]",
                    "page":       page,
                    "section_id": current_section_id,
                    "section_label": current_section_label,
                    "block_type": "formula",
                    "formula_id": formula_id,
                })

                if pil_img is not None:
                    visuals_to_process.append({
                        "type":         "formula",
                        "pil_image":    pil_img,
                        "id":           formula_id,
                        "page":         page,
                        "context_text": "",  # filled after iterate_items loop
                        "asset_path":    asset_path,
                        "self_ref":      formula_self_ref,
                        "raw_blocks_idx": len(raw_blocks) - 1,
                    })
                else:
                    print(f"[PARSE][WARN] {formula_id}: không crop được ảnh → formula sẽ là Not Decoded")

    except Exception as e:
        print(f"[PARSE][WARN] Lỗi khi duyệt items của {file_path}: {e}")
        try:
            md_text = doc.export_to_markdown()
            if "formula-not-decoded" in md_text:
                md_text = md_text.replace(
                    "<!-- formula-not-decoded -->",
                    "[Mathematical Formula - Not Decoded]",
                )
            raw_blocks = [{"text": md_text, "page": 0, "section_id": "sec_0", "block_type": "text"}]
        except Exception:
            pass

    # ── Fill context_text cho formula và image visuals ────────────────────────────────
    _fill_visual_contexts(raw_blocks, visuals_to_process)

    # ── ASYNC VISION API ────────────────────────────────────────────────────
    if visuals_to_process and not skip_visual_analysis:
        print(
            f"[VISION] Gọi {IMAGE_VLM_MODEL} cho {len(visuals_to_process)} visuals "
            f"({sum(1 for v in visuals_to_process if v['type']=='image')} ảnh + "
            f"{sum(1 for v in visuals_to_process if v['type']=='formula')} công thức + "
            f"{sum(1 for v in visuals_to_process if v['type']=='table')} bảng)..."
        )
        # Event loop fix: luôn dùng thread mới, an toàn với Streamlit/Jupyter
        api_results = _run_async_in_new_loop(asyncio_process_visuals(visuals_to_process))

        # Xóa metadata keys khỏi api_results (không phải formula result)
        api_results.pop("_formula_stats", None)

        # Back-fill formulas — đảm bảo không còn "Pending API" placeholder
        for frm in formulas:
            raw_latex = api_results.get(frm["formula_id"], "")
            frm["analysis_markdown"] = api_results.get(f"_analysis_{frm['formula_id']}", "")
            ensure_analysis_short(frm, "formula")

            frm.pop("pil_image", None)

            if raw_latex and not raw_latex.startswith("["):
                latex = _clean_latex_output(raw_latex)
                if latex and not latex.startswith("[Not Decodable"):
                    frm["latex_string"] = latex
                    frm["is_decoded"]   = True
                else:
                    frm["latex_string"] = "[Not Decodable]"
            else:
                frm["latex_string"] = "[Not Decodable]"

        # Back-fill tables
        tbl_visuals_dict = {v["id"]: v for v in visuals_to_process if v["type"] == "table"}
        for tbl in tables:
            tbl["analysis_markdown"] = api_results.get(tbl["table_id"], "")
            ensure_analysis_short(tbl, "table")
            if tbl["table_id"] in tbl_visuals_dict:
                tbl["context_text"] = tbl_visuals_dict[tbl["table_id"]].get("context_text", tbl.get("context_text", ""))

        # Back-fill images
        img_visuals_dict = {v["id"]: v for v in visuals_to_process if v["type"] == "image"}
        for img in images:
            img["analysis_markdown"] = api_results.get(img["image_id"], "")
            ensure_analysis_short(img, "image")
            # Sync updated caption from late-binding back to the main document
            if img["image_id"] in img_visuals_dict:
                img["caption"] = img_visuals_dict[img["image_id"]].get("caption", img.get("caption", ""))
            img.pop("pil_image", None)

        # Back-fill raw_blocks — O(1) dict lookup (thay O(n*m) loop cũ)
        frm_dict = {f["formula_id"]: f for f in formulas}
        for block in raw_blocks:
            if block.get("block_type") == "formula":
                frm_id = block.get("formula_id")
                if frm_id and frm_id in frm_dict:
                    frm = frm_dict[frm_id]
                    display = (
                        f"${frm['latex_string']}$"
                        if frm["is_decoded"]
                        else frm["latex_string"]
                    )
                    block["text"] = f"Formula: {display}"
    else:
        if visuals_to_process and skip_visual_analysis:
            print(
                f"[VISION] Skip visual analysis for {len(visuals_to_process)} visuals "
                "(only_vector_fast)."
            )
        for img in images:
            img.pop("pil_image", None)
            ensure_analysis_short(img, "image")
        for tbl in tables:
            ensure_analysis_short(tbl, "table")
        for frm in formulas:
            frm.pop("pil_image", None)
            ensure_analysis_short(frm, "formula")
            if "Pending API" in frm.get("latex_string", ""):
                frm["latex_string"] = "[Not Decodable]"

    if not raw_blocks:
        try:
            md_text = doc.export_to_markdown()
            if md_text.strip():
                if "formula-not-decoded" in md_text:
                    md_text = md_text.replace(
                        "<!-- formula-not-decoded -->",
                        "[Mathematical Formula - Not Decoded]",
                    )
                raw_blocks = [{"text": md_text, "page": 0, "section_id": "sec_0", "block_type": "text"}]
        except Exception:
            pass

    if not raw_blocks:
        print(f"[PARSE][WARN] Không extract được nội dung từ {file_path}")
        return None

    if not meta.get("total_pages"):
        pages_seen = {b["page"] for b in raw_blocks}
        meta["total_pages"] = max(pages_seen) if pages_seen else 0

    # Sanity check: pil_image phải đã bị pop
    for img in images:
        assert "pil_image" not in img, f"pil_image chưa được pop khỏi {img.get('image_id')}"
    for frm in formulas:
        assert "pil_image" not in frm, f"pil_image chưa được pop khỏi {frm.get('formula_id')}"

    return ParsedDocument(
        file_path  = file_path,
        file_name  = file_name,
        file_hash  = file_hash,
        doc_type   = doc_type,
        metadata   = meta,
        sections   = sections,
        tables     = tables,
        images     = images,
        formulas   = formulas,
        raw_blocks = raw_blocks,
    ), doc
