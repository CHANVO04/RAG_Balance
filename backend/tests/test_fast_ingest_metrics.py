from __future__ import annotations

import sys
import types

import numpy as np


def test_openai_embedder_records_real_response_usage(monkeypatch):
    from ingest import embedder as embedder_module

    class FakeEmbeddingItem:
        def __init__(self, index: int):
            self.index = index
            self.embedding = [float(index + 1)] * 1536

    class FakeUsage:
        prompt_tokens = 4093
        total_tokens = 4093

    class FakeEmbeddingResponse:
        data = [FakeEmbeddingItem(1), FakeEmbeddingItem(0)]
        usage = FakeUsage()

    class FakeEmbeddings:
        def create(self, **_kwargs):
            return FakeEmbeddingResponse()

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr(embedder_module, "OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))

    wrapper = embedder_module.OpenAIEmbedderWrapper("text-embedding-3-small", dim=1536)
    embeddings = wrapper.encode(["first chunk", "second chunk"], batch_size=2)

    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (2, 1536)
    assert wrapper.last_usage.model == "text-embedding-3-small"
    assert wrapper.last_usage.input_tokens == 4093


def test_build_registry_info_persists_real_ingest_metrics():
    from ingest.models import Chunk, ParsedDocument
    from ingest.pipeline import _build_registry_info

    parsed = ParsedDocument(
        file_path="paper.pdf",
        file_name="paper.pdf",
        file_hash="hash",
        doc_type="pdf",
        metadata={"total_pages": 2},
        sections=[],
        tables=[{"table_id": "t1"}, {"table_id": "t2"}],
        images=[{"image_id": "i1"}, {"image_id": "i2"}, {"image_id": "i3"}],
        formulas=[{"formula_id": "f1"}, {"formula_id": "f2"}],
        raw_blocks=[],
    )
    chunks = [
        Chunk(
            text="chunk",
            chunk_id=f"chunk-{i}",
            source_file="paper.pdf",
            file_hash="hash",
            page=1,
            section_label="intro",
            chunk_index=i,
            total_chunks=7,
            has_table=False,
            table_refs=[],
            image_refs=[],
            has_image=False,
            has_formula=False,
            formula_refs=[],
            doc_type="pdf",
            title="Paper",
            language="en",
        )
        for i in range(7)
    ]

    info = _build_registry_info(
        "paper.pdf",
        "hash",
        1234,
        parsed,
        chunks,
        0,
        workspace_id="fast_ws",
        ingest_mode="only_vector_fast",
        processing_time_seconds=53.05,
        stage_timings={"embedding": 3.55},
        embedding={
            "model": "text-embedding-3-small",
            "input_tokens": 4093,
            "price_per_1m_tokens": 0.02,
            "cost_usd": 0.00008186,
        },
    )

    assert info["ingest_mode"] == "only_vector_fast"
    assert info["processing_time_seconds"] == 53.05
    assert info["stage_timings"] == {"embedding": 3.55}
    assert info["embedding"]["model"] == "text-embedding-3-small"
    assert info["embedding"]["input_tokens"] == 4093
    assert info["embedding"]["cost_usd"] == 0.00008186
    assert info["total_dedup_chunks"] == 7
    assert info["total_tables"] == 2
    assert info["total_formulas"] == 2
    assert info["total_images"] == 3
