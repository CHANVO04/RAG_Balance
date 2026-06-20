from __future__ import annotations

import numpy as np


def _parsed_document(file_path: str):
    from ingest.models import ParsedDocument

    return ParsedDocument(
        file_path=file_path,
        file_name="paper.pdf",
        file_hash="hash",
        doc_type="pdf",
        metadata={"total_pages": 1, "title": "Paper"},
        sections=[],
        tables=[{
            "table_id": "table_1",
            "self_ref": "#/tables/0",
            "page": 1,
            "markdown": "| A | B |",
            "analysis_markdown": "",
        }],
        images=[{
            "image_id": "image_1",
            "self_ref": "#/pictures/0",
            "page": 1,
            "caption": "Figure 1",
            "analysis_markdown": "",
        }],
        formulas=[{
            "formula_id": "formula_1",
            "self_ref": "#/texts/0",
            "page": 1,
            "latex": "E=mc^2",
            "is_decoded": True,
            "analysis_markdown": "",
        }],
        raw_blocks=[],
    )


def _chunk():
    from ingest.models import Chunk

    return Chunk(
        text="Text chunk with table markdown\n| A | B |",
        chunk_id="chunk-1",
        source_file="paper.pdf",
        file_hash="hash",
        page=1,
        section_label="intro",
        chunk_index=0,
        total_chunks=1,
        has_table=True,
        table_refs=["table_1"],
        image_refs=["image_1"],
        has_image=True,
        has_formula=True,
        formula_refs=["formula_1"],
        doc_type="pdf",
        title="Paper",
        language="en",
        workspace_id="fast_ws",
        table_markdowns={"table_1": "| A | B |"},
    )


def _patch_common_pipeline(monkeypatch, tmp_path):
    from ingest import pipeline

    paper_path = tmp_path / "paper.pdf"
    paper_path.write_bytes(b"%PDF-1.4 fake")
    calls = {"docs": 0, "visuals": 0, "kg": 0, "include_image_formula_visuals": []}

    monkeypatch.setattr(pipeline, "cleanup_formula_debug_images", lambda: None)
    monkeypatch.setattr(pipeline, "find_documents", lambda _data_dir: [str(paper_path)])
    monkeypatch.setattr(pipeline, "load_registry", lambda _vector_dir: {"documents": []})
    monkeypatch.setattr(pipeline, "save_registry", lambda _registry, _vector_dir: None)
    monkeypatch.setattr(pipeline, "is_already_ingested", lambda _hash, _registry: False)
    monkeypatch.setattr(pipeline, "add_to_registry", lambda _registry, _info: None)
    monkeypatch.setattr(pipeline, "append_chunks_to_store", lambda _chunks, _vector_dir: None)
    monkeypatch.setattr(pipeline, "get_qdrant_client", lambda: object())
    monkeypatch.setattr(pipeline, "ensure_all_collections", lambda _client: None)
    monkeypatch.setattr(pipeline, "get_embedding_model", lambda _model_name: object())
    monkeypatch.setattr(pipeline, "parse_document", lambda path, skip_visual_analysis=False: (_parsed_document(path), object()))
    def fake_chunk_document(
        _parsed,
        doc_obj=None,
        workspace_id="default",
        include_image_formula_visuals=True,
    ):
        calls["include_image_formula_visuals"].append(include_image_formula_visuals)
        return [_chunk()]

    monkeypatch.setattr(pipeline, "chunk_document", fake_chunk_document)
    monkeypatch.setattr(pipeline, "dedup_chunks", lambda chunks: chunks)
    monkeypatch.setattr(pipeline, "embed_chunks", lambda chunks, _model: np.ones((len(chunks), 1536), dtype=float))

    def fake_upsert_docs(_client, _chunks, _embeddings):
        calls["docs"] += 1

    def fake_upsert_visuals(_client, _parsed, _fname, _fhash, workspace_id="default"):
        calls["visuals"] += 1
        return 3

    def fake_run_kg(_chunks, _parsed, _fname, workspace_id="default"):
        calls["kg"] += 1
        return 2

    monkeypatch.setattr(pipeline, "upsert_to_qdrant", fake_upsert_docs)
    monkeypatch.setattr(pipeline, "upsert_visuals_to_qdrant", fake_upsert_visuals)
    monkeypatch.setattr(pipeline, "run_kg_step", fake_run_kg)
    return calls


def test_fast_ingest_keeps_docs_but_skips_visual_payload_indexing(monkeypatch, tmp_path):
    from ingest.pipeline import offline_ingest

    calls = _patch_common_pipeline(monkeypatch, tmp_path)

    summary = offline_ingest(
        data_dir=str(tmp_path),
        vector_dir=str(tmp_path / "db"),
        kg_mode="none",
        skip_visual_analysis=True,
        workspace_id="fast_ws",
        verbose=False,
    )

    assert summary["status"] == "success"
    assert calls["docs"] == 1
    assert calls["visuals"] == 0
    assert calls["kg"] == 0
    assert calls["include_image_formula_visuals"] == [False]


def test_vector_visual_ingest_still_indexes_visual_payloads(monkeypatch, tmp_path):
    from ingest.pipeline import offline_ingest

    calls = _patch_common_pipeline(monkeypatch, tmp_path)

    offline_ingest(
        data_dir=str(tmp_path),
        vector_dir=str(tmp_path / "db"),
        kg_mode="none",
        skip_visual_analysis=False,
        workspace_id="visual_ws",
        verbose=False,
    )

    assert calls["docs"] == 1
    assert calls["visuals"] == 1
    assert calls["kg"] == 0
    assert calls["include_image_formula_visuals"] == [True]


def test_hybrid_ingest_keeps_visual_payloads_and_runs_kg(monkeypatch, tmp_path):
    from ingest.pipeline import offline_ingest

    calls = _patch_common_pipeline(monkeypatch, tmp_path)

    offline_ingest(
        data_dir=str(tmp_path),
        vector_dir=str(tmp_path / "db"),
        kg_mode="light",
        skip_visual_analysis=False,
        workspace_id="hybrid_ws",
        verbose=False,
    )

    assert calls["docs"] == 1
    assert calls["visuals"] == 1
    assert calls["kg"] == 1
    assert calls["include_image_formula_visuals"] == [True]


def test_fast_parser_options_disable_docling_image_generation():
    from ingest.parser import _configure_pdf_pipeline_options

    options = type("Options", (), {})()

    _configure_pdf_pipeline_options(options, skip_visual_analysis=True)

    assert options.do_ocr is False
    assert options.do_formula_enrichment is False
    assert options.generate_picture_images is False
    assert options.generate_page_images is False
    assert options.images_scale == 1.0


def test_visual_parser_options_keep_docling_image_generation():
    from ingest.parser import _configure_pdf_pipeline_options

    options = type("Options", (), {})()

    _configure_pdf_pipeline_options(options, skip_visual_analysis=False)

    assert options.do_ocr is False
    assert options.do_formula_enrichment is False
    assert options.generate_picture_images is True
    assert options.generate_page_images is True
    assert options.images_scale == 2.5
