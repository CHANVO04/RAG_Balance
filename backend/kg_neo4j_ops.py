"""
kg_neo4j_ops.py — Graph operations: delete_document_kg, upsert_visual_nodes, get_graph_for_viz.
Split from kg_neo4j.py (God Module refactor). kg_neo4j.py remains as backward-compat facade.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List

from kg_neo4j_config import (
    DELETE_EDGES_CYPHER, REMOVE_DOCUMENT_FROM_EDGES_CYPHER, DELETE_ORPHANS_CYPHER,
    DELETE_VISUAL_CYPHER, DELETE_DOCUMENT_CYPHER, DELETE_DOCUMENT_GRAPH_CYPHER,
    GET_ENTITY_GRAPH_VIZ_BY_SOURCE_CYPHER, GET_ENTITY_GRAPH_VIZ_CYPHER,
    GET_GRAPH_WITH_CHUNKS_VIZ_CYPHER,
    UPSERT_CHUNK_CYPHER, UPSERT_DOCUMENT_CYPHER, UPSERT_ENTITY_RELATION_CYPHER,
    UPSERT_FORMULA_CYPHER, UPSERT_IMAGE_CYPHER,
)
from kg_neo4j_manager import get_neo4j_manager
from kg_scientific_schema import (
    canonical_entity_key,
    normalize_entity_label,
    normalize_entity_type,
    normalize_relation_name,
)


def _safe_graph_id_part(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "").strip())
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^A-Za-z0-9_.:-]", "", value)
    return value or "unknown"


def _document_node_id(workspace_id: str, file_name: str) -> str:
    return f"{_safe_graph_id_part(workspace_id)}::document::{_safe_graph_id_part(file_name)}"


def _chunk_node_id(workspace_id: str, chunk_id: str) -> str:
    return f"{_safe_graph_id_part(workspace_id)}::chunk::{_safe_graph_id_part(chunk_id)}"


def _entity_id(workspace_id: str, canonical_key: str) -> str:
    return f"{_safe_graph_id_part(workspace_id)}::entity::{_safe_graph_id_part(canonical_key)}"


def _formula_node_id(workspace_id: str, formula_id: str) -> str:
    return f"{_safe_graph_id_part(workspace_id)}::formula::{_safe_graph_id_part(formula_id)}"


def _image_node_id(workspace_id: str, image_id: str) -> str:
    return f"{_safe_graph_id_part(workspace_id)}::image::{_safe_graph_id_part(image_id)}"


def _visual_page(item: Dict[str, Any]) -> int:
    return int(item.get("page") or item.get("page_number") or 0)


def _record_value(record: Any, key: str, default: Any = None) -> Any:
    try:
        value = record[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first_item(value: Any, default: Any = None) -> Any:
    items = _as_list(value)
    return items[0] if items else default


def _edge_id(from_id: str, relation: str, to_id: str) -> str:
    return "::".join([
        _safe_graph_id_part(from_id),
        "edge",
        _safe_graph_id_part(relation),
        _safe_graph_id_part(to_id),
    ])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chunk_preview(text: str, limit: int = 220) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _node_payload(
    node_id: str,
    label: str,
    node_type: str,
    mentions: int,
    source_files: Any,
    pages: Any,
) -> Dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "type": node_type or "Concept",
        "mentions": mentions or 1,
        "source_files": _as_list(source_files),
        "pages": _as_list(pages),
    }


def upsert_hybrid_chunk_graph(
    session,
    chunks,
    triplets,
    file_name: str,
    workspace_id: str,
    file_hash: str = "",
    total_pages: int = 0,
) -> int:
    now = _now_iso()
    workspace_id = workspace_id or "default"
    document_id = _document_node_id(workspace_id, file_name)
    session.run(
        UPSERT_DOCUMENT_CYPHER,
        id=document_id,
        label=file_name,
        workspace_id=workspace_id,
        file_name=file_name,
        file_hash=file_hash,
        total_pages=total_pages,
        created_at=now,
        updated_at=now,
    )

    chunk_by_id: Dict[str, Any] = {}
    for chunk in chunks:
        chunk_id = str(getattr(chunk, "chunk_id", "") or "")
        if not chunk_id:
            continue
        chunk_by_id[chunk_id] = chunk
        session.run(
            UPSERT_CHUNK_CYPHER,
            id=_chunk_node_id(workspace_id, chunk_id),
            document_id=document_id,
            workspace_id=workspace_id,
            chunk_id=chunk_id,
            file_name=file_name,
            page=getattr(chunk, "page", None),
            section_label=getattr(chunk, "section_label", ""),
            content_type=getattr(chunk, "content_type", "text"),
            text_preview=_chunk_preview(getattr(chunk, "text", "")),
            tokens=int(getattr(chunk, "tokens", 0) or 0),
            has_table=bool(getattr(chunk, "has_table", False)),
            has_formula=bool(getattr(chunk, "has_formula", False)),
            has_image=bool(getattr(chunk, "has_image", False)),
            created_at=now,
            updated_at=now,
        )

    written = 0
    for triplet in triplets:
        chunk_id = str(triplet.chunk_id or "")
        if not chunk_id or chunk_id not in chunk_by_id:
            continue

        subject = normalize_entity_label(triplet.subject)
        obj = normalize_entity_label(triplet.object)
        relation = normalize_relation_name(triplet.relation)
        subject_type = normalize_entity_type(triplet.subject_type)
        object_type = normalize_entity_type(triplet.object_type)
        subject_key = triplet.subject_key or canonical_entity_key(subject)
        object_key = triplet.object_key or canonical_entity_key(obj)

        if not subject or not obj or not relation:
            continue
        if not subject_key or not object_key:
            continue

        session.run(
            UPSERT_ENTITY_RELATION_CYPHER,
            workspace_id=workspace_id,
            chunk_id=chunk_id,
            file_name=file_name,
            page=triplet.page,
            subject_id=_entity_id(workspace_id, subject_key),
            subject=subject,
            subject_type=subject_type,
            subject_key=subject_key,
            subject_description=getattr(triplet, "description", "") or "",
            subject_aliases=[],
            object_id=_entity_id(workspace_id, object_key),
            object=obj,
            object_type=object_type,
            object_key=object_key,
            object_description="",
            object_aliases=[],
            relation=relation,
            evidence_preview=triplet.evidence_preview or "",
            confidence=float(triplet.confidence or 0.0),
            visual_ids=list(triplet.visual_ids or []),
        )
        written += 1
    return written


def upsert_visual_nodes(parsed: Any, source_file: str, workspace_id: str = "default") -> int:
    """Merge Formula/Image nodes with APPEARS_IN edges to Document node."""
    manager = get_neo4j_manager()
    added = 0
    workspace_id = workspace_id or "default"
    document_id = _document_node_id(workspace_id, source_file)
    now = _now_iso()

    with manager.session() as session:
        session.run(
            UPSERT_DOCUMENT_CYPHER,
            id=document_id,
            label=source_file,
            workspace_id=workspace_id,
            file_name=source_file,
            file_hash=getattr(parsed, "file_hash", "") or "",
            total_pages=int((getattr(parsed, "metadata", {}) or {}).get("total_pages", 0) or 0),
            created_at=now,
            updated_at=now,
        )

        for frm in getattr(parsed, "formulas", []):
            formula_id = frm.get("formula_id", "")
            latex      = frm.get("latex_string", "")
            if not formula_id:
                continue
            node_id = _formula_node_id(workspace_id, formula_id)
            session.run(
                UPSERT_FORMULA_CYPHER,
                id=node_id,
                label=f"Formula:{formula_id}",
                latex=latex or "",
                page=_visual_page(frm),
                document_id=document_id,
                document_label=source_file,
                workspace_id=workspace_id,
                source_file=source_file,
            )
            added += 1

        for img in getattr(parsed, "images", []):
            image_id = img.get("image_id", "")
            caption  = img.get("caption", "")
            if not image_id:
                continue
            node_id = _image_node_id(workspace_id, image_id)
            session.run(
                UPSERT_IMAGE_CYPHER,
                id=node_id,
                label=f"Image:{image_id}",
                caption=caption or "",
                page=_visual_page(img),
                document_id=document_id,
                document_label=source_file,
                workspace_id=workspace_id,
                source_file=source_file,
            )
            added += 1

    if added:
        print(f"[KG][Neo4j] {source_file}: {added} visual node(s) upserted (Formula/Image)")
    return added


def delete_document_kg(file_name: str, workspace_id: str = "default") -> int:
    """
    Delete a Neo4j-style document graph: Document -> Chunk anchors, chunks,
    the document node, then orphan Entity nodes in the same workspace.
    """
    manager = get_neo4j_manager()
    workspace_id = workspace_id or "default"
    with manager.session() as session:
        result = session.run(
            DELETE_DOCUMENT_GRAPH_CYPHER,
            file_name=file_name,
            workspace_id=workspace_id,
        )
        removed = _delete_result_count(result)

    print(
        f"[KG][Neo4j] Deleted document graph for '{file_name}' in workspace "
        f"'{workspace_id}', removed={removed}."
    )
    return removed


def _delete_result_count(result: Any) -> int:
    try:
        record = result.single()
        if record and record.get("removed") is not None:
            return int(record["removed"])
    except Exception:
        pass

    try:
        counters = result.consume().counters
        return int(counters.nodes_deleted) + int(counters.relationships_deleted)
    except Exception:
        return 0


def get_graph_for_viz(
    limit: int = 200,
    source_files: List[str] | None = None,
    workspace_id: str = "default",
    include_chunks: bool = False,
) -> Dict[str, List[Dict]]:
    """
    Return {"nodes": [...], "edges": [...]} for frontend PyVis rendering.
    Degree is pre-calculated in Python from edge data.
    """
    if source_files is not None and not source_files:
        return {"nodes": [], "edges": []}

    manager = get_neo4j_manager()
    workspace_id = workspace_id or "default"
    with manager.session() as session:
        if include_chunks:
            result = session.run(
                GET_GRAPH_WITH_CHUNKS_VIZ_CYPHER,
                limit=limit,
                workspace_id=workspace_id,
                source_files=source_files,
            )
        elif source_files is None:
            result = session.run(
                GET_ENTITY_GRAPH_VIZ_CYPHER,
                limit=limit,
                workspace_id=workspace_id,
            )
        else:
            result = session.run(
                GET_ENTITY_GRAPH_VIZ_BY_SOURCE_CYPHER,
                limit=limit,
                source_files=source_files,
                workspace_id=workspace_id,
            )

        edges: List[Dict]         = []
        node_map: Dict[str, Dict] = {}
        degree_count: Dict[str, int] = {}

        for rec in result:
            from_id = _record_value(rec, "from_id", "")
            to_id = _record_value(rec, "to_id", "")
            relation = _record_value(rec, "relation", "")
            source_files = _as_list(_record_value(rec, "source_files", []))
            pages = _as_list(_record_value(rec, "pages", []))

            edges.append({
                "id": _edge_id(from_id, relation, to_id),
                "from": from_id,
                "to": to_id,
                "relation": relation,
                "weight": _record_value(rec, "weight", 1),
                "confidence": _record_value(rec, "confidence", 0),
                "source_file": _first_item(source_files, ""),
                "page": int(_first_item(pages, 0) or 0),
                "source_files": source_files,
                "pages": pages,
                "chunk_ids": _as_list(_record_value(rec, "chunk_ids", [])),
                "visual_ids": _as_list(_record_value(rec, "visual_ids", [])),
                "evidence_preview": _record_value(rec, "evidence_preview", ""),
            })

            for nid, prefix in [
                (from_id, "from"),
                (to_id, "to"),
            ]:
                node_map.setdefault(nid, _node_payload(
                    node_id=nid,
                    label=_record_value(rec, f"{prefix}_label", nid),
                    node_type=_record_value(rec, f"{prefix}_type", "Concept"),
                    mentions=_record_value(rec, f"{prefix}_mentions", 1),
                    source_files=_record_value(rec, f"{prefix}_source_files", []),
                    pages=_record_value(rec, f"{prefix}_pages", []),
                ))
                degree_count[nid] = degree_count.get(nid, 0) + 1

    nodes = [
        {**data, "degree": degree_count.get(nid, 0)}
        for nid, data in node_map.items()
    ]
    return {"nodes": nodes, "edges": edges}
