"""
ingest/chunker.py — chunk_document(), dedup functions, cross-run dedup helper.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any, Dict, List, Set

from ingest.config import CHUNK_TOKENIZER, CHUNK_MAX_TOKENS, MIN_CHUNK_CHARS
from ingest.analysis import ensure_analysis_short
from ingest.models import ParsedDocument, Chunk
from ingest.parser import normalize_text, detect_language, _post_clean_docling_text


class VisualMappingError(RuntimeError):
    """Raised when a Docling visual item cannot be mapped by stable self_ref."""


def _item_ref(item) -> str:
    try:
        ref = str(getattr(item, "self_ref", "") or "").strip()
        if ref:
            return ref
    except Exception:
        pass
    try:
        return str(item.get_ref().cref).strip()
    except Exception:
        return ""


def _item_page(item) -> int:
    try:
        prov = getattr(item, "prov", None)
        if prov:
            return prov[0].page_no or 0
    except Exception:
        pass
    return 0


def _item_pages(item) -> List[int]:
    pages: List[int] = []
    try:
        for prov in getattr(item, "prov", None) or []:
            page = getattr(prov, "page_no", 0) or 0
            if page > 0:
                pages.append(page)
    except Exception:
        return []
    return list(dict.fromkeys(pages))


def _item_label(item) -> str:
    return str(getattr(item, "label", "") or type(item).__name__).lower()


def _is_table_item(item) -> bool:
    return type(item).__name__ == "TableItem" or "table" in _item_label(item)


def _is_picture_item(item) -> bool:
    return type(item).__name__ == "PictureItem" or _item_label(item) in {"picture", "image"}


def _is_formula_item(item) -> bool:
    return type(item).__name__ == "FormulaItem" or _item_label(item) == "formula"


def _format_table_block(table: Dict[str, Any]) -> str:
    table_id = table.get("table_id", "")
    page = table.get("page", 0)
    caption = table.get("caption", "") or "Not provided"
    markdown = table.get("markdown", "") or "[Table markdown unavailable]"
    summary = ensure_analysis_short(table, "table") or "[Table summary unavailable]"
    return (
        f"[TABLE table_id={table_id} page={page}]\n"
        f"Caption: {caption}\n"
        f"Markdown:\n{markdown}\n\n"
        f"Semantic Summary:\n{summary}\n"
        f"[/TABLE]"
    )


def _format_image_block(image: Dict[str, Any]) -> str:
    image_id = image.get("image_id", "")
    page = image.get("page", 0)
    caption = image.get("caption", "") or "Not provided"
    asset_path = image.get("asset_path") or image.get("path") or ""
    summary = ensure_analysis_short(image, "image") or "[Image summary unavailable]"
    return (
        f"[IMAGE image_id={image_id} page={page}]\n"
        f"Caption: {caption}\n"
        f"Asset Path: {asset_path}\n"
        f"Summary:\n{summary}\n"
        f"[/IMAGE]"
    )


def _format_formula_block(formula: Dict[str, Any]) -> str:
    formula_id = formula.get("formula_id", "")
    page = formula.get("page", 0)
    latex = formula.get("latex_string", "") or "[Not Decodable]"
    summary = ensure_analysis_short(formula, "formula") or "[Formula summary unavailable]"
    return (
        f"[FORMULA formula_id={formula_id} page={page}]\n"
        f"LaTeX:\n{latex}\n\n"
        f"Retrieval Summary:\n{summary}\n"
        f"[/FORMULA]"
    )


def _build_hybrid_chunker():
    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
    import tiktoken

    tokenizer = OpenAITokenizer(
        tokenizer=tiktoken.get_encoding(CHUNK_TOKENIZER),
        max_tokens=CHUNK_MAX_TOKENS,
    )
    return HybridChunker(
        tokenizer=tokenizer,
        max_tokens=CHUNK_MAX_TOKENS,
        merge_peers=True,
    )


@lru_cache(maxsize=1)
def _get_tokenizer():
    import tiktoken

    return tiktoken.get_encoding(CHUNK_TOKENIZER)


def _token_len(text: str) -> int:
    try:
        return len(_get_tokenizer().encode(text or ""))
    except Exception:
        return max(1, len(text or "") // 4)


def _match_visual_by_ref(
    item: Any,
    by_ref: Dict[str, Dict],
    visual_type: str,
    chunk_index: int,
    page: int,
) -> Dict[str, Any]:
    ref = _item_ref(item)
    if not ref:
        raise VisualMappingError(
            f"Missing self_ref for {visual_type} in chunk={chunk_index}, page={page}"
        )
    if ref not in by_ref:
        raise VisualMappingError(
            f"No parsed {visual_type} found for self_ref={ref}, chunk={chunk_index}, page={page}"
        )
    return by_ref[ref]


def _visual_ref(visual_type: str, visual: Dict[str, Any]) -> Dict[str, Any]:
    visual_id = (
        visual.get("table_id")
        or visual.get("image_id")
        or visual.get("formula_id")
        or ""
    )
    path = visual.get("asset_path") or visual.get("path") or ""
    return {
        "type": visual_type,
        "id": visual_id,
        "self_ref": visual.get("self_ref", ""),
        "page": visual.get("page", 0),
        "path": path,
    }


def _add_visual_asset(visual_assets: List[Dict[str, Any]], visual_type: str, visual: Dict[str, Any]) -> None:
    path = visual.get("asset_path") or visual.get("path") or ""
    if not path:
        return
    visual_id = visual.get("image_id") or visual.get("formula_id") or visual.get("table_id", "")
    visual_assets.append({
        "type": visual_type,
        "id": visual_id,
        "path": path,
        "page": visual.get("page", 0),
    })


def _candidate_pages(doc_items: List[Any]) -> List[int]:
    pages: List[int] = []
    for item in doc_items:
        pages.extend(_item_pages(item))
    return list(dict.fromkeys(page for page in pages if page > 0))


def _prefix_phrases(text: str) -> List[str]:
    words = normalize_text(text).split()
    phrases: List[str] = []
    for length in (80, 50, 25, 12):
        if len(words) >= length:
            phrases.append(" ".join(words[:length]))
    if words:
        phrases.append(" ".join(words[: min(len(words), 8)]))
    return list(dict.fromkeys(phrase for phrase in phrases if len(phrase) >= 40))


def _resolve_page_from_pdf(text: str, file_path: str, candidate_pages: List[int]) -> int:
    if not text.strip() or not file_path:
        return 0

    try:
        import fitz

        doc = fitz.open(file_path)
    except Exception:
        return 0

    try:
        page_numbers = candidate_pages or list(range(1, len(doc) + 1))
        phrases = _prefix_phrases(text)
        for page_no in page_numbers:
            if page_no < 1 or page_no > len(doc):
                continue
            page_text = normalize_text(doc[page_no - 1].get_text("text"))
            if any(phrase in page_text for phrase in phrases):
                return page_no
    finally:
        doc.close()
    return 0


def _resolve_page_from_raw_blocks(text: str, raw_blocks: List[Dict[str, Any]]) -> int:
    norm_text = normalize_text(text)
    if not norm_text:
        return 0

    for block in raw_blocks:
        block_text = normalize_text(str(block.get("text", "") or ""))
        if not block_text:
            continue
        probe = block_text[: min(len(block_text), 160)]
        reverse_probe = norm_text[: min(len(norm_text), 160)]
        if probe in norm_text or reverse_probe in block_text:
            page = int(block.get("page", 0) or 0)
            if page > 0:
                return page
    return 0


def _resolve_text_page(
    text: str,
    fallback_page: int,
    doc_items: List[Any],
    parsed_doc: ParsedDocument,
) -> int:
    candidate_pages = _candidate_pages(doc_items)
    pdf_page = _resolve_page_from_pdf(text, parsed_doc.file_path, candidate_pages)
    if pdf_page:
        return pdf_page

    raw_block_page = _resolve_page_from_raw_blocks(text, parsed_doc.raw_blocks)
    if raw_block_page:
        return raw_block_page

    return fallback_page


def _resolve_chunk_page(page: int, visual_refs: List[Dict[str, Any]]) -> int:
    """Prefer visual provenance when Docling reports a stale page for visual chunks."""
    if not visual_refs:
        return page

    visual_pages = [
        ref.get("page", 0)
        for ref in visual_refs
        if isinstance(ref.get("page", 0), int) and ref.get("page", 0) > 0
    ]
    if not visual_pages:
        return page

    unique_pages = sorted(set(visual_pages))
    if page in unique_pages:
        return page
    if len(unique_pages) == 1:
        return unique_pages[0]
    return page


def _combine_text_with_visual_blocks(base_text: str, visual_blocks: List[str]) -> List[str]:
    base_text = _post_clean_docling_text(base_text)
    visual_blocks = [_post_clean_docling_text(block) for block in visual_blocks if block.strip()]
    if not visual_blocks:
        return [base_text] if base_text.strip() else []

    visual_text = "VISUAL ENRICHMENT:\n" + "\n\n".join(visual_blocks)
    if not base_text.strip():
        return [visual_text]

    combined = f"{base_text}\n\n{visual_text}"
    if _token_len(combined) <= CHUNK_MAX_TOKENS:
        return [combined]
    return [base_text, visual_text]


def _make_chunk(
    text: str,
    parsed_doc: ParsedDocument,
    title: str,
    page: int,
    section_label: str,
    chunk_index: int,
    workspace_id: str = "default",
    table_refs: List[str] | None = None,
    image_refs: List[str] | None = None,
    formula_refs: List[str] | None = None,
    visual_assets: List[Dict[str, Any]] | None = None,
    visual_refs: List[Dict[str, Any]] | None = None,
    table_markdowns: Dict[str, str] | None = None,
    formula_latex: Dict[str, str] | None = None,
) -> Chunk:
    table_refs = list(dict.fromkeys(table_refs or []))
    image_refs = list(dict.fromkeys(image_refs or []))
    formula_refs = list(dict.fromkeys(formula_refs or []))
    visual_refs = visual_refs or []
    resolved_page = _resolve_chunk_page(page, visual_refs)
    chunk_key = f"{workspace_id}:{parsed_doc.file_hash}:{chunk_index}:{text}"
    return Chunk(
        text=text,
        chunk_id=hashlib.sha256(chunk_key.encode()).hexdigest()[:32],
        source_file=parsed_doc.file_name,
        file_hash=parsed_doc.file_hash,
        page=resolved_page,
        section_label=section_label,
        chunk_index=chunk_index,
        total_chunks=0,
        has_table=bool(table_refs),
        table_refs=table_refs,
        image_refs=image_refs,
        has_image=bool(image_refs),
        has_formula=bool(formula_refs),
        formula_refs=formula_refs,
        doc_type=parsed_doc.doc_type,
        title=title,
        language=detect_language(text),
        workspace_id=workspace_id,
        visual_assets=visual_assets or [],
        visual_refs=visual_refs,
        table_markdowns=table_markdowns or {},
        formula_latex=formula_latex or {},
    )


def chunk_document(
    parsed_doc: ParsedDocument,
    doc_obj=None,
    workspace_id: str = "default",
    include_image_formula_visuals: bool = True,
) -> List[Chunk]:
    if doc_obj is None:
        raise ValueError(f"[CHUNK][ERROR] doc_obj bắt buộc: {parsed_doc.file_name}")

    print(f"[CHUNK] Đang dùng IBM HybridChunker cho: {parsed_doc.file_name}")
    title = parsed_doc.metadata.get("title", parsed_doc.file_name)

    # ── BƯỚC 1: Chunk ────────────────────────────────────────────────────────
    chunker = _build_hybrid_chunker()
    raw_chunks = list(chunker.chunk(doc_obj))
    print(f"[CHUNK] HybridChunker tạo ra {len(raw_chunks)} raw chunks")

    # ── BƯỚC 2: Build ref maps từ parsed_doc ────────────────────────────────
    table_by_ref: Dict[str, Dict] = {}
    for table in parsed_doc.tables:
        if table.get("self_ref"):
            table_by_ref[table["self_ref"]] = table

    image_by_ref: Dict[str, Dict] = {}
    for image in parsed_doc.images:
        if image.get("self_ref"):
            image_by_ref[image["self_ref"]] = image

    formula_by_ref: Dict[str, Dict] = {}
    for formula in parsed_doc.formulas:
        if formula.get("self_ref"):
            formula_by_ref[formula["self_ref"]] = formula

    print(
        f"[CHUNK] Ref map — tables={len(parsed_doc.tables)} | "
        f"images={len(parsed_doc.images)} | formulas={len(parsed_doc.formulas)}"
    )

    # ── BƯỚC 3: Build chunks ──────────────────────────────────────────────────
    chunks: List[Chunk] = []
    used_visual_ids: Set[str] = set()

    for idx, rc in enumerate(raw_chunks):
        text = getattr(rc, "text", "") or ""
        page          = 0
        section_label = "general"
        t_ref: List[str] = []
        i_ref: List[str] = []
        f_ref: List[str] = []
        visual_assets: List[Dict[str, Any]] = []
        visual_refs: List[Dict[str, Any]] = []
        table_markdowns: Dict[str, str] = {}
        formula_latex: Dict[str, str] = {}

        if rc.meta and hasattr(rc.meta, "doc_items") and rc.meta.doc_items:
            doc_items = list(rc.meta.doc_items)
            first = doc_items[0]
            prov  = getattr(first, "prov", None)
            if prov:
                page = prov[0].page_no or 0

            headings = getattr(rc.meta, "headings", None) or []
            if headings:
                section_label = headings[-1]

            has_visual_items = any(
                _is_table_item(item) or _is_picture_item(item) or _is_formula_item(item)
                for item in rc.meta.doc_items
            )

            if has_visual_items:
                parts: List[str] = []
                seen_visual_refs: Set[str] = set()
                visual_blocks: List[str] = []
                for chunk_item in doc_items:
                    if _is_table_item(chunk_item):
                        table = _match_visual_by_ref(chunk_item, table_by_ref, "table", idx, page)
                        table_id = table["table_id"]
                        if table_id not in seen_visual_refs:
                            visual_blocks.append(_format_table_block(table))
                            seen_visual_refs.add(table_id)
                        t_ref.append(table_id)
                        table_markdowns[table_id] = table.get("markdown", "")
                        visual_refs.append(_visual_ref("table", table))
                        used_visual_ids.add(table_id)
                        continue

                    if _is_picture_item(chunk_item):
                        if not include_image_formula_visuals:
                            continue
                        image = _match_visual_by_ref(chunk_item, image_by_ref, "image", idx, page)
                        image_id = image["image_id"]
                        if image_id not in seen_visual_refs:
                            visual_blocks.append(_format_image_block(image))
                            seen_visual_refs.add(image_id)
                        i_ref.append(image_id)
                        visual_refs.append(_visual_ref("image", image))
                        _add_visual_asset(visual_assets, "image", image)
                        used_visual_ids.add(image_id)
                        continue

                    if _is_formula_item(chunk_item):
                        if not include_image_formula_visuals:
                            item_text = getattr(chunk_item, "text", "") or ""
                            if item_text.strip():
                                parts.append(_post_clean_docling_text(item_text))
                            continue
                        formula = _match_visual_by_ref(chunk_item, formula_by_ref, "formula", idx, page)
                        formula_id = formula["formula_id"]
                        if formula_id not in seen_visual_refs:
                            visual_blocks.append(_format_formula_block(formula))
                            seen_visual_refs.add(formula_id)
                        f_ref.append(formula_id)
                        formula_latex[formula_id] = formula.get("latex_string", "")
                        visual_refs.append(_visual_ref("formula", formula))
                        _add_visual_asset(visual_assets, "formula", formula)
                        used_visual_ids.add(formula_id)
                        continue

                    item_text = getattr(chunk_item, "text", "") or ""
                    if item_text.strip():
                        parts.append(_post_clean_docling_text(item_text))

                raw_text = text
                text_parts = [raw_text] if raw_text.strip() else parts
                text = "\n\n".join(part for part in text_parts if part.strip())
                split_texts = _combine_text_with_visual_blocks(text, visual_blocks)
            else:
                split_texts = [text]
            page = _resolve_text_page(text, page, doc_items, parsed_doc)
        else:
            split_texts = [text]

        cleaned_texts = []
        for chunk_text in split_texts:
            chunk_text = _post_clean_docling_text(chunk_text)
            chunk_text = chunk_text.replace("<!-- formula-not-decoded -->", "[Mathematical Formula - Not Decodable]")
            if len(chunk_text.strip()) >= MIN_CHUNK_CHARS:
                cleaned_texts.append(chunk_text)

        if not cleaned_texts:
            continue

        for chunk_text in cleaned_texts:
            chunks.append(_make_chunk(
                text=chunk_text,
                parsed_doc=parsed_doc,
                title=title,
                page=page,
                section_label=section_label,
                chunk_index=len(chunks),
                workspace_id=workspace_id,
                table_refs=t_ref,
                image_refs=i_ref,
                formula_refs=f_ref,
                visual_assets=visual_assets,
                visual_refs=visual_refs,
                table_markdowns=table_markdowns,
                formula_latex=formula_latex,
            ))

    # Some Docling versions do not emit PictureItem chunks. Add standalone
    # visual chunks for parsed visuals that were not referenced by raw chunks.
    for visual_type, items, id_key, formatter in (
        ("table", parsed_doc.tables, "table_id", _format_table_block),
        ("image", parsed_doc.images, "image_id", _format_image_block),
        ("formula", parsed_doc.formulas, "formula_id", _format_formula_block),
    ):
        if visual_type in {"image", "formula"} and not include_image_formula_visuals:
            continue
        for visual in items:
            visual_id = visual.get(id_key, "")
            if not visual_id or visual_id in used_visual_ids:
                continue
            text = _post_clean_docling_text(formatter(visual))
            if len(text.strip()) < MIN_CHUNK_CHARS:
                continue
            visual_assets = []
            _add_visual_asset(visual_assets, visual_type, visual)
            chunks.append(_make_chunk(
                text=text,
                parsed_doc=parsed_doc,
                title=title,
                page=visual.get("page", 0),
                section_label=f"visual:{visual_type}",
                chunk_index=len(chunks),
                workspace_id=workspace_id,
                table_refs=[visual_id] if visual_type == "table" else [],
                image_refs=[visual_id] if visual_type == "image" else [],
                formula_refs=[visual_id] if visual_type == "formula" else [],
                visual_assets=visual_assets,
                visual_refs=[_visual_ref(visual_type, visual)],
                table_markdowns={visual_id: visual.get("markdown", "")} if visual_type == "table" else {},
                formula_latex={visual_id: visual.get("latex_string", "")} if visual_type == "formula" else {},
            ))

    final_count = len(chunks)
    for i, c in enumerate(chunks):
        c.chunk_index  = i
        c.total_chunks = final_count

    table_chunks   = sum(1 for c in chunks if c.has_table)
    formula_chunks = sum(1 for c in chunks if c.has_formula)
    print(f"[CHUNK] Hoàn tất: {final_count} chunks | có table: {table_chunks} | có formula: {formula_chunks}")

    return chunks


# ── Dedup functions ───────────────────────────────────────────────────────────

def dedup_exact(chunks: List[Chunk]) -> List[Chunk]:
    """Exact dedup bằng SHA256 của normalized text."""
    seen: Set[str] = set()
    result: List[Chunk] = []
    for chunk in chunks:
        norm = normalize_text(chunk.text)
        h    = hashlib.sha256(norm.encode()).hexdigest()
        if h not in seen and len(norm) >= MIN_CHUNK_CHARS:
            seen.add(h)
            result.append(chunk)
    return result


def dedup_near(chunks: List[Chunk], prefix_words: int = 30) -> List[Chunk]:
    """Near-dedup theo 30 từ đầu của normalized text."""
    seen: Set[str] = set()
    result: List[Chunk] = []
    for chunk in chunks:
        norm   = normalize_text(chunk.text)
        prefix = " ".join(norm.split()[:prefix_words])
        ph     = hashlib.sha256(prefix.encode()).hexdigest()
        if ph not in seen:
            seen.add(ph)
            result.append(chunk)
    return result


def dedup_chunks(chunks: List[Chunk]) -> List[Chunk]:
    """Chạy cả 2 tầng dedup."""
    before = len(chunks)
    chunks = dedup_exact(chunks)
    chunks = dedup_near(chunks)
    after  = len(chunks)
    print(f"[DEDUP] {before} → {after} chunks (bỏ {before - after} duplicate)")
    return chunks
