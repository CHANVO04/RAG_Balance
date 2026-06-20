"""
Deterministic workspace document inventory for document-level questions.

This module is intentionally local and cheap: it reads registry/doc-store JSON
only when a question asks about documents/files/noise/source selection.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List


_BACKEND_DIR = Path(__file__).resolve().parents[1]
_DOCUMENT_INTENT_PATTERNS = (
    "which document", "which file", "which source",
    "noise document", "relevant document", "provided documents",
    "document discusses", "source discusses", "file discusses",
    "should not be used", "smallpdf", "e-signature", "e-signatures",
    "file sharing", "document management",
    "tai lieu nao", "tài liệu nào", "file nào", "nguồn nào",
)


def should_include_document_inventory(question: str) -> bool:
    """Return True for questions that need awareness of all workspace files."""
    normalized = _normalize(question)
    if not normalized:
        return False
    return any(pattern in normalized for pattern in _DOCUMENT_INTENT_PATTERNS)


def build_document_inventory_context(
    workspace_id: str,
    vector_dir: str | None = None,
    max_docs: int = 12,
    snippets_per_doc: int = 2,
) -> str:
    """Build a compact per-file inventory from registry and document store."""
    root = Path(vector_dir) if vector_dir else _workspace_db_dir(workspace_id)
    registry = _read_json(root / "registry.json", {"documents": []})
    store = _read_json(root / "documents_store.json", {"documents": []})

    documents = registry.get("documents", [])
    if not isinstance(documents, list) or not documents:
        return ""

    snippets_by_file = _collect_snippets(store.get("documents", []), snippets_per_doc)
    lines = ["### WORKSPACE DOCUMENT INVENTORY"]
    for doc in documents[:max_docs]:
        file_name = str(doc.get("file_name", "")).strip()
        if not file_name:
            continue
        stats = _format_doc_stats(doc)
        snippets = snippets_by_file.get(file_name, [])
        summary = " ".join(snippets) if snippets else "No representative snippet is available."
        lines.append(f"- {file_name}{stats}: {_compact(summary, 420)}")

    return "\n".join(lines) if len(lines) > 1 else ""


def _workspace_db_dir(workspace_id: str) -> Path:
    wid = _safe_workspace_id(workspace_id)
    if wid == "default":
        return _BACKEND_DIR / "db"
    return _BACKEND_DIR / "workspaces" / wid / "db"


def _safe_workspace_id(workspace_id: str | None) -> str:
    raw = (workspace_id or "default").strip() or "default"
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in ("-", "_"))
    return safe or "default"


def _read_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    if isinstance(data, list):
        return {"documents": data}
    return data if isinstance(data, dict) else fallback


def _collect_snippets(records: Any, snippets_per_doc: int) -> Dict[str, List[str]]:
    snippets: Dict[str, List[str]] = {}
    if not isinstance(records, list):
        return snippets

    for record in records:
        if not isinstance(record, dict):
            continue
        meta = record.get("metadata", {})
        file_name = str(meta.get("file_name", "")).strip() if isinstance(meta, dict) else ""
        text = _compact(str(record.get("text", "") or ""), 240)
        if not file_name or not text:
            continue
        bucket = snippets.setdefault(file_name, [])
        if len(bucket) < snippets_per_doc:
            bucket.append(text)
    return snippets


def _format_doc_stats(doc: Dict[str, Any]) -> str:
    parts = []
    pages = doc.get("total_pages")
    chunks = doc.get("total_dedup_chunks")
    if pages:
        parts.append(f"{pages} page(s)")
    if chunks:
        parts.append(f"{chunks} chunk(s)")
    return f" ({', '.join(parts)})" if parts else ""


def _compact(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rsplit(" ", 1)[0].strip()


def _normalize(text: str) -> str:
    import unicodedata

    lowered = unicodedata.normalize("NFD", (text or "").lower())
    ascii_text = "".join(ch for ch in lowered if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", ascii_text).strip()

