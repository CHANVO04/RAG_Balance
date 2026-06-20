"""
ingest/vector_store.py — Qdrant client + collection helpers + upsert functions.

Collections:
  rag_docs     — cosine, dim=EMBED_DIM, query_points() for text chunk search.
  rag_visuals  — dummy vector size=1, payload lookup for full visual evidence.

Bug fix: formula payload now stores BOTH "page" AND "source_page" so that the
query layer's page-based filter on "page" key works correctly.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Dict, List

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from ingest.config import (
    EMBED_DIM,
    IMAGE_VLM_MODEL,
    QDRANT_API_KEY,
    QDRANT_HOST,
    QDRANT_PORT,
)
from ingest.analysis import ensure_analysis_short
from ingest.models import Chunk, ParsedDocument

# ── Collection constants ───────────────────────────────────────────────────────
_COL_DOCS     = "rag_docs"
_COL_TABLES   = "rag_tables"
_COL_FORMULAS = "rag_formulas"
_COL_IMAGES   = "rag_images"
_COL_VISUALS  = "rag_visuals"
_LEGACY_COLLECTIONS = ["rag_document_chunks"]
_CONTENT_COLLECTIONS = [_COL_DOCS, _COL_VISUALS, _COL_TABLES, _COL_FORMULAS, _COL_IMAGES]
_RESET_COLLECTIONS = _CONTENT_COLLECTIONS + _LEGACY_COLLECTIONS
_PAYLOAD_INDEXES = {
    _COL_DOCS: {
        "workspace_id": PayloadSchemaType.KEYWORD,
        "file_name": PayloadSchemaType.KEYWORD,
        "page": PayloadSchemaType.INTEGER,
        "content_type": PayloadSchemaType.KEYWORD,
    },
    _COL_VISUALS: {
        "workspace_id": PayloadSchemaType.KEYWORD,
        "file_name": PayloadSchemaType.KEYWORD,
        "visual_id": PayloadSchemaType.KEYWORD,
        "visual_type": PayloadSchemaType.KEYWORD,
        "page": PayloadSchemaType.INTEGER,
    },
}


def _str_to_uuid(s: str) -> str:
    """Convert any string ID → deterministic UUIDv5 (Qdrant requires UUID or int)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, s))


def get_qdrant_client() -> QdrantClient:
    """Return a connected QdrantClient. Call once and reuse."""
    print(f"[QDRANT] Connecting → {QDRANT_HOST}:{QDRANT_PORT}")
    return QdrantClient(
        host=QDRANT_HOST,
        port=QDRANT_PORT,
        api_key=QDRANT_API_KEY,
    )


def _ensure_collection(client: QdrantClient, name: str, size: int, distance: Distance) -> None:
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=size, distance=distance),
        )
        print(f"[QDRANT] Created collection: {name} (size={size}, distance={distance.name})")


def _ensure_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    """Create payload indexes used by workspace/file filtered retrieval."""
    for field_name, field_schema in _PAYLOAD_INDEXES.get(collection_name, {}).items():
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )
        except Exception as exc:
            print(f"[QDRANT][WARN] Payload index {collection_name}.{field_name}: {exc}")


def ensure_all_collections(client: QdrantClient) -> None:
    """Create active collections if they do not exist yet."""
    _ensure_collection(client, _COL_DOCS,     size=EMBED_DIM, distance=Distance.COSINE)
    _ensure_collection(client, _COL_VISUALS,  size=1,         distance=Distance.DOT)
    _ensure_payload_indexes(client, _COL_DOCS)
    _ensure_payload_indexes(client, _COL_VISUALS)


def reset_qdrant_collections(client: QdrantClient) -> List[str]:
    """Delete known Qdrant content collections without touching source files."""
    deleted: List[str] = []
    for name in _RESET_COLLECTIONS:
        try:
            if client.collection_exists(name):
                client.delete_collection(name)
                deleted.append(name)
                print(f"[QDRANT] Deleted collection: {name}")
        except Exception as exc:
            print(f"[QDRANT][WARN] Could not delete {name}: {exc}")
    return deleted


# ── Metadata builders ─────────────────────────────────────────────────────────

def _safe_meta(chunk: Chunk) -> Dict[str, Any]:
    """Build Qdrant payload dict for a Chunk. Text goes in payload['document']."""
    if chunk.has_table and chunk.has_formula:
        content_type = "mixed_table_formula"
    elif chunk.has_table:
        content_type = "table"
    elif chunk.has_formula:
        content_type = "formula"
    elif chunk.has_image:
        content_type = "text_with_image"
    else:
        content_type = "text"

    return {
        # document text stored here (Qdrant has no separate documents field)
        "document":        chunk.text,

        # ── Source tracing ──────────────────────────────────────────────────
        "source_file":     chunk.source_file,
        "source_page":     chunk.page,
        "source_section":  chunk.section_label or "",
        "source_title":    chunk.title or "",
        "source_doc_type": chunk.doc_type,
        "source_language": chunk.language,
        "workspace_id":    chunk.workspace_id,
        "source_workspace": chunk.workspace_id,
        "file_hash":       chunk.file_hash,

        # ── Chunk position ──────────────────────────────────────────────────
        "chunk_index":     chunk.chunk_index,
        "total_chunks":    chunk.total_chunks,
        "chunk_id":        chunk.chunk_id,

        # ── Content type ────────────────────────────────────────────────────
        "content_type":    content_type,

        # ── Cross-reference flags ───────────────────────────────────────────
        "has_table":       chunk.has_table,
        "has_image":       chunk.has_image,
        "has_formula":     chunk.has_formula,

        # ── Cross-reference IDs (JSON string — Qdrant supports nested but
        #    keep as string for compatibility with existing downstream code) ──
        "table_refs":      json.dumps(chunk.table_refs),
        "image_refs":      json.dumps(chunk.image_refs),
        "formula_refs":    json.dumps(chunk.formula_refs),
        "visual_assets":   json.dumps(chunk.visual_assets, ensure_ascii=False),
        "visual_refs":     json.dumps(chunk.visual_refs, ensure_ascii=False),
        "table_markdowns": json.dumps(chunk.table_markdowns, ensure_ascii=False),
        "formula_latex":   json.dumps(chunk.formula_latex, ensure_ascii=False),

        # ── Backward-compat aliases ─────────────────────────────────────────
        "file_name":       chunk.source_file,
        "page":            chunk.page,
        "section_label":   chunk.section_label or "",
        "doc_type":        chunk.doc_type,
        "language":        chunk.language,
        "title":           chunk.title or "",
    }


def _file_filter(file_name: str, workspace_id: str | None = None) -> Filter:
    must = [FieldCondition(key="file_name", match=MatchValue(value=file_name))]
    if workspace_id:
        must.append(FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id)))
    return Filter(must=must)


# ── Upsert helpers ────────────────────────────────────────────────────────────

def upsert_to_qdrant(
    client: QdrantClient,
    chunks: List[Chunk],
    embeddings: np.ndarray,
) -> None:
    """Upsert main text chunks into rag_docs."""
    if not chunks or embeddings is None:
        return

    points = []
    for chunk, emb in zip(chunks, embeddings.tolist()):
        point_id = _str_to_uuid(chunk.chunk_id)
        payload  = _safe_meta(chunk)
        points.append(PointStruct(id=point_id, vector=emb, payload=payload))

    client.upsert(collection_name=_COL_DOCS, points=points)
    print(f"[QDRANT] Upserted {len(points)} chunks → {_COL_DOCS}")


def build_visual_points(
    parsed_doc: ParsedDocument,
    file_name: str,
    file_hash: str,
    workspace_id: str = "default",
) -> List[PointStruct]:
    """Build dummy-vector points for full visual evidence lookup."""
    points: List[PointStruct] = []
    for visual_type, items, id_key, raw_key in (
        ("table", parsed_doc.tables, "table_id", "markdown"),
        ("image", parsed_doc.images, "image_id", ""),
        ("formula", parsed_doc.formulas, "formula_id", "latex_string"),
    ):
        for visual in items:
            visual_id = visual.get(id_key, "")
            if not visual_id:
                continue
            analysis_full = visual.get("analysis_markdown", "") or ""
            analysis_short = ensure_analysis_short(visual, visual_type)
            doc_id = hashlib.sha256(f"{workspace_id}_{file_hash}_{visual_id}".encode()).hexdigest()[:32]
            payload = {
                "document": analysis_short or visual.get("caption", "") or visual.get(raw_key, ""),
                "visual_id": visual_id,
                "visual_type": visual_type,
                "workspace_id": workspace_id,
                "source_workspace": workspace_id,
                "file_name": file_name,
                "source_file": file_name,
                "file_hash": file_hash,
                "page": visual.get("page", 0),
                "source_page": visual.get("page", 0),
                "self_ref": visual.get("self_ref", ""),
                "asset_path": visual.get("asset_path") or visual.get("path", ""),
                "caption": visual.get("caption", ""),
                "raw_content": visual.get(raw_key, "") if raw_key else "",
                "analysis_short": analysis_short,
                "analysis_full": analysis_full,
                "is_decoded": visual.get("is_decoded", None),
                "doc_id": doc_id,
            }
            points.append(PointStruct(id=_str_to_uuid(doc_id), vector=[0.0], payload=payload))
    return points


def upsert_visuals_to_qdrant(
    client: QdrantClient,
    parsed_doc: ParsedDocument,
    file_name: str,
    file_hash: str,
    workspace_id: str = "default",
) -> int:
    """Upsert table/image/formula full analyses into rag_visuals for ID lookup."""
    points = build_visual_points(parsed_doc, file_name, file_hash, workspace_id=workspace_id)
    if not points:
        return 0
    client.upsert(collection_name=_COL_VISUALS, points=points)
    print(f"[QDRANT] Upserted {len(points)} visual payloads → {_COL_VISUALS}")
    return len(points)


def upsert_tables_to_qdrant(client: QdrantClient, chunks: List[Chunk]) -> None:
    """Upsert table chunks into rag_tables with dummy vector [0.0]."""
    table_chunks = [c for c in chunks if c.has_table]
    if not table_chunks:
        return

    points = []
    for chunk in table_chunks:
        point_id = _str_to_uuid(chunk.chunk_id)
        payload  = _safe_meta(chunk)
        # Bug 4: size=1 DOT collection requires exactly vector=[0.0]
        points.append(PointStruct(id=point_id, vector=[0.0], payload=payload))

    client.upsert(collection_name=_COL_TABLES, points=points)
    print(f"[QDRANT] Upserted {len(points)} table chunks → {_COL_TABLES}")


def upsert_formulas_to_qdrant(
    client: QdrantClient,
    parsed_doc: ParsedDocument,
    file_name: str,
    file_hash: str,
) -> int:
    """
    Upsert formulas into rag_formulas with dummy vector [0.0].

    Bug fix: payload stores BOTH 'page' AND 'source_page' so that the
    retrieve_formulas() filter on payload['page'] works correctly.
    """
    if not parsed_doc.formulas:
        return 0

    points = []
    for frm in parsed_doc.formulas:
        formula_id = frm["formula_id"]
        latex      = frm.get("latex_string", "")
        is_decoded = frm.get("is_decoded", False)
        page       = frm.get("page", 0)

        if "Pending API" in latex:
            latex      = "[Not Decodable]"
            is_decoded = False

        doc_id   = hashlib.sha256(f"{file_hash}_{formula_id}".encode()).hexdigest()[:32]
        point_id = _str_to_uuid(doc_id)

        payload = {
            "document":    latex,          # text content stored here

            # Source tracing
            "formula_id":  formula_id,
            "file_name":   file_name,
            "file_hash":   file_hash,
            "source_page": page,
            "page":        page,           # BUG FIX: add 'page' alias for query-layer filter
            "doc_id":      doc_id,

            # Content
            "latex_string": latex,
            "is_decoded":   is_decoded,
            "content_type": "formula",
        }
        # Bug 4: size=1 DOT collection requires exactly vector=[0.0]
        points.append(PointStruct(id=point_id, vector=[0.0], payload=payload))

    client.upsert(collection_name=_COL_FORMULAS, points=points)
    n_decoded = sum(1 for frm in parsed_doc.formulas if frm.get("is_decoded"))
    n_total   = len(points)
    print(
        f"[QDRANT] Upserted {n_total} formulas → {_COL_FORMULAS} "
        f"(decoded: {n_decoded}/{n_total}, failed: {n_total-n_decoded}/{n_total})"
    )
    return n_total


def upsert_images_to_qdrant(
    client: QdrantClient,
    parsed_doc: ParsedDocument,
    file_name: str,
    file_hash: str,
    embedding_model,
) -> int:
    """Upsert image analyses into rag_images with real OpenAI embeddings."""
    analyzed = [img for img in parsed_doc.images if img.get("analysis_markdown")]
    if not analyzed:
        print(f"[QDRANT] Không có image nào được phân tích trong {file_name} → bỏ qua {_COL_IMAGES}")
        return 0

    texts_to_embed = [img["analysis_markdown"] for img in analyzed]
    embeddings     = embedding_model.encode(texts_to_embed, normalize_embeddings=True)

    points = []
    for img, emb in zip(analyzed, embeddings.tolist()):
        image_id = img["image_id"]
        doc_id   = hashlib.sha256(f"{file_hash}_{image_id}".encode()).hexdigest()[:32]
        point_id = _str_to_uuid(doc_id)

        payload = {
            "document":       img["analysis_markdown"],

            "image_id":       image_id,
            "file_name":      file_name,
            "file_hash":      file_hash,
            "page":           img.get("page", 0),
            "caption":        img.get("caption", ""),
            "is_analyzed":    True,
            "analysis_model": IMAGE_VLM_MODEL,
            "doc_id":         doc_id,
        }
        points.append(PointStruct(id=point_id, vector=emb, payload=payload))

    client.upsert(collection_name=_COL_IMAGES, points=points)
    print(f"[QDRANT] Upserted {len(points)} image analyses → {_COL_IMAGES} (OpenAI embeddings dim={EMBED_DIM})")
    return len(points)


# ── Delete helper ─────────────────────────────────────────────────────────────

def delete_from_qdrant(
    client: QdrantClient,
    file_name: str,
    workspace_id: str | None = None,
) -> Dict[str, int]:
    """Delete all indexed payloads for one file across current and legacy collections."""
    removed = {}
    for col_name in _CONTENT_COLLECTIONS:
        try:
            before = client.count(collection_name=col_name, exact=True).count
            client.delete(
                collection_name=col_name,
                points_selector=_file_filter(file_name, workspace_id),
                wait=True,
            )
            after   = client.count(collection_name=col_name, exact=True).count
            removed[col_name] = before - after
            scope = f" workspace={workspace_id}" if workspace_id else ""
            print(f"[QDRANT] Xóa {removed[col_name]} points của '{file_name}'{scope} khỏi {col_name}")
        except Exception as e:
            print(f"[QDRANT][WARN] {col_name}: {e}")
            removed[col_name] = 0
    return removed


def delete_workspace_from_qdrant(client: QdrantClient, workspace_id: str) -> Dict[str, int]:
    """Delete all points associated with workspace_id in Qdrant collections."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    workspace_filter = Filter(must=[
        FieldCondition(
            key="workspace_id",
            match=MatchValue(value=workspace_id)
        )
    ])
    
    removed = {}
    for col_name in _CONTENT_COLLECTIONS:
        try:
            if not client.collection_exists(col_name):
                continue
            before = client.count(collection_name=col_name, exact=True).count
            client.delete(
                collection_name=col_name,
                points_selector=workspace_filter,
                wait=True,
            )
            after = client.count(collection_name=col_name, exact=True).count
            removed[col_name] = before - after
            print(f"[QDRANT] Deleted {removed[col_name]} points for workspace '{workspace_id}' from {col_name}")
        except Exception as e:
            print(f"[QDRANT][WARN] Failed to delete workspace '{workspace_id}' from {col_name}: {e}")
            removed[col_name] = 0
    return removed


