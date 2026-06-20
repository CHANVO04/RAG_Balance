from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np


class TestWorkspaceQdrantIsolation(unittest.TestCase):
    def test_ensure_all_collections_creates_payload_indexes_for_filtered_search(self):
        from ingest.vector_store import ensure_all_collections

        class _FakeClient:
            def __init__(self):
                self.payload_indexes = []

            def collection_exists(self, _name):
                return True

            def create_payload_index(self, collection_name, field_name, field_schema):
                self.payload_indexes.append((collection_name, field_name, field_schema))

        client = _FakeClient()

        ensure_all_collections(client)

        indexed_fields = {(collection, field) for collection, field, _ in client.payload_indexes}
        self.assertIn(("rag_docs", "workspace_id"), indexed_fields)
        self.assertIn(("rag_docs", "file_name"), indexed_fields)
        self.assertIn(("rag_visuals", "workspace_id"), indexed_fields)
        self.assertIn(("rag_visuals", "visual_id"), indexed_fields)

    def test_upsert_payload_contains_workspace_id(self):
        from ingest.models import Chunk
        from ingest.vector_store import upsert_to_qdrant

        chunk = Chunk(
            text="workspace scoped text",
            chunk_id="chunk-1",
            source_file="paper.pdf",
            file_hash="hash",
            page=1,
            section_label="intro",
            chunk_index=0,
            total_chunks=1,
            has_table=False,
            table_refs=[],
            image_refs=[],
            has_image=False,
            has_formula=False,
            formula_refs=[],
            doc_type="pdf",
            title="paper",
            language="en",
            workspace_id="workspace_a",
        )
        client = MagicMock()

        upsert_to_qdrant(client, [chunk], np.ones((1, 1536), dtype=float))

        point = client.upsert.call_args.kwargs["points"][0]
        self.assertEqual(point.payload["workspace_id"], "workspace_a")

    def test_visual_payload_contains_workspace_id(self):
        from ingest.vector_store import build_visual_points

        parsed = type("Parsed", (), {})()
        parsed.tables = [{
            "table_id": "table_1",
            "self_ref": "#/tables/0",
            "page": 1,
            "markdown": "| A |",
            "analysis_short": "short",
            "analysis_markdown": "full",
        }]
        parsed.images = []
        parsed.formulas = []

        points = build_visual_points(parsed, "paper.pdf", "hash", workspace_id="workspace_a")

        self.assertEqual(points[0].payload["workspace_id"], "workspace_a")

    def test_delete_filters_by_workspace_and_file_name(self):
        from ingest.vector_store import delete_from_qdrant

        class _Count:
            def __init__(self, count):
                self.count = count

        class _FakeClient:
            def __init__(self):
                self.filters = []
                self._counts = {}

            def count(self, collection_name, exact=True):
                calls = self._counts.get(collection_name, 0)
                self._counts[collection_name] = calls + 1
                return _Count(1 if calls == 0 else 0)

            def delete(self, collection_name, points_selector, wait=True):
                self.filters.append(points_selector)

        client = _FakeClient()

        delete_from_qdrant(client, "paper.pdf", workspace_id="workspace_a")

        first_filter = client.filters[0]
        keys = {condition.key for condition in first_filter.must}
        self.assertEqual(keys, {"file_name", "workspace_id"})


class TestOnlyVectorMode(unittest.TestCase):
    def test_run_ingest_maps_only_vector_to_kg_none(self):
        import main
        from schemas import TaskStatus

        captured = {}

        def fake_offline_ingest(**kwargs):
            captured.update(kwargs)
            kwargs["progress_callback"]("Đang tạo embedding: paper.pdf", 68)
            return {"status": "success"}

        task_id = "task-only-vector"
        main._tasks[task_id] = TaskStatus(
            task_id=task_id,
            status="queued",
            progress=0,
            current_step="queued",
            logs=[],
        )

        try:
            with patch("main._get_offline_ingest", return_value=fake_offline_ingest):
                main._run_ingest(
                    "paper.pdf",
                    "paper.pdf",
                    task_id,
                    data_dir="data",
                    db_dir="db",
                    ingest_mode="only_vector",
                )
            task = main._tasks[task_id]
            self.assertEqual(task.progress, 100)
            self.assertTrue(any("Đang tạo embedding" in log for log in task.logs))
        finally:
            main._tasks.pop(task_id, None)

        self.assertEqual(captured["kg_mode"], "none")
        self.assertFalse(captured["skip_visual_analysis"])
        self.assertIn("progress_callback", captured)

    def test_run_ingest_fast_request_keeps_default_vector_visuals_strategy(self):
        import main
        from schemas import TaskStatus

        captured = {}

        def fake_offline_ingest(**kwargs):
            captured.update(kwargs)
            return {"status": "success"}

        task_id = "task-only-vector-fast"
        main._tasks[task_id] = TaskStatus(
            task_id=task_id,
            status="queued",
            progress=0,
            current_step="queued",
            logs=[],
        )

        try:
            with patch("main._get_offline_ingest", return_value=fake_offline_ingest):
                main._run_ingest(
                    "paper.pdf",
                    "paper.pdf",
                    task_id,
                    data_dir="data",
                    db_dir="db",
                    ingest_mode="only_vector_fast",
                )
        finally:
            main._tasks.pop(task_id, None)

        self.assertEqual(captured["kg_mode"], "none")
        self.assertFalse(captured["skip_visual_analysis"])

    def test_query_mode_only_vector_disables_kg_and_rerank(self):
        import main

        settings = main._resolve_query_mode("only_vector")

        self.assertEqual(settings["kg_mode"], "vector")
        self.assertFalse(settings["use_rerank"])
        self.assertTrue(settings["use_visuals"])

    def test_query_mode_fast_vector_disables_visuals(self):
        import main

        settings = main._resolve_query_mode("only_vector_fast")

        self.assertEqual(settings["kg_mode"], "vector")
        self.assertFalse(settings["use_rerank"])
        self.assertFalse(settings["use_visuals"])


class TestOnlyVectorRetrievalContracts(unittest.TestCase):
    def test_retrieve_vectors_filters_by_workspace_and_selected_files(self):
        from query.vector_retriever import retrieve_vectors

        class _FakeEmbedder:
            def encode(self, *_args, **_kwargs):
                return np.array([0.1, 0.2, 0.3], dtype=float)

        class _FakePoint:
            score = 0.87
            payload = {
                "document": "retrieved chunk",
                "workspace_id": "workspace_a",
                "file_name": "paper.pdf",
                "page": 2,
            }

        class _FakeResults:
            points = [_FakePoint()]

        class _FakeClient:
            def __init__(self):
                self.query_filter = None

            def query_points(self, **kwargs):
                self.query_filter = kwargs["query_filter"]
                return _FakeResults()

        client = _FakeClient()

        with patch("query.vector_retriever.get_collection", return_value=(client, "rag_docs")):
            with patch("query.vector_retriever.get_embedder", return_value=_FakeEmbedder()):
                docs, metas, scores, q_emb = retrieve_vectors(
                    "What is the method?",
                    retrieve_k=5,
                    selected_files=["paper.pdf"],
                    workspace_id="workspace_a",
                )

        self.assertEqual(docs, ["retrieved chunk"])
        self.assertEqual(scores, [0.87])
        self.assertEqual(q_emb, [0.1, 0.2, 0.3])
        keys = {condition.key for condition in client.query_filter.must}
        self.assertEqual(keys, {"workspace_id", "file_name"})

    def test_retrieve_vectors_omits_file_filter_when_all_files_selected(self):
        from query.vector_retriever import retrieve_vectors

        class _FakeEmbedder:
            def encode(self, *_args, **_kwargs):
                return np.array([0.1, 0.2], dtype=float)

        class _FakeResults:
            points = []

        class _FakeClient:
            def __init__(self):
                self.query_filter = None

            def query_points(self, **kwargs):
                self.query_filter = kwargs["query_filter"]
                return _FakeResults()

        client = _FakeClient()

        with patch("query.vector_retriever.get_collection", return_value=(client, "rag_docs")):
            with patch("query.vector_retriever.get_embedder", return_value=_FakeEmbedder()):
                retrieve_vectors(
                    "Summarize",
                    retrieve_k=5,
                    selected_files=[],
                    workspace_id="workspace_a",
                )

        keys = {condition.key for condition in client.query_filter.must}
        self.assertEqual(keys, {"workspace_id"})


if __name__ == "__main__":
    unittest.main()
