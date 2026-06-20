"""
ingest/pipeline.py — offline_ingest(), delete_document(), main() CLI.
Per-file processing loop: Parse→Chunk→Dedup→Embed→Upsert→KG→Registry→GC.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
import sys
import time
from pathlib import Path

# Thêm thư mục backend vào sys.path để tránh lỗi ModuleNotFoundError: No module named 'ingest'
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from datetime import datetime
from typing import Any, Callable, Dict, List

from ingest.config import DATA_DIR, VECTOR_DIR, EMBED_MODEL, EMBED_PRICE_PER_1M_TOKENS
from ingest.models import Chunk, ParsedDocument
from ingest.parser import find_documents, calculate_file_hash, ensure_dir
from ingest.chunker import chunk_document, dedup_chunks
from ingest.embedder import get_embedding_model, embed_chunks
from ingest.vector_store import (
    get_qdrant_client,
    ensure_all_collections,
    upsert_to_qdrant,
    upsert_visuals_to_qdrant,
    delete_from_qdrant,
)
from ingest.registry import (
    load_registry, save_registry,
    is_already_ingested, add_to_registry,
    list_ingested_documents,
    load_doc_store, save_doc_store,
    append_chunks_to_store,
)
from ingest.kg import run_kg_step
from ingest.parser import parse_document
from ingest.vision import cleanup_formula_debug_images
from kg_neo4j import delete_document_kg


def _is_safe_document_file_name(file_name: str) -> bool:
    if not file_name or file_name in {".", ".."}:
        return False
    if "\x00" in file_name or ":" in file_name:
        return False
    if "/" in file_name or "\\" in file_name:
        return False
    return os.path.basename(file_name) == file_name


def _resolve_document_delete_path(data_dir: str, file_name: str) -> str:
    data_root = os.path.abspath(data_dir)
    file_path = os.path.abspath(os.path.join(data_root, file_name))
    if os.path.commonpath([data_root, file_path]) != data_root:
        raise ValueError("Document path escapes data directory.")
    return file_path


def _asset_roots(vector_dir: str) -> List[Path]:
    roots = [
        Path(VECTOR_DIR).resolve() / "assets",
        Path(vector_dir).resolve() / "assets",
    ]
    unique_roots: List[Path] = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)
    return unique_roots


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([str(root), str(path)]) == str(root)
    except ValueError:
        return False


def _resolve_asset_path(raw_path: str, allowed_roots: List[Path]) -> Path | None:
    if not raw_path:
        return None

    raw = Path(raw_path)
    project_root = Path(backend_dir).parent
    candidates = [raw] if raw.is_absolute() else [project_root / raw, Path.cwd() / raw]
    for candidate in candidates:
        resolved = candidate.resolve()
        if any(_path_is_under(resolved, root) for root in allowed_roots):
            return resolved
    return None


def _visual_assets_from_metadata(store: Dict[str, Any], file_name: str, allowed_roots: List[Path]) -> List[Path]:
    paths: List[Path] = []
    for item in store.get("documents", []):
        metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
        if metadata.get("file_name") != file_name:
            continue

        raw_assets = metadata.get("visual_assets", "[]")
        try:
            assets = json.loads(raw_assets) if isinstance(raw_assets, str) else raw_assets
        except json.JSONDecodeError:
            assets = []

        if not isinstance(assets, list):
            continue

        for asset in assets:
            if not isinstance(asset, dict):
                continue
            resolved = _resolve_asset_path(
                str(asset.get("path") or asset.get("asset_path") or ""),
                allowed_roots,
            )
            if resolved:
                paths.append(resolved)
    return paths


def _prune_empty_asset_parents(start: Path, allowed_roots: List[Path]) -> None:
    current = start
    for _ in range(6):
        if not any(_path_is_under(current, root) for root in allowed_roots):
            return
        if current in allowed_roots:
            return
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def delete_visual_assets_for_file(
    file_name: str,
    vector_dir: str,
    registry: Dict[str, Any],
    store: Dict[str, Any],
) -> int:
    """Delete visual PNG assets associated with one file without leaving assets roots."""
    allowed_roots = _asset_roots(vector_dir)
    file_hashes = {
        str(doc.get("file_hash"))
        for doc in registry.get("documents", [])
        if doc.get("file_name") == file_name and doc.get("file_hash")
    }

    candidates: set[Path] = set(_visual_assets_from_metadata(store, file_name, allowed_roots))
    for root in allowed_roots:
        for file_hash in file_hashes:
            hash_dir = root / file_hash
            if hash_dir.exists():
                candidates.update(path for path in hash_dir.rglob("*") if path.is_file())

    removed = 0
    for path in sorted(candidates):
        if not path.exists() or not any(_path_is_under(path, root) for root in allowed_roots):
            continue
        path.unlink()
        removed += 1
        _prune_empty_asset_parents(path.parent, allowed_roots)

    return removed


def _delete_document_kg_if_enabled(file_name: str, workspace_id: str, delete_kg: bool = True) -> int:
    if not delete_kg:
        return 0
    return int(delete_document_kg(file_name, workspace_id=workspace_id) or 0)


def _build_registry_info(
    fname: str,
    fhash: str,
    fsize: int,
    parsed: ParsedDocument,
    chunks: List[Chunk],
    n_triplets: int,
    workspace_id: str = "default",
    ingest_mode: str = "",
    processing_time_seconds: float | None = None,
    stage_timings: Dict[str, float] | None = None,
    embedding: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    info = {
        "file_name":          fname,
        "workspace_id":       workspace_id,
        "file_hash":          fhash,
        "file_size":          fsize,
        "doc_type":           parsed.doc_type,
        "total_pages":        parsed.metadata.get("total_pages", 0),
        "total_dedup_chunks": len(chunks),
        "total_tables":       len(parsed.tables),
        "total_images":       len(parsed.images),
        "total_formulas":     len(parsed.formulas),
        "total_kg_triplets":  n_triplets,
        "ingested_at":        datetime.now().isoformat(),
    }
    if ingest_mode:
        info["ingest_mode"] = ingest_mode
    if processing_time_seconds is not None:
        info["processing_time_seconds"] = round(max(0.0, processing_time_seconds), 2)
    if stage_timings is not None:
        info["stage_timings"] = stage_timings
    if embedding is not None:
        info["embedding"] = embedding
    return info


def _embedding_usage_tokens(embed_model: Any) -> int:
    usage = getattr(embed_model, "last_usage", None)
    return int(getattr(usage, "input_tokens", 0) or 0)


def _embedding_model_name(embed_model: Any, fallback: str) -> str:
    return str(getattr(embed_model, "_model", None) or fallback)


def _build_embedding_metrics(embed_model: Any, model_name: str, input_tokens: int) -> Dict[str, Any]:
    price = float(EMBED_PRICE_PER_1M_TOKENS)
    return {
        "model": _embedding_model_name(embed_model, model_name),
        "input_tokens": max(0, int(input_tokens or 0)),
        "price_per_1m_tokens": price,
        "cost_usd": round(max(0, int(input_tokens or 0)) / 1_000_000 * price, 10),
    }


def _resolve_ingest_mode_label(kg_mode: str, skip_visual_analysis: bool) -> str:
    if skip_visual_analysis:
        return "only_vector_fast"
    if kg_mode not in ("none", "ablation"):
        return "hybrid"
    return "only_vector_multimodal"


def _record_stage_timing(
    stage_timings: Dict[str, Dict[str, float]],
    file_name: str,
    stage_name: str,
    started_at: float,
    report: Callable[[str, int], None] | None = None,
    progress: int = -1,
) -> float:
    """Record one ingest stage duration and optionally emit a task log line."""
    elapsed = round(max(0.0, time.time() - started_at), 2)
    stage_timings.setdefault(file_name, {})[stage_name] = elapsed
    if report:
        report(f"[TIME] {file_name} {stage_name}: {elapsed:.2f}s", progress)
    return elapsed


def offline_ingest(
    data_dir:   str  = DATA_DIR,
    vector_dir: str  = VECTOR_DIR,
    model_name: str  = EMBED_MODEL,
    force:      bool = False,
    verbose:    bool = True,
    kg_mode:    str  = "light",
    skip_visual_analysis: bool = False,
    workspace_id: str = "default",
    progress_callback: Callable[[str, int], None] | None = None,
) -> Dict[str, Any]:
    """
    Pipeline đầy đủ với per-file processing (OOM fix):
    1. Find files
    2. Load registry → skip đã ingest
    3. Per-file: Parse→Chunk→Dedup→Embed→Upsert→KG→Registry→GC
    4. Return summary dict

    kg_mode options:
      "none"     — bỏ qua KG step hoàn toàn
      "light"    — KG bình thường (default)
      "full"     — KG với visuals (KG_INCLUDE_VISUALS override)
      "ablation" — chỉ Parse→Chunk, bỏ qua Qdrant upsert và KG
    """
    t_start = time.time()

    def report(step: str, progress: int) -> None:
        if progress_callback:
            progress_callback(step, progress)

    # Dọn formula debug images từ run trước trước khi bắt đầu run mới.
    # Khi SAVE_FORMULA_IMAGES=false: không có ảnh nào được lưu → cleanup là no-op.
    # Khi SAVE_FORMULA_IMAGES=true: xóa ảnh cũ để tránh tích lũy qua nhiều run.
    cleanup_formula_debug_images()

    if kg_mode == "ablation":
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ablation_dir = os.path.join("experiments", f"kg_ablation_{ts}")
        os.makedirs(ablation_dir, exist_ok=True)
        if verbose:
            print(f"[KG] Ablation mode → {ablation_dir}")

    if verbose:
        print("\n" + "=" * 60)
        print("  OFFLINE INGEST PIPELINE v4 (Qdrant + Neo4j)")
        print(f"  model      : {model_name}")
        print(f"  data_dir   : {data_dir}")
        print(f"  vector_dir : {vector_dir}")
        print(f"  kg_mode    : {kg_mode}")
        print(f"  vision     : {'SKIPPED' if skip_visual_analysis else 'ENABLED'}")
        print("=" * 60)

    ensure_dir(vector_dir)

    file_paths = find_documents(data_dir)
    report("Đang kiểm tra tài liệu trong workspace", 8)
    if verbose:
        print(f"[DATA] Tìm thấy {len(file_paths)} file(s): {[os.path.basename(p) for p in file_paths]}")

    if not file_paths:
        return {
            "status": "no_new_files",
            "new_files": [],
            "skipped_files": [],
            "total_files": 0,
            "total_raw_chunks": 0,
            "total_dedup_chunks": 0,
            "total_tables": 0,
            "total_images": 0,
            "total_kg_triplets": 0,
            "processing_time_seconds": 0.0,
            "stages": {
                "parsed": False, "chunked": False, "deduped": False,
                "embedded": False, "indexed": False, "kg_ingested": False,
            },
        }

    registry = load_registry(vector_dir)

    if kg_mode == "ablation":
        qdrant_client = None
        embed_model   = None
    else:
        qdrant_client = get_qdrant_client()
        ensure_all_collections(qdrant_client)
        embed_model = get_embedding_model(model_name)

    new_files:     List[str] = []
    skipped_files: List[str] = []
    error_files:   List[str] = []

    total_raw_chunks        = 0
    total_dedup_chunks      = 0
    total_tables            = 0
    total_images            = 0
    total_formulas          = 0
    total_analyzed_imgs     = 0
    total_kg_triplets       = 0
    total_decoded_formulas  = 0
    total_failed_formulas   = 0
    stage_timings: Dict[str, Dict[str, float]] = {}

    for file_path in file_paths:
        fname = os.path.basename(file_path)
        file_started_at = time.time()
        file_embedding_tokens = 0
        fhash = calculate_file_hash(str(file_path))
        fsize = os.path.getsize(file_path)
        report(f"Đang xử lý {fname}", 12)

        if not force and is_already_ingested(fhash, registry):
            if verbose:
                print(f"[SKIP] {fname} (đã ingest, hash khớp)")
            skipped_files.append({"file": fname, "reason": "already_ingested"})
            report(f"Bỏ qua {fname} vì đã ingest", 100)
            continue

        parsed, doc_obj = None, None
        try:
            report(f"Đang parse layout: {fname}", 20)
            stage_start = time.time()
            result = parse_document(file_path, skip_visual_analysis=skip_visual_analysis)
            _record_stage_timing(stage_timings, fname, "parse_layout", stage_start, report, 20)
            if result is None:
                print(f"[ERROR] Bỏ qua {fname} vì parse thất bại")
                error_files.append(fname)
                continue
            parsed, doc_obj = result
            report(f"Đã parse xong: {fname}", 38)

            _file_decoded = sum(1 for f in parsed.formulas if f.get("is_decoded"))
            _file_failed  = sum(1 for f in parsed.formulas if not f.get("is_decoded"))
            total_decoded_formulas += _file_decoded
            total_failed_formulas  += _file_failed
            if parsed.formulas:
                print(
                    f"[FORMULA] {fname}: {len(parsed.formulas)} formulas | "
                    f"{_file_decoded} decoded ({_file_failed} failed)"
                )

            report(f"Đang chunk tài liệu: {fname}", 48)
            stage_start = time.time()
            chunks = chunk_document(
                parsed,
                doc_obj=doc_obj,
                workspace_id=workspace_id,
                include_image_formula_visuals=not skip_visual_analysis,
            )
            _record_stage_timing(stage_timings, fname, "chunk", stage_start, report, 48)
            total_raw_chunks += len(chunks)

            report(f"Đang dedup chunks: {fname}", 58)
            stage_start = time.time()
            chunks = dedup_chunks(chunks)
            _record_stage_timing(stage_timings, fname, "dedup", stage_start, report, 58)

            if not chunks:
                print(f"[INFO] {fname}: không có chunk mới sau dedup → skip embed")
                new_files.append(fname)
                n_triplets = 0
            else:
                if kg_mode != "ablation":
                    report(f"Đang tạo embedding: {fname}", 68)
                    stage_start = time.time()
                    tokens_before = _embedding_usage_tokens(embed_model)
                    embeddings = embed_chunks(chunks, embed_model)
                    file_embedding_tokens = _embedding_usage_tokens(embed_model) - tokens_before
                    _record_stage_timing(stage_timings, fname, "embedding", stage_start, report, 68)
                    report(f"Đang lưu chunks vào Qdrant: {fname}", 78)
                    stage_start = time.time()
                    upsert_to_qdrant(qdrant_client, chunks, embeddings)
                    _record_stage_timing(stage_timings, fname, "qdrant_docs_upsert", stage_start, report, 78)
                    if skip_visual_analysis:
                        report(f"Bỏ qua lưu visual payload trong Fast mode: {fname}", 84)
                        stage_timings.setdefault(fname, {})["qdrant_visuals_upsert_skipped"] = 0.0
                    else:
                        report(f"Đang lưu visual payload vào Qdrant: {fname}", 84)
                        stage_start = time.time()
                        upsert_visuals_to_qdrant(
                            qdrant_client,
                            parsed,
                            fname,
                            fhash,
                            workspace_id=workspace_id,
                        )
                        _record_stage_timing(stage_timings, fname, "qdrant_visuals_upsert", stage_start, report, 84)
                        total_analyzed_imgs += sum(1 for img in parsed.images if img.get("analysis_markdown"))

                if kg_mode not in ("none", "ablation"):
                    report(f"Đang trích xuất graph: {fname}", 90)
                    stage_start = time.time()
                    n_triplets = run_kg_step(chunks, parsed, fname, workspace_id=workspace_id)
                    _record_stage_timing(stage_timings, fname, "kg_extract", stage_start, report, 90)
                else:
                    n_triplets = 0

                total_dedup_chunks += len(chunks)
                total_kg_triplets  += n_triplets

                if kg_mode != "ablation":
                    report(f"Đang cập nhật registry: {fname}", 94)
                    stage_start = time.time()
                    registry_info = _build_registry_info(
                        fname,
                        fhash,
                        fsize,
                        parsed,
                        chunks,
                        n_triplets,
                        workspace_id,
                        ingest_mode=_resolve_ingest_mode_label(kg_mode, skip_visual_analysis),
                        stage_timings=stage_timings.setdefault(fname, {}),
                        embedding=_build_embedding_metrics(embed_model, model_name, file_embedding_tokens)
                        if file_embedding_tokens > 0 else None,
                    )
                    add_to_registry(registry, registry_info)
                    append_chunks_to_store(chunks, vector_dir)
                    _record_stage_timing(stage_timings, fname, "registry_store", stage_start, report, 94)
                    registry_info["processing_time_seconds"] = round(max(0.0, time.time() - file_started_at), 2)
                    registry_info["stage_timings"] = stage_timings.get(fname, {})
                    save_registry(registry, vector_dir)
                new_files.append(fname)
                report(f"Hoàn tất ingest: {fname}", 98)

            total_tables   += len(parsed.tables)
            total_images   += len(parsed.images)
            total_formulas += len(parsed.formulas)

        except Exception as e:
            print(f"[PIPELINE][ERR] {fname}: {e}")
            error_files.append(fname)

        finally:
            del parsed, doc_obj
            gc.collect()

    if not new_files and not error_files:
        elapsed = time.time() - t_start
        return {
            "status": "no_new_files",
            "new_files": new_files,
            "skipped_files": skipped_files,
            "total_files": len(file_paths),
            "total_raw_chunks": total_raw_chunks,
            "total_dedup_chunks": total_dedup_chunks,
            "total_tables": total_tables,
            "total_images": total_images,
            "total_kg_triplets": total_kg_triplets,
            "processing_time_seconds": round(elapsed, 2),
            "stage_timings": stage_timings,
            "stages": {
                "parsed": True, "chunked": True, "deduped": True,
                "embedded": False, "indexed": False, "kg_ingested": False,
            },
        }

    elapsed = time.time() - t_start

    summary = {
        "status":                    "success",
        "new_files":                 new_files,
        "skipped_files":             skipped_files,
        "error_files":               error_files,
        "total_files":               len(file_paths),
        "total_raw_chunks":          total_raw_chunks,
        "total_dedup_chunks":        total_dedup_chunks,
        "total_tables":              total_tables,
        "total_formulas":            total_formulas,
        "total_decoded_formulas":    total_decoded_formulas,
        "total_failed_formulas":     total_failed_formulas,
        "total_images":              total_images,
        "total_analyzed_images":     total_analyzed_imgs,
        "total_kg_triplets":         total_kg_triplets,
        "processing_time_seconds":   round(elapsed, 2),
        "stage_timings":             stage_timings,
        "stages": {
            "parsed":           True,
            "chunked":          True,
            "deduped":          True,
            "embedded":         total_dedup_chunks > 0,
            "indexed":          total_dedup_chunks > 0,
            "formulas_indexed": total_formulas > 0,
            "images_indexed":   total_analyzed_imgs > 0,
            "kg_ingested":      total_kg_triplets > 0,
        },
    }

    if verbose:
        print("\n" + "=" * 60)
        print("  INGEST COMPLETE")
        for k, v in summary.items():
            if k != "stages":
                print(f"  {k:<28}: {v}")
        print("=" * 60)

    return summary


def delete_document(
    file_name:  str,
    vector_dir: str = VECTOR_DIR,
    data_dir:   str = DATA_DIR,
    workspace_id: str | None = None,
    delete_kg: bool = True,
) -> Dict[str, Any]:
    """
    Xóa document khỏi Qdrant (rag_docs), registry.json, documents_store.json, Neo4j KG và file vật lý.

    Compensation strategy:
    - JSON files (registry, store) được backup trước khi sửa đổi.
      Nếu save thất bại, backup được restore để tránh corrupt data.
    - Qdrant deletion: nếu thất bại hoàn toàn thì abort sớm (không có gì đã commit).
    - Neo4j deletion: nếu thất bại sau khi Qdrant + JSON đã commit, log rõ lỗi
      và trả về partial_success để user biết cần xử lý thủ công.
    - Mỗi step failure đều được collect vào `errors` list thay vì raise exception.
    """
    print(f"[DELETE] Đang tiến hành xóa tài liệu: {file_name}")
    print(f"[DELETE] Thư mục chứa file: {data_dir}")

    errors: List[str] = []
    if not _is_safe_document_file_name(file_name):
        return {
            "status": "error",
            "file_name": file_name,
            "step": "validation",
            "message": "Invalid document file name.",
        }

    try:
        file_path = _resolve_document_delete_path(data_dir, file_name)
    except ValueError as e:
        return {
            "status": "error",
            "file_name": file_name,
            "step": "validation",
            "message": str(e),
        }

    # ── STEP 1: Qdrant (4 collections) ────────────────────────────────────────
    # Thực hiện trước: nếu thất bại ở đây thì chưa có gì committed → safe abort.
    try:
        qdrant_client  = get_qdrant_client()
        removed_counts = delete_from_qdrant(qdrant_client, file_name, workspace_id=workspace_id)
        removed_qdrant = removed_counts.get("rag_docs", 0)
        removed_qdrant_points = sum(removed_counts.values())
    except Exception as e:
        msg = f"Qdrant deletion failed: {e}"
        print(f"[DELETE][ERR] {msg}")
        return {
            "status":    "error",
            "file_name": file_name,
            "step":      "qdrant",
            "message":   msg,
        }

    # ── STEP 2: Registry JSON — backup trước, restore nếu save fail ───────────
    registry_backup = load_registry(vector_dir)
    registry        = {k: list(v) if isinstance(v, list) else v
                       for k, v in registry_backup.items()}
    old_docs         = registry.get("documents", [])
    new_docs         = [d for d in old_docs if d.get("file_name") != file_name]
    removed_registry = len(old_docs) - len(new_docs)
    registry["documents"] = new_docs
    try:
        save_registry(registry, vector_dir)
    except Exception as e:
        # Qdrant đã xóa, nhưng registry chưa được cập nhật → restore JSON.
        save_registry(registry_backup, vector_dir)
        msg = f"Registry save failed (restored backup). Qdrant deletion committed. {e}"
        print(f"[DELETE][ERR] {msg}")
        errors.append(msg)

    # ── STEP 3: Doc store JSON — backup trước, restore nếu save fail ──────────
    store_backup = load_doc_store(vector_dir)
    store        = {k: list(v) if isinstance(v, list) else v
                    for k, v in store_backup.items()}
    old_store    = store.get("documents", [])
    new_store    = [d for d in old_store if d.get("metadata", {}).get("file_name") != file_name]
    removed_store = len(old_store) - len(new_store)
    store["documents"] = new_store
    try:
        save_doc_store(store, vector_dir)
    except Exception as e:
        save_doc_store(store_backup, vector_dir)
        msg = f"Doc store save failed (restored backup). {e}"
        print(f"[DELETE][ERR] {msg}")
        errors.append(msg)

    # ── STEP 4: Visual asset files ────────────────────────────────────────────
    removed_visual_assets = 0
    try:
        removed_visual_assets = delete_visual_assets_for_file(
            file_name,
            vector_dir,
            registry_backup,
            store_backup,
        )
    except Exception as e:
        msg = f"Visual asset cleanup failed: {e}"
        print(f"[DELETE][WARN] {msg}")
        errors.append(msg)

    # ── STEP 5: Neo4j KG ──────────────────────────────────────────────────────
    # Qdrant + JSON đã committed. Nếu Neo4j thất bại, log rõ để user xử lý thủ công.
    removed_kg = 0
    try:
        removed_kg = _delete_document_kg_if_enabled(
            file_name,
            workspace_id=workspace_id or "default",
            delete_kg=delete_kg,
        )
    except Exception as e:
        msg = (
            f"Neo4j KG deletion failed: {e}. "
            f"Qdrant + registry already committed. "
            f"Run manually: MATCH ()-[r:RELATES_TO {{source: '{file_name}'}}]->() DELETE r"
        )
        print(f"[DELETE][ERR] {msg}")
        errors.append(msg)

    # ── STEP 6: Physical file (best-effort) ───────────────────────────────────
    removed_file = False
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            removed_file = True
        except Exception as e:
            msg = f"Physical file deletion failed: {e}"
            print(f"[DELETE][WARN] {msg}")
            errors.append(msg)

    # ── STEP 7: Semantic cache ────────────────────────────────────────────────
    removed_cache_entries = 0
    try:
        from query.cache import clear_cache_entries
        removed_cache_entries = clear_cache_entries(workspace_id=workspace_id, file_name=file_name)
    except Exception as e:
        msg = f"Semantic cache cleanup failed: {e}"
        print(f"[DELETE][WARN] {msg}")
        errors.append(msg)

    if removed_registry == 0 and removed_qdrant_points == 0 and not removed_file and removed_visual_assets == 0:
        return {
            "status":    "not_found",
            "file_name": file_name,
            "message":   f"Không tìm thấy '{file_name}' trong hệ thống.",
        }

    status = "deleted" if not errors else "partial_success"
    result: Dict[str, Any] = {
        "status":                   status,
        "file_name":                file_name,
        "removed_qdrant_chunks":    removed_qdrant,
        "removed_qdrant_points":    removed_qdrant_points,
        "removed_store_chunks":     removed_store,
        "removed_registry_entries": removed_registry,
        "removed_visual_assets":    removed_visual_assets,
        "removed_kg_edges":         removed_kg,
        "removed_semantic_cache_entries": removed_cache_entries,
        "removed_physical_file":    removed_file,
        "message":                  f"Đã xóa '{file_name}' khỏi Qdrant, registry, store, visual assets, semantic cache, Neo4j KG và file vật lý.",
    }
    if errors:
        result["errors"]  = errors
        result["message"] = f"Xóa một phần '{file_name}'. Một số bước thất bại — xem 'errors' để biết chi tiết."
    return result


def reset_system(vector_dir: str = VECTOR_DIR, data_dir: str = DATA_DIR) -> Dict[str, Any]:
    """
    Xóa sạch toàn bộ: Qdrant collections, Neo4j graph, registry, doc store và folder data.
    """
    print("\n" + "!" * 60)
    print("  DANG XOA TOAN BO DU LIEU HE THONG...")
    print("!" * 60)

    # 1. Qdrant
    qdrant_client = get_qdrant_client()
    collections = ["rag_docs", "rag_visuals", "rag_tables", "rag_formulas", "rag_images"]
    removed_cols = []
    for col in collections:
        try:
            if qdrant_client.collection_exists(col):
                qdrant_client.delete_collection(col)
                removed_cols.append(col)
        except Exception as e:
            print(f"[RESET][WARN] Qdrant {col}: {e}")

    # 2. Neo4j
    removed_kg = False
    try:
        from neo4j import GraphDatabase
        from kg_neo4j import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD
        with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)) as driver:
            with driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
                removed_kg = True
    except Exception as e:
        print(f"[RESET][WARN] Neo4j: {e}")

    # 3. Local Registry & Store
    files_removed = []
    for f in ["registry.json", "documents_store.json"]:
        path = os.path.join(vector_dir, f)
        if os.path.exists(path):
            os.remove(path)
            files_removed.append(f)

    # 4. Data folder (optional but recommended for full reset)
    data_files_removed = 0
    if os.path.exists(data_dir):
        for f in os.listdir(data_dir):
            path = os.path.join(data_dir, f)
            if os.path.isfile(path):
                try:
                    os.remove(path)
                    data_files_removed += 1
                except: pass

    return {
        "status": "reset_complete",
        "deleted_qdrant_collections": removed_cols,
        "cleared_neo4j": removed_kg,
        "deleted_registry_files": files_removed,
        "deleted_data_files": data_files_removed,
        "message": "He thong da duoc lam sach hoan toan."
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest Pipeline v4 — Qdrant + Neo4j backend"
    )
    parser.add_argument("--data",       default=DATA_DIR,    help="Folder chứa tài liệu")
    parser.add_argument("--vector-dir", default=VECTOR_DIR,  help="Folder lưu registry")
    parser.add_argument("--model",      default=EMBED_MODEL, help="Embedding model name")
    parser.add_argument("--action",     default="ingest",    choices=["ingest", "list", "delete", "reset"])
    parser.add_argument("--file-name",  default="",          help="Tên file cần xóa")
    parser.add_argument("--force",      action="store_true", help="Ingest lại dù đã có")
    parser.add_argument(
        "--kg-mode",
        default="light",
        choices=["none", "light", "full", "ablation"],
        help="KG extraction mode: none|light|full|ablation",
    )

    args = parser.parse_args()

    if args.action == "ingest":
        result = offline_ingest(
            data_dir=args.data,
            vector_dir=args.vector_dir,
            model_name=args.model,
            force=args.force,
            kg_mode=args.kg_mode,
        )
        print("\n[RESULT]")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.action == "list":
        docs = list_ingested_documents(args.vector_dir)
        if not docs:
            print("[LIST] Chưa có tài liệu nào được ingest.")
        else:
            print(f"[LIST] {len(docs)} tài liệu đã ingest:")
            print(json.dumps(docs, indent=2, ensure_ascii=False))

    elif args.action == "delete":
        if not args.file_name:
            parser.error("--file-name là bắt buộc khi dùng --action delete")
        result = delete_document(file_name=args.file_name, vector_dir=args.vector_dir, data_dir=args.data)
        print("\n[RESULT]")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.action == "reset":
        confirm = input("⚠️  Ban co chac chan muon xoa TOAN BO du lieu khong? (y/n): ")
        if confirm.lower() == 'y':
            result = reset_system(vector_dir=args.vector_dir, data_dir=args.data)
            print("\n[RESULT]")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("Huy bo lenh reset.")


if __name__ == "__main__":
    main()
