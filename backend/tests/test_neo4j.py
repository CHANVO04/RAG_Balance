"""
tests/test_neo4j.py — Validation tests for Neo4j KG migration.

Run from backend/ directory with Neo4j Docker running:
  cd backend
  pytest tests/test_neo4j.py -v

Prerequisites:
  docker compose -f neo4j-server/docker-compose.yml up -d
  pip install neo4j>=5.0
"""

import sys
import os
import pytest

# Ensure backend/ is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kg_neo4j import (
    get_neo4j_manager,
    KGTriplet,
    upsert_triplets,
    upsert_visual_nodes,
    lookup_kg_context,
    delete_document_kg,
    get_graph_for_viz,
    UsageTracker,
    usage_tracker,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

class FakeUsage:
    def __init__(self, prompt=50, completion=30):
        self.prompt_tokens     = prompt
        self.completion_tokens = completion


class FakeChunk:
    def __init__(self, text, chunk_id="test-001", source="test.pdf", page=1,
                 section_label="abstract", title="Test Paper"):
        self.text          = text
        self.chunk_id      = chunk_id
        self.source_file   = source
        self.page          = page
        self.section_label = section_label
        self.title         = title


class FakeParsed:
    def __init__(self, formulas=None, images=None):
        self.formulas = formulas or []
        self.images   = images or []


_TEST_SOURCE = "_pytest_test_paper.pdf"
_WORKSPACE_SOURCE = "_pytest_workspace_shared.pdf"
_TEST_SOURCES = [
    _TEST_SOURCE,
    "_pytest_run_kg.pdf",
    "_pytest_full_delete.pdf",
    _WORKSPACE_SOURCE,
    "_pytest_multi_source_a.pdf",
    "_pytest_multi_source_b.pdf",
    "_pytest_rag_prepare_empty_filter.pdf",
]

_SAMPLE_TRIPLETS = [
    KGTriplet(subject="NOMA", relation="DEPENDS_ON", object="SIC",
              source=_TEST_SOURCE, page=1, chunk_id="c1"),
    KGTriplet(subject="NOMA", relation="IMPROVES", object="Spectral Efficiency",
              source=_TEST_SOURCE, page=1, chunk_id="c2"),
    KGTriplet(subject="SIC", relation="MITIGATES", object="Interference",
              source=_TEST_SOURCE, page=2, chunk_id="c3"),
]


@pytest.fixture(scope="module")
def manager():
    mgr = get_neo4j_manager()
    with mgr.session() as s:
        for src in _TEST_SOURCES:
            s.run("MATCH ()-[r:RELATES_TO]->() WHERE $src IN coalesce(r.source_files, []) DELETE r", src=src)
            s.run("MATCH (n)-[:APPEARS_IN]->(d:Document) WHERE d.source_file = $src DETACH DELETE n", src=src)
            s.run("MATCH (d:Document {source_file: $src}) DETACH DELETE d", src=src)
        s.run("MATCH (n:Entity) WHERE NOT (n)-[:RELATES_TO]-() AND NOT ()-[:RELATES_TO]->(n) DETACH DELETE n")
    yield mgr
    # Teardown: clean up test data
    with mgr.session() as s:
        for src in _TEST_SOURCES:
            s.run("MATCH ()-[r:RELATES_TO]->() WHERE $src IN coalesce(r.source_files, []) DELETE r", src=src)
            s.run("MATCH (n)-[:APPEARS_IN]->(d:Document) WHERE d.source_file = $src DETACH DELETE n", src=src)
            s.run("MATCH (d:Document {source_file: $src}) DETACH DELETE d", src=src)
        s.run("MATCH (n:Entity) WHERE NOT (n)-[:RELATES_TO]-() AND NOT ()-[:RELATES_TO]->(n) DETACH DELETE n")
        s.run("MATCH (n)-[:APPEARS_IN]->(d:Document {id: $src}) DETACH DELETE n", src=_TEST_SOURCE)
        s.run("MATCH (d:Document {id: $src}) DETACH DELETE d", src=_TEST_SOURCE)


# ── NEO4J-001: Connection ─────────────────────────────────────────────────────

def test_neo4j_001_connection(manager):
    """NEO4J-001: test_connection() returns True when Docker is running."""
    assert manager.test_connection() is True


# ── NEO4J-002: Schema idempotency ─────────────────────────────────────────────

def test_neo4j_002_schema_idempotent(manager):
    """NEO4J-002: init_schema() can be called twice without raising."""
    manager.init_schema()
    manager.init_schema()  # second call must be no-op


# ── NEO4J-003: Upsert triplets ────────────────────────────────────────────────

def test_neo4j_003_upsert_triplets(manager):
    """NEO4J-003: 3 triplets → 4 Entity nodes, 3 RELATES_TO edges in DB."""
    upsert_triplets(_SAMPLE_TRIPLETS)

    with manager.session() as s:
        n_nodes = s.run(
            "MATCH (n:Entity) WHERE n.id IN $ids RETURN count(n) AS cnt",
            ids=[
                "default::entity::noma",
                "default::entity::sic",
                "default::entity::spectral_efficiency",
                "default::entity::interference",
            ],
        ).single()["cnt"]

        n_edges = s.run(
            "MATCH ()-[r:RELATES_TO]->() WHERE $src IN coalesce(r.source_files, []) RETURN count(r) AS cnt",
            src=_TEST_SOURCE,
        ).single()["cnt"]

    assert n_nodes == 4, f"Expected 4 nodes, got {n_nodes}"
    assert n_edges == 3, f"Expected 3 edges, got {n_edges}"


# ── NEO4J-004: Dedup (weight increment) ───────────────────────────────────────

def test_neo4j_004_upsert_dedup(manager):
    """NEO4J-004: Replaying the same triplet chunk does not inflate weight."""
    dup = KGTriplet(subject="NOMA", relation="DEPENDS_ON", object="SIC",
                    source=_TEST_SOURCE, page=1, chunk_id="c1")
    upsert_triplets([dup])  # second upsert of same triplet

    with manager.session() as s:
        weight = s.run(
            """
            MATCH (a:Entity {id: $subject_id})-[r:RELATES_TO {relation: 'DEPENDS_ON'}]->(b:Entity {id: $object_id})
            RETURN r.weight AS w
            """,
            subject_id="default::entity::noma",
            object_id="default::entity::sic",
        ).single()["w"]

        edge_count = s.run(
            """
            MATCH (a:Entity {id: $subject_id})-[r:RELATES_TO]->(b:Entity {id: $object_id})
            RETURN count(r) AS cnt
            """,
            subject_id="default::entity::noma",
            object_id="default::entity::sic",
        ).single()["cnt"]

    assert weight == 1, f"Expected replay-safe weight 1, got {weight}"
    assert edge_count == 1, f"Expected 1 edge, got {edge_count} (duplicate!)"


# ── NEO4J-005: Visual nodes ───────────────────────────────────────────────────

def test_neo4j_005_visual_nodes(manager):
    """NEO4J-005: upsert_visual_nodes() creates Formula node with APPEARS_IN edge."""
    parsed = FakeParsed(
        formulas=[{"formula_id": "f001", "latex_string": r"P_{g,n}"}],
    )
    count = upsert_visual_nodes(parsed, _TEST_SOURCE)
    assert count == 1

    with manager.session() as s:
        exists = s.run(
            """
            MATCH (f:Formula {id: 'default::formula::f001'})-[:APPEARS_IN]->(d:Document {id: $doc_id})
            WHERE f.workspace_id = 'default' AND d.workspace_id = 'default'
            """
            "RETURN count(f) AS cnt",
            doc_id="default::document::_pytest_test_paper.pdf",
        ).single()["cnt"]

    assert exists == 1


# ── NEO4J-006: lookup_kg_context with match ───────────────────────────────────

def test_neo4j_006_lookup_with_match(manager):
    """NEO4J-006: lookup_kg_context('NOMA') returns context plus KG sources."""
    ctx, sources = lookup_kg_context("What does NOMA depend on?", verbose=False)
    assert isinstance(ctx, str)
    assert isinstance(sources, list)
    assert len(ctx) > 0
    assert "##" in ctx
    assert "[KG-01]" in ctx
    assert sources[0]["id"] == "KG-01"
    assert sources[0]["source_file"] == _TEST_SOURCE
    assert sources[0]["page"] > 0


# ── NEO4J-007: lookup_kg_context no match ─────────────────────────────────────

def test_neo4j_007_lookup_no_match():
    """NEO4J-007: lookup_kg_context with no-match term returns empty tuple without crash."""
    ctx, sources = lookup_kg_context("xyzzy_nonexistent_term_12345", verbose=False)
    assert isinstance(ctx, str)
    assert isinstance(sources, list)
    # May return empty or a general result — must not crash


# ── NEO4J-008: delete_document_kg ────────────────────────────────────────────

def test_neo4j_008_delete_document(manager):
    """NEO4J-008: delete_document_kg removes edges; orphan nodes pruned."""
    removed = delete_document_kg(_TEST_SOURCE)
    assert removed >= 3  # at least 3 RELATES_TO edges from test data

    with manager.session() as s:
        remaining_edges = s.run(
            "MATCH ()-[r:RELATES_TO]->() WHERE $src IN coalesce(r.source_files, []) RETURN count(r) AS cnt",
            src=_TEST_SOURCE,
        ).single()["cnt"]
    assert remaining_edges == 0


# ── NEO4J-009: get_graph_for_viz ─────────────────────────────────────────────

def test_neo4j_009_get_graph_for_viz(manager):
    """NEO4J-009: get_graph_for_viz() returns dict with nodes/edges; nodes have degree key."""
    # Re-insert test data for visualization check
    upsert_triplets(_SAMPLE_TRIPLETS)
    result = get_graph_for_viz(limit=50)

    assert isinstance(result, dict)
    assert "nodes" in result
    assert "edges" in result

    if result["nodes"]:
        node = result["nodes"][0]
        assert "degree" in node, "Node must have 'degree' key (Correction #2)"
        assert "id" in node
        assert "label" in node


# ── NEO4J-010: UsageTracker ───────────────────────────────────────────────────

def test_neo4j_010_usage_tracker():
    """NEO4J-010: UsageTracker.add() increments calls, tokens, and cost."""
    tracker = UsageTracker()
    tracker.add(FakeUsage(prompt=100, completion=50))

    assert tracker.calls == 1
    assert tracker.prompt_tokens == 100
    assert tracker.completion_tokens == 50
    total = tracker.summary()["total_tokens"]
    assert total == 150
    cost = tracker.estimated_cost_usd
    assert cost > 0.0

    tracker.reset()
    assert tracker.calls == 0
    assert tracker.summary()["total_tokens"] == 0


# ── NEO4J-011: run_kg_step integration (mock) ────────────────────────────────

def test_neo4j_011_run_kg_step_mock(manager):
    """NEO4J-011: run_kg_step() with pre-seeded triplets → DB has nodes/edges."""
    # Directly upsert via kg_neo4j to simulate what run_kg_step does
    test_triplets = [
        KGTriplet("BeamForming", "IMPROVES", "SINR",
                  source="_pytest_run_kg.pdf", page=1, chunk_id="ck1"),
    ]
    upsert_triplets(test_triplets)

    with manager.session() as s:
        cnt = s.run(
            """
            MATCH ()-[r:RELATES_TO]->()
            WHERE $src IN coalesce(r.source_files, [])
            RETURN count(r) AS cnt
            """,
            src="_pytest_run_kg.pdf",
        ).single()["cnt"]
    assert cnt >= 1

    # Cleanup
    delete_document_kg("_pytest_run_kg.pdf")


# ── NEO4J-012: Full delete flow ───────────────────────────────────────────────

def test_neo4j_012_full_delete_flow(manager):
    """NEO4J-012: After delete_document_kg, Neo4j has no edges for that source."""
    src = "_pytest_full_delete.pdf"
    upsert_triplets([
        KGTriplet("Alpha", "SUPPORTS", "Beta", source=src, page=1, chunk_id="x"),
    ])
    removed = delete_document_kg(src)
    assert removed >= 1

    with manager.session() as s:
        cnt = s.run(
            "MATCH ()-[r:RELATES_TO]->() WHERE $src IN coalesce(r.source_files, []) RETURN count(r) AS cnt",
            src=src,
        ).single()["cnt"]
    assert cnt == 0


# ── NEO4J-013: Workspace isolation ────────────────────────────────────────────

def test_neo4j_013_workspace_isolation_for_upsert_lookup_viz_delete_and_visuals(manager):
    """Same entity/file names in two workspaces remain isolated across KG operations."""
    workspace_a = "workspace-a"
    workspace_b = "workspace-b"
    parsed = FakeParsed(
        formulas=[{"formula_id": "f-shared", "latex_string": "x+y", "page": 4}],
        images=[{"image_id": "img-shared", "caption": "shared figure", "page": 5}],
    )

    upsert_triplets([
        KGTriplet(
            subject="Shared Entity",
            relation="ENABLES",
            object="Alpha Target",
            source=_WORKSPACE_SOURCE,
            page=4,
            chunk_id="shared-c1",
            workspace_id=workspace_a,
        ),
    ])
    upsert_triplets([
        KGTriplet(
            subject="Shared Entity",
            relation="ENABLES",
            object="Alpha Target",
            source=_WORKSPACE_SOURCE,
            page=4,
            chunk_id="shared-c1",
            workspace_id=workspace_a,
        ),
        KGTriplet(
            subject="Shared Entity",
            relation="ENABLES",
            object="Beta Target",
            source=_WORKSPACE_SOURCE,
            page=4,
            chunk_id="shared-c1",
            workspace_id=workspace_b,
        ),
    ])
    upsert_visual_nodes(parsed, _WORKSPACE_SOURCE, workspace_id=workspace_a)
    upsert_visual_nodes(parsed, _WORKSPACE_SOURCE, workspace_id=workspace_b)

    ctx_a, sources_a = lookup_kg_context(
        "What does Shared Entity enable?",
        use_llm_entity_extract=False,
        workspace_id=workspace_a,
        selected_files=[_WORKSPACE_SOURCE],
        verbose=False,
    )
    graph_a = get_graph_for_viz(
        limit=20,
        source_files=[_WORKSPACE_SOURCE],
        workspace_id=workspace_a,
    )

    with manager.session() as s:
        rel_a = s.run(
            """
            MATCH (a:Entity {id: $subject_id})-[r:RELATES_TO]->(b:Entity {id: $object_id})
            RETURN r.weight AS weight, a.mentions AS subject_mentions, b.mentions AS object_mentions
            """,
            subject_id="workspace-a::entity::shared_entity",
            object_id="workspace-a::entity::alpha_target",
        ).single()
        visual_counts = s.run(
            """
            MATCH (d:Document {source_file: $source})
            OPTIONAL MATCH (v)-[:APPEARS_IN]->(d)
            RETURN d.workspace_id AS workspace_id, count(v) AS visual_count
            ORDER BY workspace_id
            """,
            source=_WORKSPACE_SOURCE,
        ).data()

    assert rel_a["weight"] == 1
    assert rel_a["subject_mentions"] == 1
    assert rel_a["object_mentions"] == 1
    assert "Alpha Target" in ctx_a
    assert "Beta Target" not in ctx_a
    assert sources_a[0]["source_file"] == _WORKSPACE_SOURCE
    assert {edge["to"] for edge in graph_a["edges"]} == {"workspace-a::entity::alpha_target"}
    assert visual_counts == [
        {"workspace_id": workspace_a, "visual_count": 2},
        {"workspace_id": workspace_b, "visual_count": 2},
    ]

    removed = delete_document_kg(_WORKSPACE_SOURCE, workspace_id=workspace_a)
    assert removed == 5

    with manager.session() as s:
        remaining = s.run(
            """
            MATCH ()-[r:RELATES_TO]->()
            WHERE $source IN coalesce(r.source_files, [])
            RETURN r.workspace_id AS workspace_id, count(r) AS count
            ORDER BY workspace_id
            """,
            source=_WORKSPACE_SOURCE,
        ).data()
        documents = s.run(
            """
            MATCH (d:Document {source_file: $source})
            RETURN d.workspace_id AS workspace_id
            ORDER BY workspace_id
            """,
            source=_WORKSPACE_SOURCE,
        ).data()

    assert remaining == [{"workspace_id": workspace_b, "count": 1}]
    assert documents == [{"workspace_id": workspace_b}]


def test_neo4j_014_delete_document_preserves_multi_source_relationship(manager):
    """Deleting one file removes its evidence without dropping an edge supported by another file."""
    workspace_id = "workspace-multi-source"
    source_a = "_pytest_multi_source_a.pdf"
    source_b = "_pytest_multi_source_b.pdf"

    upsert_triplets([
        KGTriplet(
            subject="Shared Edge",
            relation="SUPPORTS",
            object="Durable Relation",
            source=source_a,
            page=1,
            chunk_id="chunk-a",
            workspace_id=workspace_id,
            evidence_preview="Evidence from source A.",
        ),
        KGTriplet(
            subject="Shared Edge",
            relation="SUPPORTS",
            object="Durable Relation",
            source=source_b,
            page=2,
            chunk_id="chunk-b",
            workspace_id=workspace_id,
            evidence_preview="Evidence from source B.",
        ),
    ])

    ctx_b, sources_b = lookup_kg_context(
        "How does Shared Edge support Durable Relation?",
        use_llm_entity_extract=False,
        selected_files=[source_b],
        workspace_id=workspace_id,
        verbose=False,
    )
    ctx_empty_filter, sources_empty_filter = lookup_kg_context(
        "How does Shared Edge support Durable Relation?",
        use_llm_entity_extract=False,
        selected_files=[],
        workspace_id=workspace_id,
        verbose=False,
    )

    assert "Durable Relation" in ctx_b
    assert sources_b[0]["source_file"] == source_b
    assert sources_b[0]["source_file"] != source_a
    assert sources_b[0]["page"] == 0
    assert sources_b[0]["chunk_id"] == ""
    assert sources_b[0]["evidence_preview"] == ""
    assert sources_b[0]["has_document_evidence"] is False
    assert "Durable Relation" in ctx_empty_filter
    assert sources_empty_filter

    delete_document_kg(source_a, workspace_id=workspace_id)

    _ctx_after_delete, sources_after_delete = lookup_kg_context(
        "How does Shared Edge support Durable Relation?",
        use_llm_entity_extract=False,
        selected_files=[source_b],
        workspace_id=workspace_id,
        verbose=False,
    )

    with manager.session() as s:
        row = s.run(
            """
            MATCH (a:Entity {id: $subject_id})-[r:RELATES_TO {relation: 'SUPPORTS'}]->(b:Entity {id: $object_id})
            RETURN r.source_files AS source_files,
                   r.weight AS weight,
                   r.pages AS pages,
                   r.chunk_ids AS chunk_ids,
                   r.evidence_preview AS evidence_preview
            """,
            subject_id="workspace-multi-source::entity::shared_edge",
            object_id="workspace-multi-source::entity::durable_relation",
        ).single()

    assert row is not None
    assert row["source_files"] == [source_b]
    assert source_a not in row["source_files"]
    assert row["weight"] == 1
    assert row["pages"] == []
    assert row["chunk_ids"] == ["chunk-b"]
    assert row["evidence_preview"] == ""
    assert sources_after_delete[0]["source_file"] == source_b
    assert sources_after_delete[0]["page"] == 0
    assert sources_after_delete[0]["chunk_id"] == ""
    assert sources_after_delete[0]["evidence_preview"] == ""
    assert sources_after_delete[0]["has_document_evidence"] is False


def test_neo4j_015_rag_prepare_empty_selected_files_keeps_kg_context(manager, monkeypatch):
    """selected_files=[] means no file filter, including through rag_prepare."""
    import query.engine as engine

    workspace_id = "workspace-empty-selected-files"
    source = "_pytest_rag_prepare_empty_filter.pdf"
    captured = {}

    upsert_triplets([
        KGTriplet(
            subject="Empty Filter Entity",
            relation="ENABLES",
            object="Empty Filter Target",
            source=source,
            page=3,
            chunk_id="empty-filter-c1",
            workspace_id=workspace_id,
        ),
    ])

    def fake_build_prompt(*args, **kwargs):
        captured["kg_context"] = kwargs.get("kg_context", "")
        return "system", "user", ["source"]

    monkeypatch.setattr(
        engine,
        "retrieve_vectors",
        lambda *_args, **_kwargs: (
            ["Empty Filter Entity enables Empty Filter Target."],
            [{"file_name": source, "page": 3, "section_label": "kg-test", "chunk_id": "empty-filter-c1"}],
            [0.1],
            [0.1, 0.2],
        ),
    )
    monkeypatch.setattr(engine, "retrieve_full_visual_context", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(engine, "build_prompt", fake_build_prompt)

    prepared = engine.rag_prepare(
        "How does Empty Filter Entity enable Empty Filter Target?",
        retrieve_k=1,
        top_n=1,
        use_rerank=False,
        use_cache=False,
        kg_mode="default",
        selected_files=[],
        workspace_id=workspace_id,
        use_visuals=False,
    )

    assert "Empty Filter Target" in prepared["kg_context"]
    assert "Empty Filter Target" in captured["kg_context"]
    assert prepared["kg_sources"][0]["has_document_evidence"] is True
