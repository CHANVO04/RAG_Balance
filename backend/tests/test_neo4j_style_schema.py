from types import SimpleNamespace

import kg_neo4j_config as config
import kg_neo4j_extractor as extractor
import kg_neo4j_ops
from kg_neo4j_manager import KGTriplet


def test_schema_creates_hot_bridge_indexes():
    joined = "\n".join(config.SCHEMA_QUERIES)

    assert "FOR (c:Chunk) REQUIRE c.id IS UNIQUE" in joined
    assert "FOR (c:Chunk) ON (c.workspace_id, c.chunk_id)" in joined
    assert "FOR (e:Entity) ON (e.workspace_id, e.canonical_key)" in joined
    assert "FOR (d:Document) ON (d.workspace_id, d.file_name)" in joined


def test_anchored_context_query_uses_chunk_id_parameter_list_and_workspace_filters():
    query = config.ANCHORED_KG_CONTEXT_CYPHER

    assert "c.chunk_id IN $chunk_ids" in query
    assert "c.workspace_id = $workspace_id" in query
    assert "RELATES_TO*1.." in query
    assert "$hops" not in query
    assert "all(r IN relList WHERE r.workspace_id = $workspace_id)" in query
    assert "APPEARS_IN" not in query


def test_anchored_context_helper_clamps_variable_hops():
    assert "RELATES_TO*1..1" in config.anchored_kg_context_cypher(0)
    assert "RELATES_TO*1..2" in config.anchored_kg_context_cypher(2)
    assert "RELATES_TO*1..3" in config.anchored_kg_context_cypher(99)
    assert "$hops" not in config.anchored_kg_context_cypher(2)


def test_graph_viz_defaults_to_entity_first():
    query = config.GET_ENTITY_GRAPH_VIZ_CYPHER

    assert "MATCH (a:Entity" in query
    assert "RELATES_TO" in query
    assert "Chunk" not in query


def test_chunk_debug_graph_applies_source_filter_to_all_node_types():
    query = config.GET_GRAPH_WITH_CHUNKS_VIZ_CYPHER

    assert "WHERE (n:Document OR n:Chunk OR n:Entity)" in query
    assert "WHERE n:Document OR n:Chunk OR n:Entity\n  AND" not in query
    assert "n.workspace_id = $workspace_id" in query
    assert "r.workspace_id = $workspace_id" in query
    assert "m.workspace_id = $workspace_id" in query


def test_bfs_context_query_filters_by_workspace_id():
    query = config.BFS_CONTEXT_CYPHER
    assert "seed.workspace_id = $workspace_id" in query
    assert "nb.workspace_id = $workspace_id" in query
    assert "all(rel IN relationships(path) WHERE rel.workspace_id = $workspace_id)" in query
    assert "r.workspace_id = $workspace_id" in query


def test_delete_document_cypher_removes_chunks_and_prunes_orphan_entities():
    query = config.DELETE_DOCUMENT_GRAPH_CYPHER

    assert "MATCH (d:Document" in query
    assert "workspace_id: $workspace_id" in query
    assert "deleted_chunk_ids" in query
    assert "size(coalesce(r.source_files, [])) > 1" in query
    assert "source <> $file_name" in query
    assert "NOT chunk_id IN deleted_chunk_ids" in query
    assert "size(coalesce(r.source_files, [])) <= 1" in query
    assert "MATCH ()-[r:RELATES_TO {workspace_id: $workspace_id}]->()" in query
    assert "$file_name IN coalesce(r.source_files, [])" in query
    assert "DELETE r" in query
    assert "DETACH DELETE c" in query
    assert "DETACH DELETE e" in query


def test_entity_relation_cypher_guards_mentions_against_chunk_replay():
    query = config.UPSERT_ENTITY_RELATION_CYPHER

    assert "$chunk_id IN coalesce(r.chunk_ids, []) AS is_replay" in query
    assert "s.mentions = CASE WHEN is_replay" in query
    assert "o.mentions = CASE WHEN is_replay" in query
    assert "s.mentions = coalesce(s.mentions, 0) + 1" not in query
    assert "o.mentions = coalesce(o.mentions, 0) + 1" not in query


class RecordingSession:
    def __init__(self, result=None):
        self.calls = []
        self.result = result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def run(self, query, **params):
        self.calls.append((query, params))
        return self.result or []


class DeleteResult:
    def single(self):
        return {"removed": 3}


def test_delete_document_kg_runs_neo4j_style_graph_delete(monkeypatch):
    session = RecordingSession(result=DeleteResult())
    monkeypatch.setattr(
        kg_neo4j_ops,
        "get_neo4j_manager",
        lambda: SimpleNamespace(session=lambda: session),
    )

    removed = kg_neo4j_ops.delete_document_kg("paper.pdf", workspace_id="hybrid_ws")

    assert removed == 3
    assert session.calls == [
        (
            config.DELETE_DOCUMENT_GRAPH_CYPHER,
            {"file_name": "paper.pdf", "workspace_id": "hybrid_ws"},
        )
    ]


def test_upsert_hybrid_chunk_graph_writes_document_chunk_and_relation():
    session = RecordingSession()
    chunks = [
        SimpleNamespace(
            chunk_id="chunk-1",
            text="The CNN model runs on the K210 KPU.",
            page=3,
            section_label="Method",
            content_type="text",
            visual_ids=[],
        )
    ]
    triplets = [
        KGTriplet(
            subject="CNN",
            subject_type="Model",
            subject_key="cnn",
            relation="RUNS_ON",
            object="K210 KPU",
            object_type="Hardware",
            object_key="k210_kpu",
            source="paper.pdf",
            page=3,
            chunk_id="chunk-1",
            workspace_id="hybrid_ws",
            evidence_preview="CNN model runs on the K210 KPU.",
            confidence=0.8,
        )
    ]

    written = kg_neo4j_ops.upsert_hybrid_chunk_graph(
        session=session,
        chunks=chunks,
        triplets=triplets,
        file_name="paper.pdf",
        workspace_id="hybrid_ws",
        file_hash="hash",
        total_pages=6,
    )

    queries = "\n".join(query for query, _params in session.calls)
    assert written == 1
    assert "MERGE (d:Document" in queries
    assert "MERGE (c:Chunk" in queries
    assert "MERGE (s)-[sf:FROM_CHUNK" in queries
    assert "MERGE (s)-[r:RELATES_TO" in queries


def test_upsert_hybrid_chunk_graph_writes_chunks_without_triplets():
    session = RecordingSession()
    chunks = [
        SimpleNamespace(
            chunk_id="chunk-empty",
            text="This chunk has no extractable graph relation.",
            page=1,
            section_label="Abstract",
            content_type="text",
        )
    ]

    written = kg_neo4j_ops.upsert_hybrid_chunk_graph(
        session=session,
        chunks=chunks,
        triplets=[],
        file_name="paper.pdf",
        workspace_id="hybrid_ws",
    )

    queries = "\n".join(query for query, _params in session.calls)
    assert written == 0
    assert "MERGE (d:Document" in queries
    assert "MERGE (c:Chunk" in queries


def test_upsert_hybrid_chunk_graph_skips_forbidden_relation_at_write_boundary():
    session = RecordingSession()
    chunk = SimpleNamespace(
        chunk_id="chunk-1",
        text="The model uses the dataset.",
        page=1,
        section_label="Method",
        content_type="text",
    )
    triplet = KGTriplet(
        subject="Model",
        relation="uses",
        object="Dataset",
        source="paper.pdf",
        page=1,
        chunk_id="chunk-1",
        workspace_id="hybrid_ws",
        evidence_preview="The model uses the dataset.",
    )

    written = kg_neo4j_ops.upsert_hybrid_chunk_graph(
        session=session,
        chunks=[chunk],
        triplets=[triplet],
        file_name="paper.pdf",
        workspace_id="hybrid_ws",
    )

    assert written == 0
    assert all(
        query != config.UPSERT_ENTITY_RELATION_CYPHER
        for query, _params in session.calls
    )


def test_upsert_hybrid_chunk_graph_normalizes_relation_and_entity_types_at_write_boundary():
    session = RecordingSession()
    chunk = SimpleNamespace(
        chunk_id="chunk-1",
        text="The CNN model runs on the K210 KPU.",
        page=3,
        section_label="Method",
        content_type="text",
    )
    triplet = KGTriplet(
        subject="  CNN  ",
        subject_type="UnknownType",
        relation="runs on",
        object=" K210 KPU ",
        object_type="Hardware",
        source="paper.pdf",
        page=3,
        chunk_id="chunk-1",
        workspace_id="hybrid_ws",
        evidence_preview="CNN model runs on the K210 KPU.",
    )

    written = kg_neo4j_ops.upsert_hybrid_chunk_graph(
        session=session,
        chunks=[chunk],
        triplets=[triplet],
        file_name="paper.pdf",
        workspace_id="hybrid_ws",
    )

    relation_calls = [
        params
        for query, params in session.calls
        if query == config.UPSERT_ENTITY_RELATION_CYPHER
    ]
    assert written == 1
    assert relation_calls[0]["subject"] == "CNN"
    assert relation_calls[0]["object"] == "K210 KPU"
    assert relation_calls[0]["relation"] == "RUNS_ON"
    assert relation_calls[0]["subject_type"] == "Concept"
    assert relation_calls[0]["object_type"] == "Hardware"
    assert relation_calls[0]["subject_key"] == "cnn"
    assert relation_calls[0]["object_key"] == "k210_kpu"


def test_legacy_upsert_triplets_returns_zero_for_forbidden_relation(monkeypatch, capsys):
    def fail_if_db_requested():
        raise AssertionError("Forbidden legacy triplet should not request Neo4j")

    monkeypatch.setattr(extractor, "get_neo4j_manager", fail_if_db_requested)

    written = extractor.upsert_triplets([
        KGTriplet(
            subject="Model",
            relation="uses",
            object="Dataset",
            source="paper.pdf",
            page=1,
            chunk_id="chunk-1",
        )
    ])

    captured = capsys.readouterr()
    assert written == 0
    assert "skipped 1" in captured.out.lower()
