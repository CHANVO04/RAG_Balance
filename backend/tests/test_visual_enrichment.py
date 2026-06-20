"""
Tests for visual enrichment and provenance-safe Qdrant payloads.

Run:
  pytest tests/test_visual_enrichment.py -v
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parsed_document(**overrides):
    from ingest.models import ParsedDocument

    data = {
        "file_path": "paper.pdf",
        "file_name": "paper.pdf",
        "file_hash": "hash",
        "doc_type": "pdf",
        "metadata": {},
        "sections": [],
        "tables": [],
        "images": [],
        "formulas": [],
        "raw_blocks": [],
    }
    data.update(overrides)
    return ParsedDocument(**data)


class _FakeProv:
    def __init__(self, page_no: int):
        self.page_no = page_no


class _FakeMeta:
    def __init__(self, doc_items, headings=None):
        self.doc_items = doc_items
        self.headings = headings or []


class _FakeRawChunk:
    def __init__(self, text, doc_items, headings=None):
        self.text = text
        self.meta = _FakeMeta(doc_items, headings=headings)


class _FakeChunker:
    def __init__(self, raw_chunks):
        self.raw_chunks = raw_chunks

    def chunk(self, _doc_obj):
        return self.raw_chunks


class _TextDocItem:
    label = "text"
    self_ref = "#/texts/1"

    def __init__(self, pages, text=""):
        self.prov = [_FakeProv(page) for page in pages]
        self.text = text


class TableItem:
    label = "table"

    def __init__(self, self_ref="#/tables/0", page=2):
        self.self_ref = self_ref
        self.prov = [_FakeProv(page)]


class PictureItem:
    label = "picture"

    def __init__(self, self_ref="#/pictures/0", page=1):
        self.self_ref = self_ref
        self.prov = [_FakeProv(page)]


class TestAnalysisShortExtraction(unittest.TestCase):
    def test_extracts_table_semantic_summary(self):
        from ingest.analysis import extract_analysis_short

        full = """### 1. TABLE IDENTITY
Details.

### 4. SEMANTIC SUMMARY
This table compares latency and power consumption.
It highlights that the proposed K210 system uses about 0.6 W.

### 5. RAW TABLE TEXT
raw markdown here
"""

        short = extract_analysis_short("table", full)

        self.assertEqual(
            short,
            "This table compares latency and power consumption.\n"
            "It highlights that the proposed K210 system uses about 0.6 W.",
        )

    def test_extracts_formula_retrieval_summary(self):
        from ingest.analysis import extract_analysis_short

        full = """### 1. FORMULA PURPOSE
Purpose text.

### 3. RETRIEVAL SUMMARY
The formula computes max pooling over a p by p window.
It reduces spatial dimensions of the feature map.
"""

        short = extract_analysis_short("formula", full)

        self.assertIn("max pooling", short)
        self.assertNotIn("FORMULA PURPOSE", short)

    def test_extracts_image_comprehensive_summary(self):
        from ingest.analysis import extract_analysis_short

        full = """### 2. STRUCTURED KEY ELEMENTS
- X axis: epoch

### 3. COMPREHENSIVE SEMANTIC SUMMARY
The graph shows training accuracy increasing over epochs.
Validation accuracy follows the same trend.

### 4. RAW TEXT / OCR (Verbatim)
accuracy
"""

        short = extract_analysis_short("image", full)

        self.assertEqual(
            short,
            "The graph shows training accuracy increasing over epochs.\n"
            "Validation accuracy follows the same trend.",
        )


class TestStrictVisualMapping(unittest.TestCase):
    def test_match_visual_by_ref_raises_when_ref_missing(self):
        from ingest.chunker import VisualMappingError, _match_visual_by_ref

        class NoRefItem:
            pass

        with self.assertRaises(VisualMappingError) as ctx:
            _match_visual_by_ref(
                NoRefItem(),
                {},
                visual_type="image",
                chunk_index=3,
                page=5,
            )

        self.assertIn("Missing self_ref", str(ctx.exception))

    def test_match_visual_by_ref_raises_when_ref_unknown(self):
        from ingest.chunker import VisualMappingError, _match_visual_by_ref

        class UnknownRefItem:
            self_ref = "#/pictures/404"

        with self.assertRaises(VisualMappingError) as ctx:
            _match_visual_by_ref(
                UnknownRefItem(),
                {"#/pictures/1": {"image_id": "img_1_1"}},
                visual_type="image",
                chunk_index=7,
                page=2,
            )

        self.assertIn("#/pictures/404", str(ctx.exception))

    def test_make_chunk_prefers_visual_page_when_docling_page_is_stale(self):
        from ingest.chunker import _make_chunk
        from ingest.models import ParsedDocument

        parsed = ParsedDocument(
            file_path="paper.pdf",
            file_name="paper.pdf",
            file_hash="hash",
            doc_type="pdf",
            metadata={},
            sections=[],
            tables=[],
            images=[],
            formulas=[],
            raw_blocks=[],
        )
        chunk = _make_chunk(
            text="[FORMULA formula_id=formula_4_3 page=4]\nLaTeX:\nx",
            parsed_doc=parsed,
            title="paper",
            page=3,
            section_label="method",
            chunk_index=0,
            formula_refs=["formula_4_3"],
            visual_refs=[{
                "type": "formula",
                "id": "formula_4_3",
                "self_ref": "#/texts/50",
                "page": 4,
                "path": "formula_4_3.png",
            }],
        )

        self.assertEqual(chunk.page, 4)


class TestHybridChunkPreservation(unittest.TestCase):
    def test_chunk_document_preserves_raw_text_when_chunk_contains_table(self):
        from ingest.chunker import chunk_document

        raw_text = (
            "Consistent with the overall system architecture described above and the specific "
            "components in Table I, the hardware implementation consists of an MPU6050 "
            "Inertial Measurement Unit."
        )
        parsed = _parsed_document(
            tables=[{
                "table_id": "table_2_1",
                "self_ref": "#/tables/0",
                "page": 2,
                "caption": "TABLE I",
                "markdown": "| Component | Specification |",
                "analysis_short": "Hardware components summary.",
            }],
        )
        raw_chunk = _FakeRawChunk(
            raw_text,
            [_TextDocItem([2], text=""), TableItem(page=2)],
            headings=["B. Hardware Component"],
        )

        with patch("ingest.chunker._build_hybrid_chunker", return_value=_FakeChunker([raw_chunk])):
            chunks = chunk_document(parsed, doc_obj=object())

        self.assertEqual(len(chunks), 1)
        self.assertIn("Consistent with the overall system architecture described", chunks[0].text)
        self.assertIn("Hardware components summary.", chunks[0].text)
        self.assertIn("table_2_1", chunks[0].table_refs)

    def test_chunk_document_uses_raw_block_page_when_docling_item_spans_pages(self):
        from ingest.chunker import chunk_document

        raw_text = (
            "This novel data processing method enables efficient feature extraction using "
            "a Convolutional Neural Network."
        )
        parsed = _parsed_document(raw_blocks=[{
            "text": raw_text,
            "page": 2,
            "section_id": "intro",
            "block_type": "text",
        }])
        raw_chunk = _FakeRawChunk(
            raw_text,
            [_TextDocItem([1, 2], text=raw_text)],
            headings=["I. INTRODUCTION"],
        )

        with patch("ingest.chunker._build_hybrid_chunker", return_value=_FakeChunker([raw_chunk])):
            chunks = chunk_document(parsed, doc_obj=object())

        self.assertEqual(chunks[0].page, 2)

    def test_chunk_document_namespaces_chunk_id_by_workspace(self):
        from ingest.chunker import chunk_document

        raw_text = "The same text can appear in two separate workspaces."
        parsed = _parsed_document(file_hash="same-file-hash")
        raw_chunk = _FakeRawChunk(raw_text, [_TextDocItem([1], text=raw_text)])

        with patch("ingest.chunker._build_hybrid_chunker", return_value=_FakeChunker([raw_chunk])):
            chunks_a = chunk_document(parsed, doc_obj=object(), workspace_id="workspace_a")
        with patch("ingest.chunker._build_hybrid_chunker", return_value=_FakeChunker([raw_chunk])):
            chunks_b = chunk_document(parsed, doc_obj=object(), workspace_id="workspace_b")

        self.assertNotEqual(chunks_a[0].chunk_id, chunks_b[0].chunk_id)
        self.assertEqual(chunks_a[0].workspace_id, "workspace_a")
        self.assertEqual(chunks_b[0].workspace_id, "workspace_b")

    def test_fast_chunk_document_skips_standalone_image_chunks_but_keeps_tables(self):
        from ingest.chunker import chunk_document

        raw_text = "The paper reports corrosion behavior for stainless steel in acidic solution."
        parsed = _parsed_document(
            tables=[{
                "table_id": "table_1_1",
                "self_ref": "#/tables/0",
                "page": 1,
                "caption": "Table 1",
                "markdown": "| Sample | Corrosion rate |",
                "analysis_short": "Corrosion data table.",
            }],
            images=[{
                "image_id": "img_1_1",
                "self_ref": "#/pictures/0",
                "page": 1,
                "caption": "Not provided",
                "asset_path": "",
                "analysis_short": "[Image summary unavailable]",
            }],
        )
        raw_chunk = _FakeRawChunk(
            raw_text,
            [_TextDocItem([1], text=raw_text), TableItem(self_ref="#/tables/0", page=1)],
            headings=["general"],
        )

        with patch("ingest.chunker._build_hybrid_chunker", return_value=_FakeChunker([raw_chunk])):
            chunks = chunk_document(
                parsed,
                doc_obj=object(),
                include_image_formula_visuals=False,
            )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].table_refs, ["table_1_1"])
        self.assertNotIn("visual:image", {chunk.section_label for chunk in chunks})
        self.assertNotIn("[IMAGE image_id=img_1_1", "\n".join(chunk.text for chunk in chunks))


class TestVisualBlocksAndPayloads(unittest.TestCase):
    def test_visual_blocks_use_short_analysis_not_full_analysis(self):
        from ingest.chunker import _format_image_block

        image = {
            "image_id": "img_5_3",
            "page": 5,
            "caption": "Fig. 3: Accuracy",
            "asset_path": "assets/img_5_3.png",
            "analysis_short": "Accuracy increases over epochs.",
            "analysis_markdown": "### 1. CAPTION & IMAGE TYPE\nVery long full analysis.",
        }

        block = _format_image_block(image)

        self.assertIn("Summary:\nAccuracy increases over epochs.", block)
        self.assertNotIn("Very long full analysis", block)

    def test_build_visual_points_store_full_analysis_with_dummy_vector(self):
        from ingest.vector_store import build_visual_points

        parsed = type("Parsed", (), {})()
        parsed.tables = [{
            "table_id": "table_2_1",
            "page": 2,
            "self_ref": "#/tables/0",
            "caption": "TABLE I",
            "markdown": "| A | B |",
            "analysis_short": "Hardware summary.",
            "analysis_markdown": "Full table analysis.",
        }]
        parsed.images = [{
            "image_id": "img_5_3",
            "page": 5,
            "self_ref": "#/pictures/2",
            "caption": "Fig. 3",
            "asset_path": "assets/img_5_3.png",
            "analysis_short": "Accuracy graph summary.",
            "analysis_markdown": "Full image analysis.",
        }]
        parsed.formulas = [{
            "formula_id": "formula_3_1",
            "page": 3,
            "self_ref": "#/texts/28",
            "latex_string": "Y(i,j)=...",
            "analysis_short": "Convolution summary.",
            "analysis_markdown": "Full formula analysis.",
            "is_decoded": True,
        }]

        points = build_visual_points(parsed, "paper.pdf", "hash123")

        self.assertEqual(len(points), 3)
        for point in points:
            self.assertEqual(point.vector, [0.0])
            self.assertIn("analysis_full", point.payload)
            self.assertIn("visual_id", point.payload)
            self.assertIn("self_ref", point.payload)


class TestVisualRetrievalDecision(unittest.TestCase):
    def test_visual_detail_question_collects_visual_refs(self):
        from query.visuals import collect_visual_ids, should_fetch_full_visual_context

        ranked = [(
            "chunk",
            {
                "visual_refs": '[{"type":"image","id":"img_5_3","page":5}]',
                "image_refs": '["img_5_3"]',
            },
            0.91,
        )]

        self.assertTrue(should_fetch_full_visual_context("Hình 3 thể hiện gì?", ranked))
        self.assertEqual(collect_visual_ids(ranked), ["img_5_3"])

    def test_general_summary_question_does_not_fetch_full_visual_context(self):
        from query.visuals import should_fetch_full_visual_context

        ranked = [("chunk", {"image_refs": '["img_5_3"]'}, 0.91)]

        self.assertFalse(should_fetch_full_visual_context("Tóm tắt paper này", ranked))

    def test_fig_abbreviation_question_fetches_full_visual_context(self):
        from query.visuals import should_fetch_full_visual_context

        ranked = [("chunk", {"image_refs": '["img_5_3"]'}, 0.91)]

        self.assertTrue(should_fetch_full_visual_context("What does Fig 3 show?", ranked))

    def test_equation_reference_question_fetches_full_visual_context(self):
        from query.visuals import should_fetch_full_visual_context

        ranked = [("chunk", {"formula_refs": '["formula_4_2"]'}, 0.91)]

        self.assertTrue(should_fetch_full_visual_context("Can you explain Eq. (2)?", ranked))

    def test_visual_id_question_fetches_full_visual_context(self):
        from query.visuals import should_fetch_full_visual_context

        ranked = [("chunk", {"image_refs": '["img_5_3"]'}, 0.91)]

        self.assertTrue(should_fetch_full_visual_context("Interpret img_5_3 for me", ranked))

    def test_visual_only_question_can_skip_kg_context(self):
        from query.visuals import should_skip_kg_for_visual_question

        ranked = [("chunk", {"image_refs": '["img_5_3"]'}, 0.91)]

        self.assertTrue(should_skip_kg_for_visual_question("Fig 5 có ý nghĩa gì?", ranked))
        self.assertFalse(should_skip_kg_for_visual_question("Fig 5 liên hệ với corrosion rate như thế nào?", ranked))

    def test_full_visual_context_filters_by_workspace_and_preserves_ref_order(self):
        from query.visuals import retrieve_full_visual_context

        class _Record:
            def __init__(self, payload):
                self.payload = payload

        class _FakeClient:
            def __init__(self):
                self.scroll_filter = None

            def scroll(self, **kwargs):
                self.scroll_filter = kwargs["scroll_filter"]
                return [
                    _Record({
                        "visual_id": "formula_2_1",
                        "visual_type": "formula",
                        "page": 2,
                        "file_name": "paper.pdf",
                        "analysis_full": "Formula full analysis.",
                    }),
                    _Record({
                        "visual_id": "img_5_3",
                        "visual_type": "image",
                        "page": 5,
                        "file_name": "paper.pdf",
                        "analysis_full": "Image full analysis.",
                    }),
                ], None

        client = _FakeClient()
        ranked = [(
            "chunk",
            {
                "image_refs": '["img_5_3"]',
                "formula_refs": '["formula_2_1"]',
            },
            0.91,
        )]

        with patch("query.clients.get_collection", return_value=(client, "rag_visuals")):
            context = retrieve_full_visual_context(
                "Explain Fig 3 and the formula.",
                ranked,
                workspace_id="workspace_a",
            )

        keys = {condition.key for condition in client.scroll_filter.must}
        self.assertEqual(keys, {"visual_id", "workspace_id"})
        self.assertLess(context.index("img_5_3"), context.index("formula_2_1"))
        self.assertIn("Image full analysis.", context)
        self.assertIn("Formula full analysis.", context)


class TestQdrantIndexReset(unittest.TestCase):
    def test_reset_qdrant_collections_only_deletes_known_collections(self):
        from ingest.vector_store import reset_qdrant_collections

        class FakeClient:
            def __init__(self):
                self.deleted = []

            def collection_exists(self, name):
                return name in {"rag_docs", "rag_visuals", "rag_tables", "rag_document_chunks"}

            def delete_collection(self, name):
                self.deleted.append(name)

        client = FakeClient()

        deleted = reset_qdrant_collections(client)

        self.assertEqual(deleted, ["rag_docs", "rag_visuals", "rag_tables", "rag_document_chunks"])
        self.assertNotIn("backend/data", " ".join(client.deleted))


if __name__ == "__main__":
    unittest.main()
