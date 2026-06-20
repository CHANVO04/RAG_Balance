from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import query.engine as engine


def test_hybrid_query_retrieves_vectors_before_anchored_kg(monkeypatch):
    calls = []

    def fake_retrieve_vectors(*_args, **_kwargs):
        calls.append("vector")
        return (
            ["chunk text"],
            [{"chunk_id": "chunk-1", "file_name": "paper.pdf", "page": 1}],
            [0.91],
            [0.0],
        )

    def fake_retrieve_kg(*_args, **kwargs):
        calls.append(("kg", kwargs.get("chunk_ids")))
        return engine.KGSearchResult(
            context="kg context",
            trace={"graph_relationships_used_in_prompt": 1},
        )

    monkeypatch.setattr(engine, "retrieve_vectors", fake_retrieve_vectors)
    monkeypatch.setattr(engine, "retrieve_kg", fake_retrieve_kg)
    monkeypatch.setattr(engine, "retrieve_full_visual_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(engine, "build_prompt", lambda **kwargs: ("system", "prompt", ["source"]))

    engine.rag_prepare(
        question="What runs on K210?",
        kg_mode="default",
        use_rerank=True,
        use_visuals=True,
        use_cache=False,
        workspace_id="hybrid_ws",
    )

    assert calls[0] == "vector"
    assert calls[1] == ("kg", ["chunk-1"])


def test_visual_only_hybrid_question_skips_kg_traversal(monkeypatch):
    calls = []

    def fake_retrieve_vectors(*_args, **_kwargs):
        return (
            ["[IMAGE image_id=img_5_3 page=5] Fig. 5 caption"],
            [{
                "chunk_id": "chunk-5",
                "file_name": "paper.pdf",
                "page": 5,
                "image_refs": '["img_5_3"]',
            }],
            [0.91],
            [0.0],
        )

    def fake_retrieve_kg(*_args, **_kwargs):
        calls.append("kg")
        return engine.KGSearchResult(context="kg context")

    monkeypatch.setattr(engine, "retrieve_vectors", fake_retrieve_vectors)
    monkeypatch.setattr(engine, "retrieve_kg", fake_retrieve_kg)
    monkeypatch.setattr(engine, "retrieve_full_visual_context", lambda *args, **kwargs: "[image img_5_3] full visual")
    monkeypatch.setattr(engine, "build_prompt", lambda **kwargs: ("system", "prompt", ["source"]))

    prepared = engine.rag_prepare(
        question="Fig 5 có ý nghĩa gì?",
        kg_mode="default",
        use_rerank=True,
        use_visuals=True,
        use_cache=False,
        workspace_id="hybrid_ws",
    )

    assert calls == []
    assert prepared["kg_unavailable_reason"] == "visual_question_prefers_visual_context"


def test_prompt_context_is_evidence_first():
    from query.prompt_builder import build_prompt

    _system_prompt, user_prompt, _sources = build_prompt(
        question="What runs on K210?",
        kg_context="[KG-01] CNN --RUNS_ON--> K210 KPU",
        formula_context="",
        table_context="",
        image_context="[table table-1 | Page 3]\nK210 deployment evidence.",
        ranked_results=[
            (
                "CNN model runs on the K210 KPU.",
                {
                    "chunk_id": "chunk-1",
                    "citation_id": "a3z1",
                    "file_name": "paper.pdf",
                    "page": 3,
                    "section_label": "Deployment",
                },
                0.91,
            )
        ],
        kg_sources=[
            {
                "id": "KG-01",
                "subject": "CNN",
                "relation": "RUNS_ON",
                "object": "K210 KPU",
                "source_file": "paper.pdf",
                "page": 3,
                "chunk_id": "chunk-1",
                "citation": "a3z1",
                "has_document_evidence": True,
            }
        ],
    )

    text_index = user_prompt.index("### TEXT DOCUMENTS")
    kg_index = user_prompt.index("### KNOWLEDGE GRAPH RELATIONSHIPS")
    citation_index = user_prompt.index("### STRUCTURED GRAPH CITATIONS")
    visual_index = user_prompt.index("### HIGH-DETAIL VISUAL EVIDENCE")

    assert text_index < kg_index < citation_index < visual_index
