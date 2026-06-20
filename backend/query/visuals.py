"""
Conditional retrieval of full visual analyses from rag_visuals.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Tuple


_VISUAL_KEYWORDS = (
    "table", "bảng", "row", "column", "metric", "so sánh", "số liệu",
    "figure", "fig.", "fig ", "hình", "image", "ảnh", "chart", "graph", "plot",
    "diagram", "sơ đồ", "trục", "axis", "legend",
    "formula", "equation", "công thức", "phương trình", "latex", "biến số",
    "latency", "power", "accuracy", "loss",
)

_VISUAL_REFERENCE_RE = re.compile(
    r"\b(?:fig(?:ure)?|hinh|hình|table|bang|bảng|eq(?:uation)?|formula|cong\s*thuc|"
    r"công\s*thức|phuong\s*trinh|phương\s*trình)\s*[\.:#-]?\s*\(?\d+",
    re.IGNORECASE,
)

_VISUAL_ID_RE = re.compile(r"\b(?:img|image|table|formula)_\d+_\d+\b", re.IGNORECASE)

_GRAPH_REASONING_KEYWORDS = (
    "why", "how", "compare", "comparison", "relationship", "relate", "depends",
    "cause", "effect", "impact", "improve", "reduce", "increase", "decrease",
    "vì sao", "tại sao", "như thế nào", "so sánh", "quan hệ", "liên hệ",
    "phụ thuộc", "nguyên nhân", "ảnh hưởng", "cải thiện", "làm tăng", "làm giảm",
)


def should_fetch_full_visual_context(
    question: str,
    ranked_results: List[Tuple[str, Dict, float]],
) -> bool:
    """Return True only for questions that likely need detailed visual evidence."""
    if not collect_visual_ids(ranked_results):
        return False
    q = (question or "").lower()
    return _has_visual_intent(q)


def should_skip_kg_for_visual_question(
    question: str,
    ranked_results: List[Tuple[str, Dict, float]],
) -> bool:
    """Skip graph traversal for direct figure/table/equation inspection questions."""
    if not should_fetch_full_visual_context(question, ranked_results):
        return False
    q = (question or "").lower()
    return not any(keyword in q for keyword in _GRAPH_REASONING_KEYWORDS)


def _has_visual_intent(question: str) -> bool:
    if any(keyword in question for keyword in _VISUAL_KEYWORDS):
        return True
    if _VISUAL_ID_RE.search(question):
        return True
    return bool(_VISUAL_REFERENCE_RE.search(question))


def collect_visual_ids(
    ranked_results: List[Tuple[str, Dict, float]],
    limit: int = 3,
) -> List[str]:
    """Collect visual IDs from ranked chunk metadata, preserving result order."""
    ids: List[str] = []
    for _, meta, _ in ranked_results:
        for visual in _loads_json(meta.get("visual_refs", "[]")):
            if isinstance(visual, dict):
                _append_unique(ids, str(visual.get("id", "")).strip(), limit)
        for key in ("table_refs", "image_refs", "formula_refs"):
            for visual_id in _loads_json(meta.get(key, "[]")):
                _append_unique(ids, str(visual_id).strip(), limit)
        if len(ids) >= limit:
            break
    return ids


def retrieve_full_visual_context(
    question: str,
    ranked_results: List[Tuple[str, Dict, float]],
    max_visuals: int = 3,
    workspace_id: str | None = None,
) -> str:
    """Fetch full visual analyses by ID from rag_visuals when the query needs them."""
    if not should_fetch_full_visual_context(question, ranked_results):
        return ""

    visual_ids = collect_visual_ids(ranked_results, limit=max_visuals)
    if not visual_ids:
        return ""

    try:
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue
        from query.clients import get_collection

        must = [FieldCondition(key="visual_id", match=MatchAny(any=visual_ids))]
        if workspace_id:
            must.append(FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id)))

        client, col_name = get_collection("rag_visuals")
        records, _ = client.scroll(
            collection_name=col_name,
            scroll_filter=Filter(must=must),
            with_payload=True,
            with_vectors=False,
            limit=max_visuals,
        )
    except Exception as exc:
        print(f"[VISUALS][WARN] Không lấy được full visual context: {exc}")
        return ""

    by_id = {r.payload.get("visual_id", ""): r.payload for r in records}
    parts = []
    for visual_id in visual_ids:
        payload = by_id.get(visual_id)
        if not payload:
            continue
        header = (
            f"[{payload.get('visual_type', 'visual')} {visual_id} | "
            f"Trang {payload.get('page', '?')} | "
            f"Source: {payload.get('file_name', '')}]"
        )
        full = payload.get("analysis_full") or payload.get("analysis_short") or ""
        raw = payload.get("raw_content") or ""
        raw_block = f"\n\nRaw Content:\n{raw}" if raw else ""
        parts.append(f"{header}\n{full}{raw_block}")
    return "\n\n---\n\n".join(parts)


def _loads_json(value) -> list:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, list) else []
    except Exception:
        return []


def _append_unique(ids: List[str], visual_id: str, limit: int) -> None:
    if not visual_id or visual_id in ids or len(ids) >= limit:
        return
    ids.append(visual_id)
