import asyncio
from unittest.mock import patch

import main
from schemas import WorkspaceInfo


def test_default_workspace_strategy_is_vector_visuals():
    workspaces = main._load_workspaces()
    default = next(item for item in workspaces if item.id == "default")

    assert default.strategy == "only_vector_multimodal"
    assert default.isSetupComplete is True


def test_ingest_strategy_comes_from_workspace_not_request_mode():
    workspace = WorkspaceInfo(
        id="vector_ws",
        name="Vector Workspace",
        description="Vector workspace",
        strategy="only_vector_multimodal",
        created_at="2026-06-09T00:00:00",
        updated_at="2026-06-09T00:00:00",
    )

    with patch.object(main, "_load_workspaces", return_value=[workspace]):
        settings = main._resolve_workspace_ingest_settings(
            workspace_id="vector_ws",
            requested_ingest_mode="hybrid",
        )

    assert settings["effective_strategy"] == "only_vector_multimodal"
    assert settings["kg_mode"] == "none"
    assert settings["skip_visual_analysis"] is False


def test_hybrid_workspace_enables_graph_and_visuals_without_rerank():
    workspace = WorkspaceInfo(
        id="hybrid_ws",
        name="Hybrid Workspace",
        description="Hybrid workspace",
        strategy="hybrid",
        created_at="2026-06-09T00:00:00",
        updated_at="2026-06-09T00:00:00",
    )

    with patch.object(main, "_load_workspaces", return_value=[workspace]):
        settings = main._resolve_workspace_query_settings(
            workspace_id="hybrid_ws",
            requested_query_mode="only_vector_multimodal",
        )

    assert settings["effective_strategy"] == "hybrid"
    assert settings["kg_mode"] == "default"
    assert settings["use_rerank"] is False
    assert settings["use_visuals"] is True


def test_vector_visuals_query_ignores_requested_hybrid_mode():
    workspace = WorkspaceInfo(
        id="vector_ws",
        name="Vector Workspace",
        description="Vector workspace",
        strategy="only_vector_multimodal",
        created_at="2026-06-09T00:00:00",
        updated_at="2026-06-09T00:00:00",
    )

    with patch.object(main, "_load_workspaces", return_value=[workspace]):
        settings = main._resolve_workspace_query_settings(
            workspace_id="vector_ws",
            requested_query_mode="hybrid",
        )

    assert settings["effective_strategy"] == "only_vector_multimodal"
    assert settings["kg_mode"] == "vector"
    assert settings["use_rerank"] is False
    assert settings["use_visuals"] is True


def test_hybrid_ingest_ignores_requested_vector_visuals_mode():
    workspace = WorkspaceInfo(
        id="hybrid_ws",
        name="Hybrid Workspace",
        description="Hybrid workspace",
        strategy="hybrid",
        created_at="2026-06-09T00:00:00",
        updated_at="2026-06-09T00:00:00",
    )

    with patch.object(main, "_load_workspaces", return_value=[workspace]):
        settings = main._resolve_workspace_ingest_settings(
            workspace_id="hybrid_ws",
            requested_ingest_mode="only_vector_multimodal",
        )

    assert settings["effective_strategy"] == "hybrid"
    assert settings["kg_mode"] == "light"
    assert settings["skip_visual_analysis"] is False


def test_pre_created_workspace_can_set_final_strategy_during_setup():
    existing = WorkspaceInfo(
        id="draft_ws",
        name="Draft Workspace",
        description="Draft workspace",
        strategy="only_vector_multimodal",
        isSetupComplete=False,
        created_at="2026-06-09T00:00:00",
        updated_at="2026-06-09T00:00:00",
    )
    incoming = WorkspaceInfo(
        id="draft_ws",
        name="Hybrid Workspace",
        description="Ready workspace",
        strategy="hybrid",
        isSetupComplete=True,
        created_at="2026-06-09T00:00:00",
        updated_at="2026-06-09T01:00:00",
    )
    saved = {}

    def capture_save(workspaces):
        saved["workspaces"] = workspaces

    with patch.object(main, "_load_workspaces", return_value=[existing]):
        with patch.object(main, "_save_workspaces", side_effect=capture_save):
            updated = asyncio.run(main.update_workspace("draft_ws", incoming))

    assert updated.name == "Hybrid Workspace"
    assert updated.strategy == "hybrid"
    assert updated.isSetupComplete is True
    assert saved["workspaces"][0].strategy == "hybrid"
    assert saved["workspaces"][0].isSetupComplete is True


def test_completed_workspace_update_preserves_existing_strategy():
    existing = WorkspaceInfo(
        id="hybrid_ws",
        name="Hybrid Workspace",
        description="Hybrid workspace",
        strategy="hybrid",
        isSetupComplete=True,
        created_at="2026-06-09T00:00:00",
        updated_at="2026-06-09T00:00:00",
    )
    incoming = WorkspaceInfo(
        id="hybrid_ws",
        name="Renamed Workspace",
        description="Updated description",
        strategy="only_vector_multimodal",
        isSetupComplete=True,
        created_at="2026-06-09T00:00:00",
        updated_at="2026-06-09T01:00:00",
    )
    saved = {}

    def capture_save(workspaces):
        saved["workspaces"] = workspaces

    with patch.object(main, "_load_workspaces", return_value=[existing]):
        with patch.object(main, "_save_workspaces", side_effect=capture_save):
            updated = asyncio.run(main.update_workspace("hybrid_ws", incoming))

    assert updated.name == "Renamed Workspace"
    assert updated.strategy == "hybrid"
    assert updated.isSetupComplete is True
    assert saved["workspaces"][0].strategy == "hybrid"


def test_document_delete_kg_cleanup_can_be_skipped(monkeypatch):
    from ingest import pipeline

    called = []
    monkeypatch.setattr(
        pipeline,
        "delete_document_kg",
        lambda file_name, workspace_id="default": called.append((file_name, workspace_id)) or 1,
    )

    removed = pipeline._delete_document_kg_if_enabled(
        file_name="paper.pdf",
        workspace_id="vector_ws",
        delete_kg=False,
    )

    assert removed == 0
    assert called == []


def test_query_runtime_settings_are_clamped_by_backend():
    from schemas import ChatRequest

    req = ChatRequest(
        question="What is this paper about?",
        qdrant_limit=999,
        score_threshold=-5,
        max_context_chunks=99,
        temperature=2.0,
        max_output_tokens=100000,
        max_input_tokens=100000,
    )

    qdrant_limit, score_threshold, max_context_chunks = main._resolve_retrieval_settings(req)
    generation = main._resolve_generation_settings(req)

    assert qdrant_limit == 80
    assert score_threshold == 0.0
    assert max_context_chunks == 12
    assert generation == {
        "temperature": 0.7,
        "max_output_tokens": 2048,
        "max_input_tokens": 16000,
    }


def test_query_runtime_settings_keep_safe_requested_values():
    from schemas import ChatRequest

    req = ChatRequest(
        question="Summarize the method.",
        qdrant_limit=24,
        score_threshold=0.35,
        max_context_chunks=6,
        temperature=0.2,
        max_output_tokens=768,
        max_input_tokens=6000,
    )

    qdrant_limit, score_threshold, max_context_chunks = main._resolve_retrieval_settings(req)
    generation = main._resolve_generation_settings(req)

    assert qdrant_limit == 24
    assert score_threshold == 0.35
    assert max_context_chunks == 6
    assert generation == {
        "temperature": 0.2,
        "max_output_tokens": 768,
        "max_input_tokens": 6000,
    }
