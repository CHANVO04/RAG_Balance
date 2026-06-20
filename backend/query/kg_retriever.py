from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional
import unicodedata

try:
    from kg_neo4j_config import anchored_kg_context_cypher
    from kg_neo4j_manager import get_neo4j_manager
    from query.config import (
        KG_ENTITY_EXPANSION_HOPS,
        KG_MAX_ANCHORED_RELATIONS,
        KG_MIN_RELATION_CONFIDENCE,
    )
    HAS_KG = True
except ImportError:
    HAS_KG = False
    print("[WARN] Không tìm thấy kg_neo4j.py. Hệ thống sẽ bỏ qua Knowledge Graph.")


def lookup_kg_context(*_args, **_kwargs):
    """Deprecated query-time lookup hook kept only so old tests can assert it is unused."""
    raise RuntimeError("query-time KG lookup is disabled; use chunk-anchored retrieval")


@dataclass
class KGSearchResult:
    context: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    unavailable_reason: str = ""
    trace: Dict[str, Any] = field(default_factory=dict)


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        return dict(value)
    except Exception:
        return {}


def _record_get(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(key, default)
    try:
        return record[key]
    except Exception:
        return getattr(record, key, default)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _first(values: List[Any], default: Any = "") -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return default


def _safe_graph_id_part(value: Any) -> str:
    value = unicodedata.normalize("NFKC", str(value or "").strip())
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^A-Za-z0-9_.:-]", "", value)
    return value or "unknown"


def _graph_edge_id(source_id: str, relation: str, target_id: str) -> str:
    """Match graph visualization edge ids so citations can focus relationships."""
    return "::".join([
        _safe_graph_id_part(source_id),
        "edge",
        _safe_graph_id_part(relation),
        _safe_graph_id_part(target_id),
    ])


def _edge_from_record(record: Any) -> Dict[str, Any]:
    source = _as_dict(_record_get(record, "source"))
    relationship = _as_dict(_record_get(record, "relationship"))
    target = _as_dict(_record_get(record, "target"))

    source_files = _as_list(relationship.get("source_files"))
    pages = _as_list(relationship.get("pages"))
    chunk_ids = [str(item) for item in _as_list(relationship.get("chunk_ids")) if item]
    visual_ids = [str(item) for item in _as_list(relationship.get("visual_ids")) if item]

    relation = relationship.get("relation") or relationship.get("type") or "RELATES_TO"
    source_id = source.get("id") or ""
    target_id = target.get("id") or ""

    return {
        "subject": source.get("label") or source.get("name") or source.get("id") or "",
        "relation": relation,
        "object": target.get("label") or target.get("name") or target.get("id") or "",
        "source_id": source_id,
        "target_id": target_id,
        "edge_id": _graph_edge_id(source_id, relation, target_id),
        "source_files": source_files,
        "pages": pages,
        "chunk_ids": chunk_ids,
        "visual_ids": visual_ids,
        "file_name": _first(source_files),
        "page": _first(pages, None),
        "chunk_id": _first(chunk_ids),
        "evidence_preview": relationship.get("evidence_preview") or "",
        "confidence": float(relationship.get("confidence") or 0.0),
        "weight": float(relationship.get("weight") or 0.0),
        "distance": int(_record_get(record, "distance", 99) or 99),
    }


def _edge_key(edge: Dict[str, Any]) -> tuple:
    return (
        edge.get("source_id", ""),
        edge.get("relation", ""),
        edge.get("target_id", ""),
    )


def _merge_unique(left: List[Any], right: List[Any]) -> List[Any]:
    merged: List[Any] = []
    for value in [*left, *right]:
        if value not in (None, "") and value not in merged:
            merged.append(value)
    return merged


def _dedupe_graph_edges(edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[tuple, Dict[str, Any]] = {}
    for edge in edges:
        key = _edge_key(edge)
        current = deduped.get(key)
        if current is None:
            deduped[key] = dict(edge)
            continue

        current["source_files"] = _merge_unique(current.get("source_files", []), edge.get("source_files", []))
        current["pages"] = _merge_unique(current.get("pages", []), edge.get("pages", []))
        current["chunk_ids"] = _merge_unique(current.get("chunk_ids", []), edge.get("chunk_ids", []))
        current["visual_ids"] = _merge_unique(current.get("visual_ids", []), edge.get("visual_ids", []))
        current["weight"] = max(float(current.get("weight") or 0), float(edge.get("weight") or 0))
        current["confidence"] = max(float(current.get("confidence") or 0), float(edge.get("confidence") or 0))
        if int(edge.get("distance") or 99) < int(current.get("distance") or 99):
            current["distance"] = edge.get("distance")
            current["evidence_preview"] = edge.get("evidence_preview") or current.get("evidence_preview", "")

    return list(deduped.values())


def _rank_graph_edges(edges, chunk_ids, seed_entity_ids, visual_intent, limit):
    chunk_id_set = set(chunk_ids or [])

    def score(edge):
        overlap = bool(chunk_id_set.intersection(edge.get("chunk_ids") or []))
        seed_connection = (
            edge.get("source_id") in seed_entity_ids
            and edge.get("target_id") in seed_entity_ids
        )
        visual_boost = visual_intent and bool(edge.get("visual_ids"))
        return (
            1 if overlap else 0,
            1 if seed_connection else 0,
            float(edge.get("weight") or 0),
            float(edge.get("confidence") or 0),
            1 if visual_boost else 0,
            -int(edge.get("distance") or 99),
        )

    return sorted(edges, key=score, reverse=True)[:limit]


def _format_graph_context(edges) -> str:
    lines = []
    for index, edge in enumerate(edges, start=1):
        chunk_id = (edge.get("chunk_ids") or [edge.get("chunk_id", "") or ""])[0]
        citation = edge.get("citation") or edge.get("citation_id") or f"KG{index}"
        page = edge.get("page") if edge.get("page") is not None else "?"
        lines.append(
            f"[KG-{index:02d}] {edge.get('subject')} --{edge.get('relation')}--> {edge.get('object')}\n"
            f"Evidence anchor: {edge.get('file_name')}, page {page}, chunk_id={chunk_id}, citation=[{citation}]\n"
            f"Evidence preview: \"{edge.get('evidence_preview', '')}\""
        )
    return "\n\n".join(lines)


def _source_from_edge(index: int, edge: Dict[str, Any]) -> Dict[str, Any]:
    source_id = f"KG-{index:02d}"
    chunk_id = (edge.get("chunk_ids") or [edge.get("chunk_id", "") or ""])[0]
    return {
        "id": source_id,
        "citation_id": source_id,
        "subject": edge.get("subject", ""),
        "relation": edge.get("relation", ""),
        "object": edge.get("object", ""),
        "subject_id": edge.get("source_id", ""),
        "object_id": edge.get("target_id", ""),
        "edge_id": edge.get("edge_id", ""),
        "source_file": edge.get("file_name", ""),
        "file_name": edge.get("file_name", ""),
        "page": edge.get("page"),
        "chunk_id": chunk_id,
        "chunk_ids": edge.get("chunk_ids", []),
        "visual_ids": edge.get("visual_ids", []),
        "citation": edge.get("citation", ""),
        "evidence_preview": edge.get("evidence_preview", ""),
        "confidence": edge.get("confidence", 0.0),
        "weight": edge.get("weight", 0.0),
        "distance": edge.get("distance", 99),
        "has_document_evidence": bool(edge.get("file_name") and chunk_id),
    }


def retrieve_kg(
    question: str,
    kg_mode: str = "default",
    workspace_id: str = "default",
    selected_files: Optional[List[str]] = None,
    chunk_ids: Optional[List[str]] = None,
    visual_intent: bool = False,
    chunk_citations: Optional[Dict[str, str]] = None,
) -> KGSearchResult:
    if not HAS_KG:
        return KGSearchResult(
            unavailable_reason="kg_module_missing",
            trace={"kg_mode": kg_mode, "reason": "kg_module_missing"},
        )

    if kg_mode != "default":
        return KGSearchResult(
            unavailable_reason="kg_disabled",
            trace={"kg_mode": kg_mode, "reason": "kg_disabled"},
        )

    normalized_chunk_ids = [str(chunk_id) for chunk_id in (chunk_ids or []) if chunk_id]
    if not normalized_chunk_ids:
        return KGSearchResult(
            unavailable_reason="no_chunk_anchors",
            trace={"kg_mode": kg_mode, "reason": "no_chunk_anchors"},
        )

    print("[KG] Đang truy xuất đồ thị từ Qdrant chunk anchors...")
    try:
        query = anchored_kg_context_cypher(KG_ENTITY_EXPANSION_HOPS)
        with get_neo4j_manager().session() as session:
            records = list(session.run(
                query,
                {"workspace_id": workspace_id, "chunk_ids": normalized_chunk_ids},
            ))

        traversed_count = len(records)
        selected_file_set = set(selected_files or [])
        edges = _dedupe_graph_edges([_edge_from_record(record) for record in records])
        if selected_file_set:
            edges = [
                edge for edge in edges
                if selected_file_set.intersection(edge.get("source_files") or [])
            ]
        edges = [
            edge for edge in edges
            if float(edge.get("confidence") or 0.0) >= KG_MIN_RELATION_CONFIDENCE
        ]
        seed_entity_ids = {
            _record_get(record, "seed_id")
            for record in records
            if _record_get(record, "seed_id")
        }
        ranked_edges = _rank_graph_edges(
            edges,
            normalized_chunk_ids,
            seed_entity_ids,
            visual_intent,
            KG_MAX_ANCHORED_RELATIONS,
        )

        chunk_citations = chunk_citations or {}
        for edge in ranked_edges:
            anchor_chunk_id = edge.get("chunk_id") or _first(edge.get("chunk_ids", []))
            edge["citation"] = chunk_citations.get(str(anchor_chunk_id), "")

        kg_sources = [_source_from_edge(index, edge) for index, edge in enumerate(ranked_edges, start=1)]
        trace = {
            "kg_mode": kg_mode,
            "graph_relationships_traversed": traversed_count,
            "graph_relationships_used_in_prompt": len(ranked_edges),
        }
        if ranked_edges:
            print("[KG] Tìm thấy graph context từ chunk anchors.")
        else:
            print("[KG] Không có quan hệ graph phù hợp với chunk anchors.")
        return KGSearchResult(
            context=_format_graph_context(ranked_edges),
            sources=kg_sources,
            trace=trace,
        )
    except Exception as e:
        print(f"[KG][ERROR] {e}")
        return KGSearchResult(
            unavailable_reason=str(e),
            trace={"kg_mode": kg_mode, "reason": str(e)},
        )
