from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas import GraphData, KGEvidenceInfo
from kg_neo4j_manager import KGTriplet
from query.kg_retriever import KGSearchResult
from query.prompt_builder import build_prompt


def test_kg_evidence_info_accepts_graph_citation_payload():
    evidence = KGEvidenceInfo(
        id="KG-01",
        subject="Edge Computing",
        relation="enables",
        object="Safety Prediction",
        subject_id="workspace-a::entity::edge_computing",
        object_id="workspace-a::entity::safety_prediction",
        edge_id="workspace-a::edge::edge_computing::enables::safety_prediction",
        source_file="paper.pdf",
        page=4,
        chunk_id="chunk-1",
        weight=2.0,
        evidence_preview="Edge computing enables near-source safety prediction.",
    )

    assert evidence.id == "KG-01"
    assert evidence.source_file == "paper.pdf"
    assert evidence.page == 4


def test_graph_data_remains_backward_compatible_with_existing_shape():
    graph = GraphData(
        nodes=[{"id": "a", "label": "A", "mentions": 1, "degree": 1}],
        edges=[{"source": "a", "target": "b", "relation": "uses", "weight": 1}],
    )

    assert graph.nodes[0]["id"] == "a"
    assert graph.edges[0]["source"] == "a"


def test_kg_triplet_requires_workspace_metadata():
    triplet = KGTriplet(
        subject="Stay Cable",
        relation="uses",
        object="Safety Predictor",
        source="paper.pdf",
        page=4,
        chunk_id="c1",
        workspace_id="workspace-a",
        evidence_preview="Stay cable safety is predicted at the edge.",
    )

    assert triplet.workspace_id == "workspace-a"
    assert triplet.evidence_preview.startswith("Stay cable")


def test_kg_search_result_has_context_and_sources():
    result = KGSearchResult(
        context="## Knowledge Graph\nA --uses--> B",
        sources=[{
            "id": "KG-01",
            "subject": "A",
            "relation": "uses",
            "object": "B",
            "source_file": "paper.pdf",
            "page": 1,
        }],
        unavailable_reason="",
    )

    assert result.context.startswith("## Knowledge Graph")
    assert result.sources[0]["id"] == "KG-01"
    assert result.unavailable_reason == ""


def test_build_prompt_includes_prompt_level_graph_citations():
    system_prompt, user_prompt, _sources = build_prompt(
        question="How does A use B?",
        kg_context="A --uses--> B",
        formula_context="",
        table_context="",
        image_context="",
        ranked_results=[],
        kg_sources=[{
            "id": "KG-01",
            "subject": "A",
            "relation": "uses",
            "object": "B",
            "source_file": "paper.pdf",
            "page": 2,
            "has_document_evidence": True,
        }],
    )

    assert "STRUCTURED GRAPH CITATIONS" in user_prompt
    assert "[KG-01] A --uses--> B" in user_prompt
    assert "paper.pdf" in user_prompt
    assert "page 2" in user_prompt
    lowered_system_prompt = system_prompt.lower()
    assert "graph citation" in lowered_system_prompt
    assert "chỉ được dùng nếu id đó xuất hiện" in system_prompt
    assert "ưu tiên ghép graph citation với citation tài liệu" in system_prompt


def test_build_prompt_omits_structured_graph_citations_when_absent():
    _system_prompt, user_prompt, _sources = build_prompt(
        question="How does A use B?",
        kg_context="A --uses--> B",
        formula_context="",
        table_context="",
        image_context="",
        ranked_results=[],
        kg_sources=[],
    )

    assert "STRUCTURED GRAPH CITATIONS" not in user_prompt


def test_rag_prepare_passes_kg_sources_into_prompt_builder(monkeypatch):
    import query.engine as engine

    kg_sources = [{
        "id": "KG-01",
        "subject": "A",
        "relation": "uses",
        "object": "B",
        "source_file": "paper.pdf",
        "page": 2,
        "has_document_evidence": True,
    }]
    captured = {}

    def fake_build_prompt(*_args, **kwargs):
        captured["kg_sources"] = kwargs.get("kg_sources")
        return "system", "user", ["source"]

    monkeypatch.setattr(
        engine,
        "retrieve_kg",
        lambda *_args, **_kwargs: KGSearchResult(
            context="## Knowledge Graph\n[KG-01] A --uses--> B",
            sources=kg_sources,
        ),
    )
    monkeypatch.setattr(
        engine,
        "retrieve_vectors",
        lambda *_args, **_kwargs: (
            ["A uses B in the paper."],
            [{"file_name": "paper.pdf", "page": 2, "section_label": "method"}],
            [0.9],
            [0.1, 0.2],
        ),
    )
    monkeypatch.setattr(engine, "retrieve_full_visual_context", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(engine, "build_prompt", fake_build_prompt)

    prepared = engine.rag_prepare(
        "How does A use B?",
        retrieve_k=1,
        top_n=1,
        use_rerank=False,
        use_cache=False,
        kg_mode="default",
        workspace_id="default",
        use_visuals=False,
    )

    assert captured["kg_sources"] == kg_sources
    assert prepared["kg_sources"] == kg_sources


def test_kg_source_edge_id_matches_graph_visualization_format():
    import kg_neo4j_traversal as traversal

    edge_id = traversal._graph_edge_id(
        "workspace-a::entity::edge_computing",
        "enables",
        "workspace-a::entity::safety_prediction",
    )

    assert edge_id == (
        "workspace-a::entity::edge_computing::edge::"
        "enables::workspace-a::entity::safety_prediction"
    )


def test_lookup_kg_context_raises_on_connection_error(monkeypatch):
    import kg_neo4j_traversal as traversal

    class FailingManager:
        def session(self):
            raise RuntimeError("neo4j down")

    monkeypatch.setattr(traversal, "get_neo4j_manager", lambda: FailingManager())

    with pytest.raises(RuntimeError, match="neo4j down"):
        traversal.lookup_kg_context("What does NOMA use?", verbose=False)


def test_retrieve_kg_records_no_chunk_anchor_reason(monkeypatch):
    import query.kg_retriever as kg_retriever

    monkeypatch.setattr(kg_retriever, "HAS_KG", True)
    monkeypatch.setattr(
        kg_retriever,
        "lookup_kg_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("old lookup must not be used")),
    )

    result = kg_retriever.retrieve_kg("What does NOMA use?")

    assert result.context == ""
    assert result.sources == []
    assert result.unavailable_reason == "no_chunk_anchors"
    assert result.trace["reason"] == "no_chunk_anchors"
