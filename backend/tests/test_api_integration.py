"""
Integration contract tests for FastAPI route ordering and frontend source URLs.

These tests avoid Qdrant/Neo4j/OpenAI calls. They protect the frontend-backend
contract that broke when the React SPA was mounted before /api routes.
"""

from __future__ import annotations

import os
import sys
import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main as main_module  # noqa: E402
from main import _build_sources, _sse_generator, app  # noqa: E402
from schemas import ChatRequest, WorkspaceInfo  # noqa: E402


def test_api_health_is_not_shadowed_by_spa_mount_when_dist_exists():
    """API routes must stay reachable even when frontend/react-app/dist exists."""
    dist = Path(__file__).resolve().parents[2] / "frontend" / "react-app" / "dist"
    assert dist.exists(), "This regression only applies when the production SPA build exists."

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_build_sources_uses_default_data_url_for_default_workspace():
    sources = _build_sources(
        [{"id": 1, "file_name": "paper.pdf", "page": 3, "score": 0.91}],
        base_url="http://localhost:8000",
        workspace_id="default",
    )

    assert sources[0].pdf_url == "http://localhost:8000/data/paper.pdf"


def test_build_sources_url_encodes_file_names():
    sources = _build_sources(
        [{"id": 1, "file_name": "PB NOMA paper.pdf", "page": 3, "score": 0.91}],
        base_url="http://localhost:8000",
        workspace_id="default",
    )

    assert sources[0].pdf_url == "http://localhost:8000/data/PB%20NOMA%20paper.pdf"


def test_build_sources_uses_workspace_data_url_for_non_default_workspace():
    sources = _build_sources(
        [{"id": 1, "file_name": "paper.pdf", "page": 3, "score": 0.91}],
        base_url="http://localhost:8000",
        workspace_id="Research Space/../A",
    )

    assert sources[0].pdf_url == "http://localhost:8000/workspace-data/ResearchSpaceA/data/paper.pdf"


def test_build_sources_derives_asset_url_from_backend_db_asset_path():
    sources = _build_sources(
        [{
            "id": 1,
            "file_name": "paper.pdf",
            "page": 3,
            "score": 0.91,
            "kind": "image",
            "visual_id": "img_3_1",
            "asset_path": r"C:\repo\backend\db\assets\hash\images\img_3_1.png",
        }],
        base_url="http://localhost:8000",
        workspace_id="default",
    )

    assert sources[0].asset_url == "http://localhost:8000/assets/hash/images/img_3_1.png"


def test_sse_generator_disables_global_semantic_cache(monkeypatch):
    captured = {}

    def fake_rag_prepare(*args):
        captured["use_cache"] = args[4]
        return {"cache_hit": False, "error": "stop after retrieval", "kg_context": ""}

    monkeypatch.setattr("main._get_rag_prepare", lambda: fake_rag_prepare)
    monkeypatch.setattr("main._workspace_file_names", lambda workspace_id: ["paper.pdf"])

    async def collect_events():
        req = ChatRequest(question="What is PB-NOMA?", workspace_id="default", use_cache=False)
        events = []
        async for event in _sse_generator(req, "http://localhost:8000"):
            events.append(event)
            if '"type": "error"' in event:
                break
        return events

    events = asyncio.run(collect_events())

    assert captured["use_cache"] is False
    assert any('"type": "error"' in event for event in events)


def test_sse_generator_short_circuits_plain_greeting(monkeypatch):
    def fail_rag_prepare():
        raise AssertionError("Greeting should not enter the RAG retrieval pipeline.")

    monkeypatch.setattr("main._get_rag_prepare", fail_rag_prepare)

    async def collect_events():
        req = ChatRequest(question="HI", workspace_id="default")
        events = []
        async for event in _sse_generator(req, "http://localhost:8000"):
            events.append(event)
            if '"type": "done"' in event:
                break
        return events

    events = asyncio.run(collect_events())

    assert any('"type": "token"' in event for event in events)
    assert any('"type": "done"' in event for event in events)
    assert not any('"Đang tìm kiếm..."' in event for event in events)


def test_sse_generator_emits_user_facing_research_trace(monkeypatch):
    def fake_rag_prepare(*_args):
        return {"cache_hit": False, "error": "stop after retrieval", "kg_context": ""}

    monkeypatch.setattr("main._get_rag_prepare", lambda: fake_rag_prepare)
    monkeypatch.setattr("main._workspace_file_names", lambda workspace_id: ["paper.pdf"])

    async def collect_events():
        req = ChatRequest(question="What is PB-NOMA?", workspace_id="default")
        events = []
        async for event in _sse_generator(req, "http://localhost:8000"):
            events.append(event)
            if '"type": "error"' in event:
                break
        return events

    events = asyncio.run(collect_events())
    payload = "\n".join(events)

    assert "Analyzing question" in payload
    assert "Searching workspace evidence" in payload
    assert "Workspace:" not in payload


def test_sse_generator_sends_heartbeat_during_slow_retrieval(monkeypatch):
    def slow_rag_prepare(*_args):
        time.sleep(0.05)
        return {"cache_hit": False, "error": "stop after retrieval", "kg_context": ""}

    monkeypatch.setattr(main_module, "SSE_HEARTBEAT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr("main._get_rag_prepare", lambda: slow_rag_prepare)
    monkeypatch.setattr("main._workspace_file_names", lambda workspace_id: ["paper.pdf"])

    async def collect_events():
        req = ChatRequest(question="What is PB-NOMA?", workspace_id="default")
        events = []
        async for event in _sse_generator(req, "http://localhost:8000"):
            events.append(event)
            if '"type": "error"' in event:
                break
        return events

    events = asyncio.run(collect_events())

    assert any(event == ": heartbeat\n\n" for event in events)
    assert any('"type": "error"' in event for event in events)


def test_sse_done_emits_kg_sources(monkeypatch):
    class FakeDelta:
        content = "Answer"

    class FakeChoice:
        delta = FakeDelta()

    class FakeChunk:
        choices = [FakeChoice()]

    class FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if getattr(self, "_sent", False):
                raise StopAsyncIteration
            self._sent = True
            return FakeChunk()

    class FakeCompletions:
        async def create(self, **_kwargs):
            return FakeStream()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        chat = FakeChat()

    def fake_rag_prepare(*_args):
        return {
            "cache_hit": False,
            "kg_context": "KG context",
            "kg_sources": [{
                "id": "KG-01",
                "subject": "PB-NOMA",
                "relation": "IMPROVES",
                "object": "spectral efficiency",
                "has_document_evidence": True,
            }],
            "retrieval_trace": {"context_used": {"kg": True}},
            "sources_structured": [],
            "system_prompt": "You are grounded.",
            "user_prompt": "Question",
            "use_cache": False,
        }

    monkeypatch.setattr("main._get_rag_prepare", lambda: fake_rag_prepare)
    monkeypatch.setattr("main._workspace_file_names", lambda workspace_id: ["paper.pdf"])
    monkeypatch.setattr(main_module, "_async_openai", FakeOpenAI())

    async def collect_done_payload():
        req = ChatRequest(question="Explain PB-NOMA graph evidence.", workspace_id="default")
        async for event in _sse_generator(req, "http://localhost:8000"):
            if '"type": "done"' in event:
                return event
        return ""

    payload = asyncio.run(collect_done_payload())

    assert '"kg_sources"' in payload
    assert "KG-01" in payload
    assert '"context_used"' in payload


def test_sse_generator_enforces_max_input_tokens_before_openai(monkeypatch):
    captured = {}

    class FakeDelta:
        content = "Answer"

    class FakeChoice:
        delta = FakeDelta()

    class FakeChunk:
        choices = [FakeChoice()]

    class FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if getattr(self, "_sent", False):
                raise StopAsyncIteration
            self._sent = True
            return FakeChunk()

    class FakeCompletions:
        async def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return FakeStream()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        chat = FakeChat()

    def fake_rag_prepare(*_args):
        long_context = "expensive context token " * 2000
        return {
            "cache_hit": False,
            "kg_context": "",
            "kg_sources": [],
            "retrieval_trace": {"settings": {}},
            "sources_structured": [],
            "system_prompt": "Short system prompt.",
            "user_prompt": f"Context:\n{long_context}\n\nQuestion: What is PB-NOMA?",
            "use_cache": False,
        }

    monkeypatch.setattr("main._get_rag_prepare", lambda: fake_rag_prepare)
    monkeypatch.setattr("main._workspace_file_names", lambda workspace_id: ["paper.pdf"])
    monkeypatch.setattr(main_module, "_async_openai", FakeOpenAI())

    async def collect_done_payload():
        req = ChatRequest(
            question="What is PB-NOMA?",
            workspace_id="default",
            max_input_tokens=2048,
        )
        async for event in _sse_generator(req, "http://localhost:8000"):
            if '"type": "done"' in event:
                return event
        return ""

    payload = asyncio.run(collect_done_payload())
    messages = captured["kwargs"]["messages"]
    input_tokens = main_module._count_chat_input_tokens(messages)

    assert input_tokens <= 2048
    assert "What is PB-NOMA?" in messages[1]["content"]
    assert len(messages[1]["content"]) < len(fake_rag_prepare()["user_prompt"])
    assert '"max_input_tokens": 2048' in payload


def test_ingest_rejects_unsupported_upload_extension():
    response = TestClient(app).post(
        "/api/ingest",
        files={"file": ("notes.txt", b"plain text is not supported", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_ingest_accepts_supported_upload_in_workspace(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    db_dir = tmp_path / "db"

    def fake_workspace_paths(workspace_id):
        data_dir.mkdir(parents=True, exist_ok=True)
        db_dir.mkdir(parents=True, exist_ok=True)
        return str(data_dir), str(db_dir)

    def fake_run_ingest(*_args, **_kwargs):
        main_module._active_task = None

    monkeypatch.setattr(main_module, "_workspace_paths", fake_workspace_paths)
    monkeypatch.setattr(main_module, "_run_ingest", fake_run_ingest)
    monkeypatch.setattr(main_module, "_active_task", None)

    response = TestClient(app).post(
        "/api/ingest?workspace_id=research",
        files={"file": ("paper.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["file_name"] == "paper.pdf"
    assert (data_dir / "paper.pdf").exists()


def test_run_ingest_records_actual_elapsed_and_stage_timings(monkeypatch, tmp_path):
    task_id = "timed-task"
    data_dir = tmp_path / "data"
    db_dir = tmp_path / "db"
    data_dir.mkdir()
    db_dir.mkdir()

    def fake_offline_ingest(**_kwargs):
        time.sleep(0.001)
        return {
            "status": "success",
            "new_files": ["paper.pdf"],
            "stage_timings": {
                "paper.pdf": {
                    "parse_layout": 1.25,
                    "embedding": 0.5,
                    "qdrant_docs_upsert": 0.125,
                }
            },
        }

    monkeypatch.setattr(main_module, "_get_offline_ingest", lambda: fake_offline_ingest)
    monkeypatch.setattr(main_module, "_active_task", task_id)
    monkeypatch.setattr(main_module, "_umap_cache", {"default": {"data": []}})
    monkeypatch.setattr(main_module, "_tasks", {
        task_id: main_module.TaskStatus(
            task_id=task_id,
            status="queued",
            progress=0,
            current_step="Chờ xử lý",
            logs=[],
        )
    })

    main_module._run_ingest(
        str(data_dir / "paper.pdf"),
        "paper.pdf",
        task_id,
        str(data_dir),
        str(db_dir),
        "only_vector_multimodal",
        "default",
    )

    status = main_module._tasks[task_id]
    assert status.status == "done"
    assert status.started_at is not None
    assert status.completed_at is not None
    assert status.elapsed_ms is not None
    assert status.elapsed_ms >= 1
    assert status.stage_timings_ms == {
        "paper.pdf": {
            "parse_layout": 1250,
            "embedding": 500,
            "qdrant_docs_upsert": 125,
        }
    }


def test_documents_api_exposes_persisted_ingest_metrics(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    db_dir = tmp_path / "db"
    data_dir.mkdir()
    db_dir.mkdir()
    (data_dir / "paper.pdf").write_bytes(b"%PDF-1.4 fake")

    def fake_workspace_paths(workspace_id):
        assert workspace_id == "fast_ws"
        return str(data_dir), str(db_dir)

    def fake_list_documents(_db_dir):
        return [{
            "file_name": "paper.pdf",
            "file_hash": "hash",
            "ingested_at": "2026-06-12T10:00:00",
            "total_pages": 2,
            "total_dedup_chunks": 7,
            "total_tables": 2,
            "total_formulas": 2,
            "total_images": 3,
            "ingest_mode": "only_vector_fast",
            "processing_time_seconds": 53.05,
            "stage_timings": {"embedding": 3.55},
            "embedding": {
                "model": "text-embedding-3-small",
                "input_tokens": 4093,
                "price_per_1m_tokens": 0.02,
                "cost_usd": 0.00008186,
            },
        }]

    monkeypatch.setattr(main_module, "_workspace_paths", fake_workspace_paths)
    monkeypatch.setattr(main_module, "_get_list_documents", lambda: fake_list_documents)

    response = TestClient(app).get("/api/documents?workspace_id=fast_ws")

    assert response.status_code == 200
    doc = response.json()[0]
    assert doc["file_name"] == "paper.pdf"
    assert doc["chunk_count"] == 7
    assert doc["ingest_mode"] == "only_vector_fast"
    assert doc["processing_time_seconds"] == 53.05
    assert doc["stage_timings"] == {"embedding": 3.55}
    assert doc["embedding"]["model"] == "text-embedding-3-small"
    assert doc["embedding"]["input_tokens"] == 4093
    assert doc["embedding"]["cost_usd"] == 0.00008186
    assert doc["total_tables"] == 2
    assert doc["total_formulas"] == 2
    assert doc["total_images"] == 3


def test_graph_api_defaults_to_entity_first(monkeypatch):
    captured = {}

    def fake_graph(limit=200, source_files=None, workspace_id="default", include_chunks=False):
        captured["limit"] = limit
        captured["source_files"] = source_files
        captured["workspace_id"] = workspace_id
        captured["include_chunks"] = include_chunks
        return {"nodes": [], "edges": []}

    monkeypatch.setattr(main_module, "_workspace_file_names", lambda workspace_id: ["paper.pdf"])
    monkeypatch.setattr(main_module, "_get_graph_for_viz", lambda: fake_graph)

    response = TestClient(app).get("/api/graph?workspace_id=research")

    assert response.status_code == 200
    assert captured == {
        "limit": 300,
        "source_files": ["paper.pdf"],
        "workspace_id": "research",
        "include_chunks": False,
    }


def test_graph_api_passes_include_chunks_when_requested(monkeypatch):
    captured = {}

    def fake_graph(limit=200, source_files=None, workspace_id="default", include_chunks=False):
        captured["include_chunks"] = include_chunks
        return {"nodes": [], "edges": []}

    monkeypatch.setattr(main_module, "_workspace_file_names", lambda workspace_id: ["paper.pdf"])
    monkeypatch.setattr(main_module, "_get_graph_for_viz", lambda: fake_graph)

    response = TestClient(app).get("/api/graph?workspace_id=research&include_chunks=true")

    assert response.status_code == 200
    assert captured["include_chunks"] is True


def test_graph_endpoint_filters_neo4j_by_workspace_files(monkeypatch):
    captured = {}

    def fake_graph(limit, source_files, workspace_id, include_chunks=False):
        captured["limit"] = limit
        captured["source_files"] = source_files
        captured["workspace_id"] = workspace_id
        captured["include_chunks"] = include_chunks
        return {
            "nodes": [{"id": "a", "label": "A", "type": "Concept", "mentions": 1, "degree": 1}],
            "edges": [{
                "from": "a",
                "to": "b",
                "relation": "USES",
                "weight": 0.8,
                "source_file": "paper.pdf",
                "page": 2,
                "chunk_ids": ["c1"],
                "evidence_preview": "A uses B.",
            }],
        }

    monkeypatch.setattr(main_module, "_workspace_file_names", lambda workspace_id: ["paper.pdf"])
    monkeypatch.setattr(main_module, "_get_graph_for_viz", lambda: fake_graph)

    response = TestClient(app).get("/api/graph?workspace_id=research")

    assert response.status_code == 200
    assert captured == {
        "limit": 300,
        "source_files": ["paper.pdf"],
        "workspace_id": "research",
        "include_chunks": False,
    }
    body = response.json()
    assert body["edges"][0]["source"] == "a"
    assert body["edges"][0]["target"] == "b"
    assert body["edges"][0]["source_file"] == "paper.pdf"
    assert body["edges"][0]["chunk_ids"] == ["c1"]


def test_delete_hybrid_workspace_passes_workspace_id_to_neo4j_cleanup(monkeypatch):
    captured = []

    monkeypatch.setattr(
        main_module,
        "_load_workspaces",
        lambda: [
            WorkspaceInfo(
                id="review-space",
                name="Review Space",
                icon="RS",
                collectionName="review",
                systemPrompt="",
                strategy="hybrid",
                createdAt="2026-01-01T00:00:00",
            )
        ],
    )
    monkeypatch.setattr(main_module, "_save_workspaces", lambda workspaces: None)
    monkeypatch.setattr(main_module, "_workspace_file_names", lambda workspace_id: ["paper.pdf"])

    import kg_neo4j_ops
    import query.clients
    import ingest.vector_store

    def fake_delete_document_kg(file_name, workspace_id="default"):
        captured.append((file_name, workspace_id))
        return 1

    monkeypatch.setattr(kg_neo4j_ops, "delete_document_kg", fake_delete_document_kg)
    monkeypatch.setattr(query.clients, "get_qdrant_client", lambda: object())
    monkeypatch.setattr(ingest.vector_store, "delete_workspace_from_qdrant", lambda client, workspace_id: None)
    monkeypatch.setattr(main_module, "_delete_remaining_workspace_graph", lambda workspace_id: {"nodes": 0, "relationships": 0})

    response = TestClient(app).delete("/api/workspaces/review-space")

    assert response.status_code == 200
    assert captured == [("paper.pdf", "review-space")]


def test_delete_vector_visuals_workspace_skips_neo4j_cleanup(monkeypatch):
    captured = {"document": [], "leftover": []}

    monkeypatch.setattr(
        main_module,
        "_load_workspaces",
        lambda: [
            WorkspaceInfo(
                id="vector-space",
                name="Vector Space",
                icon="VS",
                collectionName="vector",
                systemPrompt="",
                strategy="only_vector_multimodal",
                createdAt="2026-01-01T00:00:00",
            )
        ],
    )
    monkeypatch.setattr(main_module, "_save_workspaces", lambda workspaces: None)
    monkeypatch.setattr(main_module, "_workspace_file_names", lambda workspace_id: ["paper.pdf"])

    import kg_neo4j_ops
    import query.clients
    import ingest.vector_store

    monkeypatch.setattr(
        kg_neo4j_ops,
        "delete_document_kg",
        lambda file_name, workspace_id="default": captured["document"].append((file_name, workspace_id)) or 1,
    )
    monkeypatch.setattr(query.clients, "get_qdrant_client", lambda: object())
    monkeypatch.setattr(ingest.vector_store, "delete_workspace_from_qdrant", lambda client, workspace_id: None)
    monkeypatch.setattr(
        main_module,
        "_delete_remaining_workspace_graph",
        lambda workspace_id: captured["leftover"].append(workspace_id) or {"nodes": 0, "relationships": 0},
    )

    response = TestClient(app).delete("/api/workspaces/vector-space")

    assert response.status_code == 200
    assert captured == {"document": [], "leftover": []}


def test_delete_workspace_allows_orphan_workspace_cleanup(monkeypatch, tmp_path):
    """A browser-local workspace may have data even when workspaces.json lost it."""
    wid = "workspace-orphan"
    root = tmp_path / wid
    data_dir = root / "data"
    db_dir = root / "db"
    data_dir.mkdir(parents=True)
    db_dir.mkdir(parents=True)
    (data_dir / "paper.pdf").write_bytes(b"%PDF-1.4\n%%EOF")

    monkeypatch.setattr(main_module, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(main_module, "WORKSPACE_FILE", tmp_path / "workspaces.json")
    monkeypatch.setattr(
        main_module,
        "_load_workspaces",
        lambda: [
            WorkspaceInfo(
                id="default",
                name="General Science",
                icon="SR",
                collectionName="scientific_papers",
                systemPrompt="",
                createdAt="2026-01-01T00:00:00",
            )
        ],
    )
    monkeypatch.setattr(main_module, "_save_workspaces", lambda workspaces: None)
    monkeypatch.setattr(main_module, "_workspace_file_names", lambda workspace_id: ["paper.pdf"])

    import ingest.pipeline
    import ingest.registry
    import ingest.vector_store
    import kg_neo4j_ops
    import query.cache
    import query.clients

    captured = {"qdrant": "", "kg": []}

    monkeypatch.setattr(query.clients, "get_qdrant_client", lambda: object())
    monkeypatch.setattr(
        ingest.vector_store,
        "delete_workspace_from_qdrant",
        lambda _client, workspace_id: captured.update({"qdrant": workspace_id}) or {"rag_docs": 0, "rag_visuals": 0},
    )
    monkeypatch.setattr(
        kg_neo4j_ops,
        "delete_document_kg",
        lambda file_name, workspace_id="default": captured["kg"].append((file_name, workspace_id)) or 0,
    )
    monkeypatch.setattr(ingest.registry, "load_registry", lambda _db_dir: {})
    monkeypatch.setattr(ingest.registry, "load_doc_store", lambda _db_dir: {})
    monkeypatch.setattr(ingest.pipeline, "delete_visual_assets_for_file", lambda *_args: 0)
    monkeypatch.setattr(query.cache, "clear_cache_entries", lambda workspace_id: 0)
    monkeypatch.setattr(main_module, "_delete_remaining_workspace_graph", lambda workspace_id: {"nodes": 0, "relationships": 0})

    response = TestClient(app).delete(f"/api/workspaces/{wid}")

    assert response.status_code == 200
    assert captured["qdrant"] == wid
    assert captured["kg"] == []
    assert not root.exists()


def test_delete_document_rejects_encoded_backslash_traversal(monkeypatch):
    called = False

    def fake_delete_document(*args):
        nonlocal called
        called = True
        return {"status": "deleted"}

    monkeypatch.setattr(main_module, "_get_delete_document", lambda: fake_delete_document)

    response = TestClient(app).delete("/api/documents/..%5C..%5Coutside.txt?workspace_id=default")

    assert response.status_code == 400
    assert called is False


def test_umap_workspace_filter_uses_safe_workspace_id():
    qdrant_filter = main_module._workspace_qdrant_filter("Research Space/../A")

    condition = qdrant_filter.must[0]
    assert condition.key == "workspace_id"
    assert condition.match.value == "ResearchSpaceA"


def test_list_workspace_chunks_uses_workspace_filter_and_compact_payload(monkeypatch):
    captured = {}

    class FakePoint:
        def __init__(self, point_id, payload):
            self.id = point_id
            self.payload = payload

    class FakeClient:
        def scroll(self, **kwargs):
            captured.update(kwargs)
            return [
                FakePoint("late", {
                    "file_name": "paper.pdf",
                    "document": "chunk two text",
                    "chunk_index": 2,
                    "page": 3,
                    "section_label": "Results",
                    "doc_type": "text",
                }),
                FakePoint("early", {
                    "file_name": "paper.pdf",
                    "document": "chunk zero text",
                    "chunk_index": 0,
                    "page": 1,
                    "section_label": "Intro",
                    "doc_type": "text",
                }),
            ], None

    monkeypatch.setattr(main_module, "_get_qdrant_client", lambda: lambda: FakeClient())

    chunks = main_module._list_workspace_chunks("Research Space/../A", limit=25)

    assert captured["collection_name"] == "rag_docs"
    assert captured["with_vectors"] is False
    assert captured["with_payload"] is True
    assert captured["scroll_filter"].must[0].match.value == "ResearchSpaceA"
    assert [chunk.chunk_index for chunk in chunks] == [0, 2]
    assert chunks[0].file_name == "paper.pdf"
    assert chunks[0].content == "chunk zero text"
