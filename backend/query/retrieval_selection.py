from __future__ import annotations

from typing import Any, Dict, List, Tuple


RankedChunk = Tuple[str, Dict[str, Any], float]


def _safe_float(value: float, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp_retrieval_settings(
    qdrant_limit: int | None,
    score_threshold: float | None,
    *,
    min_limit: int = 2,
    max_limit: int = 80,
) -> tuple[int, float]:
    limit = int(qdrant_limit or 30)
    limit = max(min_limit, min(max_limit, limit))

    threshold = _safe_float(score_threshold, 0.58)
    threshold = max(0.0, min(0.9, threshold))
    return limit, threshold


def _source_trace(
    rank: int,
    doc: str,
    meta: Dict[str, Any],
    score: float,
    reason: str,
) -> Dict[str, Any]:
    return {
        "rank": rank,
        "chunk_id": meta.get("chunk_id", ""),
        "file_name": meta.get("file_name", ""),
        "page": meta.get("page", 0),
        "section_label": meta.get("section_label", ""),
        "score": float(score or 0.0),
        "selection_reason": reason,
        "preview": " ".join((doc or "").split())[:360],
    }


def select_retrieval_context(
    raw_docs: List[str],
    raw_metas: List[Dict[str, Any]],
    scores: List[float],
    *,
    score_threshold: float,
    min_chunks: int = 2,
    max_chunks: int = 8,
) -> tuple[List[RankedChunk], Dict[str, Any]]:
    raw = list(zip(raw_docs, raw_metas, scores))
    passed = [
        (doc, meta, score)
        for doc, meta, score in raw
        if float(score or 0.0) >= score_threshold
    ]

    fallback_used = len(passed) < min_chunks
    pool = raw[:min_chunks] if fallback_used else passed
    selected = pool[:max_chunks]
    selected_ids = {id(meta) for _doc, meta, _score in selected}
    filtered_out = [
        _source_trace(rank, doc, meta, score, "below_threshold")
        for rank, (doc, meta, score) in enumerate(raw, start=1)
        if id(meta) not in selected_ids and float(score or 0.0) < score_threshold
    ]

    trace = {
        "score_threshold": score_threshold,
        "min_chunks": min_chunks,
        "max_chunks": max_chunks,
        "raw_retrieved_count": len(raw),
        "passed_threshold_count": len(passed),
        "final_context_count": len(selected),
        "filtered_out_count": len(filtered_out),
        "fallback_used": fallback_used,
        "selected_sources": [
            _source_trace(
                rank,
                doc,
                meta,
                score,
                "fallback_top_raw" if fallback_used else "passed_threshold",
            )
            for rank, (doc, meta, score) in enumerate(selected, start=1)
        ],
        "filtered_out_sources": filtered_out[:24],
    }
    return selected, trace
