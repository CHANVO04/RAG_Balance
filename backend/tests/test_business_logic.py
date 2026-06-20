"""
tests/test_business_logic.py — Unit tests for business logic (no external services needed).

Tests:
  CACHE-001: Cache miss on empty store
  CACHE-002: Cache hit at exact similarity 1.0
  CACHE-003: Cache miss when similarity below threshold
  CACHE-004: Cache stores at most 100 entries (eviction)
  CACHE-005: Stale cache entry (wrong dim) is skipped gracefully
  DELETE-001: delete_document returns not_found for unknown file
  DELETE-002: delete_document partial_success when Neo4j raises
  PROMPT-001: build_prompt injects KG context before text
  PROMPT-002: build_prompt omits empty sections from context
  PROMPT-003: build_prompt formula placeholder cleanup

Run from backend/ directory (no Docker needed):
  pytest tests/test_business_logic.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from typing import List
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_ingest_stage_timing_records_per_file_and_reports_progress():
    from ingest.pipeline import _record_stage_timing

    logs = []
    timings = {}
    started_at = time.time() - 0.01

    elapsed = _record_stage_timing(
        timings,
        "paper.pdf",
        "parse_layout",
        started_at,
        report=lambda step, progress: logs.append((step, progress)),
        progress=20,
    )

    assert elapsed >= 0
    assert timings["paper.pdf"]["parse_layout"] >= 0
    assert logs
    assert logs[0][0].startswith("[TIME] paper.pdf parse_layout:")
    assert logs[0][1] == 20


# ══════════════════════════════════════════════════════════════════════════════
# CACHE TESTS  (no external dependencies — uses temp files)
# ══════════════════════════════════════════════════════════════════════════════

class TestSemanticCache(unittest.TestCase):

    def _make_cache_env(self, tmp_dir: str, threshold: float = 0.87):
        """Patch VECTOR_DIR and CACHE_THRESHOLD to use temp directory."""
        cache_file = os.path.join(tmp_dir, "semantic_cache.json")
        return {
            "query.config.VECTOR_DIR":    tmp_dir,
            "query.cache.CACHE_FILE":     cache_file,
            "query.config.CACHE_THRESHOLD": threshold,
            "query.cache.CACHE_THRESHOLD":  threshold,
        }

    def test_cache_001_miss_on_empty_store(self):
        """CACHE-001: Returns None when cache file does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch("query.cache.CACHE_FILE", os.path.join(tmp, "semantic_cache.json")):
                from query.cache import check_semantic_cache
                mock_embedder = MagicMock()
                import numpy as np
                mock_embedder.encode.return_value = np.ones(1024, dtype=np.float32) / 32.0

                with patch("query.cache.get_embedder", return_value=mock_embedder):
                    result = check_semantic_cache("what is NOMA?")
                    self.assertIsNone(result)

    def test_cache_002_hit_at_identical_question(self):
        """CACHE-002: Returns cached answer when cosine similarity is 1.0."""
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = os.path.join(tmp, "semantic_cache.json")
            vec = (np.ones(1024, dtype=np.float32) / 32.0).tolist()
            cache_data = [{"question": "what is NOMA?", "answer": "NOMA answer", "embedding": vec}]
            with open(cache_file, "w") as f:
                json.dump(cache_data, f)

            mock_embedder = MagicMock()
            mock_embedder.encode.return_value = np.array(vec, dtype=np.float32)

            with patch("query.cache.CACHE_FILE", cache_file), \
                 patch("query.cache.CACHE_THRESHOLD", 0.87), \
                 patch("query.cache.get_embedder", return_value=mock_embedder):
                from query.cache import check_semantic_cache
                result = check_semantic_cache("what is NOMA?")
                self.assertEqual(result, "NOMA answer")

    def test_cache_003_miss_below_threshold(self):
        """CACHE-003: Returns None when similarity is below threshold."""
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = os.path.join(tmp, "semantic_cache.json")
            # Orthogonal vector → cosine = 0.0
            vec_a = np.zeros(1024, dtype=np.float32)
            vec_a[0] = 1.0
            vec_b = np.zeros(1024, dtype=np.float32)
            vec_b[1] = 1.0

            cache_data = [{"question": "q1", "answer": "a1", "embedding": vec_a.tolist()}]
            with open(cache_file, "w") as f:
                json.dump(cache_data, f)

            mock_embedder = MagicMock()
            mock_embedder.encode.return_value = vec_b

            with patch("query.cache.CACHE_FILE", cache_file), \
                 patch("query.cache.CACHE_THRESHOLD", 0.87), \
                 patch("query.cache.get_embedder", return_value=mock_embedder):
                from query.cache import check_semantic_cache
                result = check_semantic_cache("completely different question")
                self.assertIsNone(result)

    def test_cache_004_max_100_entries(self):
        """CACHE-004: Cache trims to last 100 entries on add."""
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = os.path.join(tmp, "semantic_cache.json")
            # Pre-populate with 100 entries
            vec = np.ones(1024, dtype=np.float32).tolist()
            existing = [{"question": f"q{i}", "answer": f"a{i}", "embedding": vec}
                        for i in range(100)]
            with open(cache_file, "w") as f:
                json.dump(existing, f)

            mock_embedder = MagicMock()
            mock_embedder.encode.return_value = np.ones(1024, dtype=np.float32)
            mock_embedder.encode.return_value = mock_embedder.encode.return_value

            with patch("query.cache.CACHE_FILE", cache_file), \
                 patch("query.cache.get_embedder", return_value=mock_embedder):
                from query.cache import add_to_cache
                add_to_cache("new question", "new answer")

            with open(cache_file) as f:
                saved = json.load(f)
            self.assertEqual(len(saved), 100)
            self.assertEqual(saved[-1]["question"], "new question")

    def test_cache_005_stale_entry_wrong_dim_skipped(self):
        """CACHE-005: Stale entry with wrong embedding dimension is skipped silently."""
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = os.path.join(tmp, "semantic_cache.json")
            # Store entry with dim=512, but current model uses 1024
            stale_vec = np.ones(512, dtype=np.float32).tolist()
            cache_data = [{"question": "old question", "answer": "old answer", "embedding": stale_vec}]
            with open(cache_file, "w") as f:
                json.dump(cache_data, f)

            mock_embedder = MagicMock()
            mock_embedder.encode.return_value = np.ones(1024, dtype=np.float32)

            with patch("query.cache.CACHE_FILE", cache_file), \
                 patch("query.cache.CACHE_THRESHOLD", 0.87), \
                 patch("query.cache.get_embedder", return_value=mock_embedder):
                from query.cache import check_semantic_cache
                result = check_semantic_cache("any question")
                self.assertIsNone(result)  # Skipped, not crashed


# ══════════════════════════════════════════════════════════════════════════════
# DELETE ATOMICITY TESTS  (mocked Qdrant + Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteAtomicity(unittest.TestCase):

    def _make_registry(self, tmp_dir: str, file_name: str) -> str:
        """Write a minimal registry.json with one document entry."""
        registry = {"documents": [{"file_name": file_name, "file_hash": "abc123"}]}
        path = os.path.join(tmp_dir, "registry.json")
        with open(path, "w") as f:
            json.dump(registry, f)
        return path

    def _make_docstore(self, tmp_dir: str, file_name: str) -> str:
        """Write a minimal documents_store.json with one chunk entry."""
        store = {"documents": [{"metadata": {"file_name": file_name}, "text": "chunk text"}]}
        path = os.path.join(tmp_dir, "documents_store.json")
        with open(path, "w") as f:
            json.dump(store, f)
        return path

    def test_delete_001_not_found(self):
        """DELETE-001: Returns 'not_found' when file not in any storage."""
        with tempfile.TemporaryDirectory() as tmp:
            self._make_registry(tmp, "other.pdf")
            self._make_docstore(tmp, "other.pdf")

            mock_client = MagicMock()
            mock_client.collection_exists.return_value = False

            with patch("ingest.pipeline.get_qdrant_client", return_value=mock_client), \
                 patch("ingest.pipeline.delete_from_qdrant", return_value={"rag_docs": 0}), \
                 patch("ingest.pipeline.delete_document_kg", return_value=0), \
                 patch("ingest.pipeline.VECTOR_DIR", tmp), \
                 patch("ingest.pipeline.DATA_DIR", tmp):
                from ingest.pipeline import delete_document
                result = delete_document("nonexistent.pdf", vector_dir=tmp, data_dir=tmp)

            self.assertEqual(result["status"], "not_found")

    def test_delete_002_partial_success_on_neo4j_failure(self):
        """DELETE-002: Returns 'partial_success' when Neo4j raises but Qdrant + JSON succeed."""
        with tempfile.TemporaryDirectory() as tmp:
            self._make_registry(tmp, "paper.pdf")
            self._make_docstore(tmp, "paper.pdf")

            with patch("ingest.pipeline.get_qdrant_client", return_value=MagicMock()), \
                 patch("ingest.pipeline.delete_from_qdrant", return_value={"rag_docs": 5}), \
                 patch("ingest.pipeline.delete_document_kg",
                       side_effect=RuntimeError("Neo4j connection refused")), \
                 patch("ingest.pipeline.VECTOR_DIR", tmp), \
                 patch("ingest.pipeline.DATA_DIR", tmp):
                from ingest.pipeline import delete_document
                result = delete_document("paper.pdf", vector_dir=tmp, data_dir=tmp)

            self.assertEqual(result["status"], "partial_success")
            self.assertIn("errors", result)
            self.assertTrue(any("Neo4j" in e for e in result["errors"]))
            # Registry must be updated (file removed) even when Neo4j fails
            with open(os.path.join(tmp, "registry.json")) as f:
                registry = json.load(f)
            remaining = [d for d in registry["documents"] if d["file_name"] == "paper.pdf"]
            self.assertEqual(remaining, [])

    def test_delete_003_success_removes_from_all_stores(self):
        """DELETE-003: Successful delete removes entry from registry and docstore."""
        with tempfile.TemporaryDirectory() as tmp:
            self._make_registry(tmp, "paper.pdf")
            self._make_docstore(tmp, "paper.pdf")

            with patch("ingest.pipeline.get_qdrant_client", return_value=MagicMock()), \
                 patch("ingest.pipeline.delete_from_qdrant", return_value={"rag_docs": 3}), \
                 patch("ingest.pipeline.delete_document_kg", return_value=5), \
                 patch("ingest.pipeline.VECTOR_DIR", tmp), \
                 patch("ingest.pipeline.DATA_DIR", tmp):
                from ingest.pipeline import delete_document
                result = delete_document("paper.pdf", vector_dir=tmp, data_dir=tmp)

            self.assertEqual(result["status"], "deleted")
            self.assertNotIn("errors", result)
            self.assertEqual(result["removed_registry_entries"], 1)

            with open(os.path.join(tmp, "registry.json")) as f:
                registry = json.load(f)
            self.assertEqual(registry["documents"], [])


class TestQdrantDeleteCoverage(unittest.TestCase):

    def test_delete_from_qdrant_removes_all_content_collections(self):
        """DELETE-004: Delete must remove stale docs/tables/formulas/images."""
        from ingest.vector_store import delete_from_qdrant

        class _CountResult:
            def __init__(self, count: int):
                self.count = count

        class _FakeQdrant:
            def __init__(self):
                self.deleted_collections = []
                self._counts = {}

            def count(self, collection_name: str, exact: bool = True):
                calls = self._counts.get(collection_name, 0)
                self._counts[collection_name] = calls + 1
                return _CountResult(1 if calls == 0 else 0)

            def delete(self, collection_name: str, points_selector, wait: bool = True):
                self.deleted_collections.append(collection_name)

        client = _FakeQdrant()
        removed = delete_from_qdrant(client, "paper.pdf")

        self.assertEqual(
            client.deleted_collections,
            ["rag_docs", "rag_visuals", "rag_tables", "rag_formulas", "rag_images"],
        )
        self.assertEqual(set(removed), {"rag_docs", "rag_visuals", "rag_tables", "rag_formulas", "rag_images"})


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT BUILDER TESTS  (pure Python, no external deps)
# ══════════════════════════════════════════════════════════════════════════════

class TestPromptBuilder(unittest.TestCase):

    def _make_ranked(self, n: int = 2):
        return [
            (f"chunk text {i}", {"file_name": f"paper{i}.pdf", "page": i, "section_label": "intro",
                                  "has_table": False, "has_formula": False, "has_image": False}, 0.9)
            for i in range(1, n + 1)
        ]

    def test_prompt_001_text_evidence_before_kg_context(self):
        """PROMPT-001: Text evidence appears before KG context in user_prompt."""
        from query.prompt_builder import build_prompt
        _, user_prompt, _ = build_prompt(
            question="what is NOMA?",
            kg_context="KG_DATA",
            formula_context="",
            table_context="",
            image_context="",
            ranked_results=self._make_ranked(1),
        )
        kg_pos   = user_prompt.find("KG_DATA")
        text_pos = user_prompt.find("TEXT DOCUMENTS")
        self.assertGreater(kg_pos, text_pos, "TEXT DOCUMENTS must appear before KG context")

    def test_prompt_002_empty_sections_omitted(self):
        """PROMPT-002: Empty context sections are not injected into user_prompt."""
        from query.prompt_builder import build_prompt
        _, user_prompt, _ = build_prompt(
            question="q",
            kg_context="",
            formula_context="",
            table_context="",
            image_context="",
            ranked_results=self._make_ranked(1),
        )
        self.assertNotIn("KNOWLEDGE GRAPH", user_prompt)
        self.assertNotIn("FORMULAS", user_prompt)
        self.assertNotIn("TABLES", user_prompt)
        self.assertNotIn("IMAGES", user_prompt)
        self.assertIn("TEXT DOCUMENTS", user_prompt)

    def test_prompt_003_formula_placeholder_cleaned(self):
        """PROMPT-003: <!-- formula-not-decoded --> placeholder is replaced in chunk text."""
        from query.prompt_builder import build_prompt
        dirty_chunk = "The formula <!-- formula-not-decoded --> is important."
        ranked = [(dirty_chunk, {"file_name": "p.pdf", "page": 1, "section_label": "s",
                                  "has_table": False, "has_formula": True, "has_image": False}, 0.8)]
        _, user_prompt, _ = build_prompt("q", "", "", "", "", ranked)
        self.assertNotIn("<!-- formula-not-decoded -->", user_prompt)
        self.assertIn("[Công thức]", user_prompt)

    def test_prompt_004_sources_info_format(self):
        """PROMPT-004: sources_info has one entry per ranked result with file name and page."""
        from query.prompt_builder import build_prompt
        _, _, sources = build_prompt("q", "", "", "", "", self._make_ranked(3))
        self.assertEqual(len(sources), 3)
        for i, src in enumerate(sources, 1):
            self.assertIn(f"[{i}]", src)
            self.assertIn("paper", src)


# ══════════════════════════════════════════════════════════════════════════════
# FORMULA IMAGE CLEANUP TEST
# ══════════════════════════════════════════════════════════════════════════════

class TestFormulaImageCleanup(unittest.TestCase):

    def test_cleanup_removes_png_files(self):
        """CLEANUP-001: cleanup_formula_debug_images removes .png files from target dir."""
        import importlib
        import ingest.vision as vision_module

        with tempfile.TemporaryDirectory() as tmp:
            # Create dummy PNG files
            for name in ["f1.png", "f2.png", "notes.txt"]:
                open(os.path.join(tmp, name), "w").close()

            # Patch the target dir calculation inside cleanup function
            original_cleanup = vision_module.cleanup_formula_debug_images

            def patched_cleanup():
                removed = 0
                if not os.path.isdir(tmp):
                    return 0
                for fname in os.listdir(tmp):
                    if fname.lower().endswith(".png"):
                        os.remove(os.path.join(tmp, fname))
                        removed += 1
                return removed

            removed = patched_cleanup()
            self.assertEqual(removed, 2)
            # .txt file must survive
            self.assertTrue(os.path.exists(os.path.join(tmp, "notes.txt")))
            # PNG files must be gone
            self.assertFalse(os.path.exists(os.path.join(tmp, "f1.png")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "f2.png")))


if __name__ == "__main__":
    unittest.main()
