import os
import json
import numpy as np
from datetime import datetime
from typing import Any, List, Dict, Optional

from query.config import VECTOR_DIR, CACHE_THRESHOLD
from query.clients import get_embedder

CACHE_FILE = os.path.join(VECTOR_DIR, "semantic_cache.json")

def load_cache() -> List[Dict]:
    if not os.path.exists(CACHE_FILE):
        return []
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cache(cache_data: List[Dict]):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)

def _normalize_files(file_names: Optional[List[str]]) -> set[str]:
    return {str(name) for name in (file_names or []) if str(name).strip()}


def _entry_file_names(entry: Dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("file_names", "selected_files", "source_files"):
        value = entry.get(key)
        if isinstance(value, list):
            names.update(str(item) for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            names.add(value)
    return names


def _is_legacy_unscoped(entry: Dict[str, Any]) -> bool:
    return not entry.get("workspace_id") and not _entry_file_names(entry)


def _cache_entry_in_query_scope(
    entry: Dict[str, Any],
    workspace_id: Optional[str],
    file_names: Optional[List[str]],
) -> bool:
    if workspace_id and entry.get("workspace_id") != workspace_id:
        return False

    requested_files = _normalize_files(file_names)
    if not requested_files:
        return True

    cached_files = _entry_file_names(entry)
    return bool(cached_files & requested_files)


def _cache_entry_matches_delete_scope(
    entry: Dict[str, Any],
    workspace_id: Optional[str],
    file_name: Optional[str],
) -> bool:
    if _is_legacy_unscoped(entry):
        # Legacy cache cannot be proven safe after scoped deletes.
        return bool(workspace_id or file_name)

    if workspace_id and entry.get("workspace_id") == workspace_id:
        return True

    if file_name and file_name in _entry_file_names(entry):
        return True

    return False


def clear_cache_entries(workspace_id: Optional[str] = None, file_name: Optional[str] = None) -> int:
    """Remove semantic cache entries that could reference deleted local data."""
    cache = load_cache()
    if not cache:
        return 0

    if not workspace_id and not file_name:
        save_cache([])
        return len(cache)

    kept = [
        entry for entry in cache
        if not _cache_entry_matches_delete_scope(entry, workspace_id, file_name)
    ]
    removed = len(cache) - len(kept)
    if removed:
        save_cache(kept)
    return removed


def check_semantic_cache(
    question: str,
    workspace_id: Optional[str] = None,
    file_names: Optional[List[str]] = None,
) -> Optional[str]:
    cache = load_cache()
    if not cache:
        return None
    embedder = get_embedder()
    q_emb = embedder.encode(question, normalize_embeddings=True)
    q_dim = q_emb.shape[0]
    for entry in cache:
        if not _cache_entry_in_query_scope(entry, workspace_id, file_names):
            continue
        c_emb = np.array(entry["embedding"])
        if c_emb.shape[0] != q_dim:
            # Stale cache entry from old embedding model — skip silently
            print(f"[CACHE][WARN] Bỏ qua entry cũ dim={c_emb.shape[0]} (hiện tại dim={q_dim})")
            continue
        sim = float(np.dot(q_emb, c_emb))
        if sim >= CACHE_THRESHOLD:
            print(f"[CACHE] HIT! Trùng khớp {sim*100:.1f}% với câu hỏi: '{entry['question']}'")
            return entry["answer"]
    return None

def add_to_cache(
    question: str,
    answer: str,
    workspace_id: Optional[str] = None,
    file_names: Optional[List[str]] = None,
):
    cache = load_cache()
    embedder = get_embedder()
    q_emb = embedder.encode(question, normalize_embeddings=True).tolist()
    cache.append({
        "question": question,
        "answer": answer,
        "embedding": q_emb,
        "workspace_id": workspace_id or "",
        "file_names": sorted(_normalize_files(file_names)),
        "timestamp": datetime.now().isoformat()
    })
    save_cache(cache[-100:])
