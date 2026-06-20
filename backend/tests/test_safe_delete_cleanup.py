from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_clear_cache_entries_removes_scoped_and_legacy_entries(tmp_path, monkeypatch):
    from query import cache

    cache_file = tmp_path / "semantic_cache.json"
    cache_file.write_text(
        json.dumps(
            [
                {
                    "question": "scoped paper",
                    "answer": "old answer",
                    "embedding": [0.1],
                    "workspace_id": "workspace-a",
                    "file_names": ["paper.pdf"],
                },
                {
                    "question": "legacy unscoped",
                    "answer": "legacy answer",
                    "embedding": [0.2],
                },
                {
                    "question": "other workspace",
                    "answer": "keep answer",
                    "embedding": [0.3],
                    "workspace_id": "workspace-b",
                    "file_names": ["other.pdf"],
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cache, "CACHE_FILE", str(cache_file))

    removed = cache.clear_cache_entries(workspace_id="workspace-a", file_name="paper.pdf")

    remaining = json.loads(cache_file.read_text(encoding="utf-8"))
    assert removed == 2
    assert [entry["question"] for entry in remaining] == ["other workspace"]


def test_delete_visual_assets_for_file_removes_global_and_workspace_assets(tmp_path, monkeypatch):
    from ingest import pipeline

    global_db = tmp_path / "global-db"
    workspace_db = tmp_path / "workspace-db"
    monkeypatch.setattr(pipeline, "VECTOR_DIR", str(global_db))

    global_asset = global_db / "assets" / "hash-a" / "image" / "IMG-a.png"
    workspace_asset = workspace_db / "assets" / "hash-a" / "formula" / "FORM-a.png"
    metadata_asset = global_db / "assets" / "hash-a" / "table" / "TBL-a.png"
    unrelated_asset = global_db / "assets" / "hash-b" / "image" / "IMG-b.png"
    for path in [global_asset, workspace_asset, metadata_asset, unrelated_asset]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")

    registry = {
        "documents": [
            {"file_name": "paper.pdf", "file_hash": "hash-a"},
            {"file_name": "other.pdf", "file_hash": "hash-b"},
        ]
    }
    store = {
        "documents": [
            {
                "metadata": {
                    "file_name": "paper.pdf",
                    "visual_assets": json.dumps([{"path": str(metadata_asset)}]),
                }
            }
        ]
    }

    removed = pipeline.delete_visual_assets_for_file(
        "paper.pdf",
        str(workspace_db),
        registry,
        store,
    )

    assert removed == 3
    assert not global_asset.exists()
    assert not workspace_asset.exists()
    assert not metadata_asset.exists()
    assert unrelated_asset.exists()
