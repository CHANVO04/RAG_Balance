from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from query.kg_retriever import _format_graph_context, _rank_graph_edges, retrieve_kg


class _FakeNode(dict):
    def __init__(self, **values):
        super().__init__(values)


class _FakeRelationship(dict):
    def __init__(self, **values):
        super().__init__(values)


class _FakeSession:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def run(self, query, parameters=None, **kwargs):
        self.calls.append((query, parameters or kwargs))
        return self.records


class _FakeManager:
    def __init__(self, session):
        self._session = session

    def session(self):
        return self._session


def test_rank_graph_edges_prefers_chunk_overlap_and_seed_connection():
    edges = [
        {
            "subject": "A",
            "relation": "ENABLES",
            "object": "B",
            "source_id": "entity-a",
            "target_id": "entity-b",
            "chunk_ids": ["other"],
            "weight": 10,
            "confidence": 0.9,
            "distance": 2,
            "visual_ids": [],
        },
        {
            "subject": "C",
            "relation": "RUNS_ON",
            "object": "D",
            "source_id": "entity-c",
            "target_id": "entity-d",
            "chunk_ids": ["chunk-1"],
            "weight": 1,
            "confidence": 0.5,
            "distance": 1,
            "visual_ids": [],
        },
    ]

    ranked = _rank_graph_edges(
        edges=edges,
        chunk_ids=["chunk-1"],
        seed_entity_ids=set(),
        visual_intent=False,
        limit=1,
    )

    assert ranked[0]["relation"] == "RUNS_ON"


def test_retrieve_kg_uses_chunk_anchors_in_one_neo4j_call(monkeypatch):
    session = _FakeSession([
        {
            "source": _FakeNode(id="entity-cnn", label="CNN"),
            "relationship": _FakeRelationship(
                relation="RUNS_ON",
                source_files=["paper.pdf"],
                pages=[3],
                chunk_ids=["chunk-1"],
                visual_ids=["table-1"],
                evidence_preview="CNN model runs on the K210 KPU.",
                confidence=0.82,
                weight=2,
            ),
            "target": _FakeNode(id="entity-kpu", label="K210 KPU"),
            "distance": 1,
        }
    ])

    import query.kg_retriever as kg_retriever

    monkeypatch.setattr(kg_retriever, "get_neo4j_manager", lambda: _FakeManager(session), raising=False)
    monkeypatch.setattr(
        kg_retriever,
        "lookup_kg_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("old lookup must not be used")),
        raising=False,
    )

    result = retrieve_kg(
        "What runs on K210?",
        kg_mode="default",
        workspace_id="hybrid_ws",
        chunk_ids=["chunk-1"],
        visual_intent=True,
    )

    assert len(session.calls) == 1
    assert session.calls[0][1]["workspace_id"] == "hybrid_ws"
    assert session.calls[0][1]["chunk_ids"] == ["chunk-1"]
    assert "[KG-01] CNN --RUNS_ON--> K210 KPU" in result.context
    assert result.sources[0]["id"] == "KG-01"
    assert result.sources[0]["edge_id"] == "entity-cnn::edge::RUNS_ON::entity-kpu"
    assert result.sources[0]["chunk_id"] == "chunk-1"
    assert result.trace["graph_relationships_traversed"] == 1
    assert result.trace["graph_relationships_used_in_prompt"] == 1


def test_retrieve_kg_uses_seed_ids_from_records_for_seed_boost(monkeypatch):
    session = _FakeSession([
        {
            "seed_id": "entity-cnn",
            "source": _FakeNode(id="entity-cnn", label="CNN"),
            "relationship": _FakeRelationship(
                relation="RUNS_ON",
                source_files=["paper.pdf"],
                pages=[3],
                chunk_ids=["chunk-1"],
                visual_ids=[],
                evidence_preview="CNN model runs on K210.",
                confidence=0.5,
                weight=1,
            ),
            "target": _FakeNode(id="entity-kpu", label="K210 KPU"),
            "distance": 1,
        },
        {
            "seed_id": "entity-kpu",
            "source": _FakeNode(id="entity-kpu", label="K210 KPU"),
            "relationship": _FakeRelationship(
                relation="SUPPORTS",
                source_files=["paper.pdf"],
                pages=[3],
                chunk_ids=["other"],
                visual_ids=[],
                evidence_preview="K210 supports edge inference.",
                confidence=0.5,
                weight=0,
            ),
            "target": _FakeNode(id="entity-edge", label="Edge Inference"),
            "distance": 1,
        },
        {
            "seed_id": "entity-cnn",
            "source": _FakeNode(id="entity-a", label="High Weight A"),
            "relationship": _FakeRelationship(
                relation="ENABLES",
                source_files=["paper.pdf"],
                pages=[3],
                chunk_ids=["chunk-1"],
                visual_ids=[],
                evidence_preview="A enables B.",
                confidence=0.9,
                weight=10,
            ),
            "target": _FakeNode(id="entity-b", label="High Weight B"),
            "distance": 1,
        },
    ])

    import query.kg_retriever as kg_retriever

    monkeypatch.setattr(kg_retriever, "get_neo4j_manager", lambda: _FakeManager(session), raising=False)

    result = retrieve_kg(
        "What runs on K210?",
        kg_mode="default",
        workspace_id="hybrid_ws",
        chunk_ids=["chunk-1"],
    )

    assert "seed.id AS seed_id" in session.calls[0][0]
    assert result.context.index("[KG-01] CNN --RUNS_ON--> K210 KPU") < result.context.index(
        "High Weight A --ENABLES--> High Weight B"
    )


def test_retrieve_kg_dedupes_duplicate_relationship_records(monkeypatch):
    duplicate_rel = _FakeRelationship(
        relation="RUNS_ON",
        source_files=["paper.pdf"],
        pages=[3],
        chunk_ids=["chunk-1"],
        visual_ids=[],
        evidence_preview="CNN model runs on K210.",
        confidence=0.8,
        weight=1,
    )
    session = _FakeSession([
        {
            "seed_id": "entity-cnn",
            "source": _FakeNode(id="entity-cnn", label="CNN"),
            "relationship": duplicate_rel,
            "target": _FakeNode(id="entity-kpu", label="K210 KPU"),
            "distance": 2,
        },
        {
            "seed_id": "entity-kpu",
            "source": _FakeNode(id="entity-cnn", label="CNN"),
            "relationship": duplicate_rel,
            "target": _FakeNode(id="entity-kpu", label="K210 KPU"),
            "distance": 1,
        },
    ])

    import query.kg_retriever as kg_retriever

    monkeypatch.setattr(kg_retriever, "get_neo4j_manager", lambda: _FakeManager(session), raising=False)

    result = retrieve_kg(
        "What runs on K210?",
        kg_mode="default",
        workspace_id="hybrid_ws",
        chunk_ids=["chunk-1"],
    )

    assert result.context.count("CNN --RUNS_ON--> K210 KPU") == 1
    assert result.sources[0]["distance"] == 1
    assert result.trace["graph_relationships_traversed"] == 2
    assert result.trace["graph_relationships_used_in_prompt"] == 1


def test_retrieve_kg_skips_non_default_mode_without_neo4j(monkeypatch):
    import query.kg_retriever as kg_retriever

    monkeypatch.setattr(
        kg_retriever,
        "get_neo4j_manager",
        lambda: (_ for _ in ()).throw(AssertionError("Neo4j should not be touched")),
        raising=False,
    )

    result = retrieve_kg(
        "What runs on K210?",
        kg_mode="vector",
        workspace_id="default",
        chunk_ids=["chunk-1"],
    )

    assert result.context == ""
    assert result.sources == []
    assert result.trace["reason"] == "kg_disabled"


def test_format_graph_context_uses_evidence_anchored_triplets():
    context = _format_graph_context(
        [
            {
                "subject": "CNN",
                "relation": "RUNS_ON",
                "object": "K210 KPU",
                "file_name": "paper.pdf",
                "page": 3,
                "chunk_ids": ["chunk-1"],
                "citation": "S1",
                "evidence_preview": "CNN model runs on the K210 KPU.",
            }
        ]
    )

    assert "[KG-01] CNN --RUNS_ON--> K210 KPU" in context
    assert "Evidence anchor: paper.pdf, page 3, chunk_id=chunk-1, citation=[S1]" in context
    assert 'Evidence preview: "CNN model runs on the K210 KPU."' in context
