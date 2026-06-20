"""
ingest/registry.py — Load/save registry.json và documents_store.json.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List

from ingest.config import VECTOR_DIR
from ingest.models import Chunk


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


# ── Registry ─────────────────────────────────────────────────────────────────

def load_registry(vector_dir: str = VECTOR_DIR) -> Dict[str, Any]:
    """Đọc registry.json."""
    path = os.path.join(vector_dir, "registry.json")
    if not os.path.exists(path):
        return {"documents": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {"documents": data}
            return data
    except Exception:
        return {"documents": []}


def save_registry(registry: Dict[str, Any], vector_dir: str = VECTOR_DIR) -> None:
    ensure_dir(vector_dir)
    path = os.path.join(vector_dir, "registry.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    print(f"[REGISTRY] Saved → {path}")


def is_already_ingested(file_hash: str, registry: Dict[str, Any]) -> bool:
    return any(d.get("file_hash") == file_hash for d in registry.get("documents", []))


def add_to_registry(registry: Dict[str, Any], info: Dict[str, Any]) -> None:
    docs = registry.setdefault("documents", [])
    # Replace existing entry by file_name (handles --force re-ingest without duplicates)
    for i, d in enumerate(docs):
        if d.get("file_name") == info.get("file_name"):
            docs[i] = info
            return
    docs.append(info)


def list_ingested_documents(vector_dir: str = VECTOR_DIR) -> List[Dict[str, Any]]:
    return load_registry(vector_dir).get("documents", [])


# ── Document Store ────────────────────────────────────────────────────────────

def load_doc_store(vector_dir: str = VECTOR_DIR) -> Dict[str, Any]:
    path = os.path.join(vector_dir, "documents_store.json")
    if not os.path.exists(path):
        return {"documents": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {"documents": data}
            return data
    except Exception:
        return {"documents": []}


def save_doc_store(store: Dict[str, Any], vector_dir: str = VECTOR_DIR) -> None:
    ensure_dir(vector_dir)
    path = os.path.join(vector_dir, "documents_store.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)
    print(f"[DOC_STORE] Saved → {path}")


def _normalize_text(text: str) -> str:
    """Inline normalize — tránh circular import với parser.py."""
    import re
    import unicodedata
    text = text.lower().strip()
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _safe_meta(chunk: Chunk) -> Dict[str, Any]:
    """Chuyển Chunk metadata về dict chỉ chứa str/int/float/bool."""
    import json as _json
    return {
        "file_name":     chunk.source_file,
        "workspace_id":  chunk.workspace_id,
        "file_hash":     chunk.file_hash,
        "page":          chunk.page,
        "section_label": chunk.section_label or "",
        "chunk_index":   chunk.chunk_index,
        "total_chunks":  chunk.total_chunks,
        "has_table":     chunk.has_table,
        "table_refs":    _json.dumps(chunk.table_refs),
        "image_refs":    _json.dumps(chunk.image_refs),
        "has_image":     chunk.has_image,
        "has_formula":   chunk.has_formula,
        "formula_refs":  _json.dumps(chunk.formula_refs),
        "visual_assets": _json.dumps(chunk.visual_assets, ensure_ascii=False),
        "visual_refs":   _json.dumps(chunk.visual_refs, ensure_ascii=False),
        "table_markdowns": _json.dumps(chunk.table_markdowns, ensure_ascii=False),
        "formula_latex": _json.dumps(chunk.formula_latex, ensure_ascii=False),
        "doc_type":      chunk.doc_type,
        "title":         chunk.title or "",
        "language":      chunk.language,
        "chunk_id":      chunk.chunk_id,
    }


def append_chunks_to_store(chunks: List[Chunk], vector_dir: str = VECTOR_DIR) -> None:
    """
    Append chunks vào documents_store.json.
    Thêm content_hash field cho cross-run dedup.
    Per-file flush: ~0.05s/call trên NVMe — negligible vs LLM/embed latency.
    """
    store = load_doc_store(vector_dir)
    if not isinstance(store, dict) or "documents" not in store:
        store = {"documents": []}
    for c in chunks:
        content_hash = hashlib.sha256(_normalize_text(c.text).encode()).hexdigest()
        store["documents"].append({
            "chunk_id":     c.chunk_id,
            "content_hash": content_hash,
            "text":         c.text,
            "metadata":     _safe_meta(c),
        })
    save_doc_store(store, vector_dir)
