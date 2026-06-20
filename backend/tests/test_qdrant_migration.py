"""
backend/tests/test_qdrant_migration.py
Run from backend/ directory:
    pytest tests/test_qdrant_migration.py -v

Requires Qdrant running on localhost:6333.
"""

from __future__ import annotations

import uuid
import numpy as np
import pytest

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchAny, MatchValue,
    PointStruct, VectorParams,
)

# ── Shared client ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def client():
    c = QdrantClient(host="localhost", port=6333)
    return c


# ── T01: Connection ───────────────────────────────────────────────────────────
def test_T01_connection(client):
    info = client.get_collections()
    assert info is not None, "Qdrant không phản hồi"


# ── T02: active collections tồn tại với đúng config ───────────────────────────
def test_T02_collections_exist(client):
    from ingest.vector_store import ensure_all_collections
    ensure_all_collections(client)

    for name in ["rag_docs", "rag_visuals"]:
        assert client.collection_exists(name), f"Collection '{name}' không tồn tại"

    # Kiểm tra dim
    docs_info  = client.get_collection("rag_docs")
    visuals_info = client.get_collection("rag_visuals")

    assert docs_info.config.params.vectors.size == 1536
    assert visuals_info.config.params.vectors.size == 1


# ── T03: Upsert + retrieve + idempotent ───────────────────────────────────────
_TEST_DOC_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "test_chunk_abc123"))
_TEST_VECTOR = list(np.random.rand(1536).astype(float))

def test_T03_upsert_and_retrieve(client):
    point = PointStruct(
        id=_TEST_DOC_ID,
        vector=_TEST_VECTOR,
        payload={
            "document":  "Test chunk text",
            "file_name": "__test__.pdf",
            "page":      1,
            "chunk_index": 0,
            "has_table": False,
        },
    )
    client.upsert("rag_docs", points=[point])

    # Idempotent — upsert lại phải không sinh duplicate
    client.upsert("rag_docs", points=[point])

    results, _ = client.scroll(
        "rag_docs",
        scroll_filter=Filter(must=[FieldCondition(key="file_name", match=MatchValue(value="__test__.pdf"))]),
        with_payload=True,
        with_vectors=False,
        limit=100,
    )
    ids = [str(r.id) for r in results]
    assert ids.count(_TEST_DOC_ID) == 1, "Idempotency failed — duplicate found"


# ── T04: query_points() search (KHÔNG phải search()) ─────────────────────────
def test_T04_query_points(client):
    q = list(np.random.rand(1536).astype(float))
    results = client.query_points("rag_docs", query=q, limit=5, with_payload=True)
    # Chỉ cần không throw — API đúng
    assert hasattr(results, "points"), "query_points() không trả về .points attribute"


# ── T05: scroll() filter visuals — MatchAny ───────────────────────────────────
def test_T05_scroll_visuals_matchany(client):
    # Upsert 2 visual points với file_name khác nhau
    for i, fname in enumerate(["paper_a.pdf", "paper_b.pdf"]):
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"visual_{fname}"))
        client.upsert("rag_visuals", points=[
            PointStruct(id=pid, vector=[0.0], payload={
                "document":  f"Visual content {i}",
                "file_name": fname,
                "page":      1,
                "visual_id": f"table_{i}",
                "visual_type": "table",
            })
        ])

    records, _ = client.scroll(
        "rag_visuals",
        scroll_filter=Filter(must=[FieldCondition(
            key="file_name",
            match=MatchAny(any=["paper_a.pdf", "paper_b.pdf"]),
        )]),
        with_payload=True, with_vectors=False, limit=100,
    )
    fnames = {r.payload["file_name"] for r in records}
    assert "paper_a.pdf" in fnames and "paper_b.pdf" in fnames, "MatchAny filter không hoạt động"


# ── T06: visual formula page key ──────────────────────────────────────────────
def test_T06_visual_formula_page_key(client):
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, "formula_test_page_key"))
    client.upsert("rag_visuals", points=[
        PointStruct(id=pid, vector=[0.0], payload={
            "document":    r"\sigma^2",
            "file_name":   "__test__.pdf",
            "visual_id":   "formula_2_1",
            "visual_type": "formula",
            "formula_id":  "formula_2_1",
            "source_page": 2,
            "page":        2,        # Bug fix: both keys present
            "is_decoded":  True,
            "latex_string": r"\sigma^2",
        })
    ])

    records, _ = client.scroll(
        "rag_visuals",
        scroll_filter=Filter(must=[FieldCondition(
            key="file_name", match=MatchValue(value="__test__.pdf")
        )]),
        with_payload=True, with_vectors=False, limit=100,
    )
    pages = [r.payload.get("page") for r in records]
    assert 2 in pages, "Bug fix: 'page' key missing from formula payload"

    source_pages = [r.payload.get("source_page") for r in records]
    assert 2 in source_pages, "'source_page' key missing from formula payload"


# ── T07: visual lookup by ID ──────────────────────────────────────────────────
def test_T07_visual_lookup_by_id(client):
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, "image_test_lookup"))
    client.upsert("rag_visuals", points=[
        PointStruct(id=pid, vector=[0.0], payload={
            "document":       "Accuracy graph summary",
            "file_name":      "__test__.pdf",
            "visual_id":      "img_5_3",
            "visual_type":    "image",
            "analysis_full":  "Full image analysis",
            "page":           5,
        })
    ])

    records, _ = client.scroll(
        "rag_visuals",
        scroll_filter=Filter(must=[FieldCondition(
            key="visual_id", match=MatchValue(value="img_5_3")
        )]),
        with_payload=True, with_vectors=False, limit=10,
    )
    assert any(r.payload.get("analysis_full") == "Full image analysis" for r in records)


# ── T08: delete_from_qdrant ───────────────────────────────────────────────────
def test_T08_delete_from_qdrant(client):
    from ingest.vector_store import delete_from_qdrant

    # Upsert test point
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, "delete_test_chunk"))
    client.upsert("rag_docs", points=[
        PointStruct(id=pid, vector=list(np.random.rand(1536).astype(float)),
                    payload={"document": "del me", "file_name": "__delete_test__.pdf", "page": 1})
    ])

    removed = delete_from_qdrant(client, "__delete_test__.pdf")
    assert removed["rag_docs"] >= 1, "delete_from_qdrant không xóa được rag_docs"

    # Verify gone
    records, _ = client.scroll(
        "rag_docs",
        scroll_filter=Filter(must=[FieldCondition(
            key="file_name", match=MatchValue(value="__delete_test__.pdf")
        )]),
        with_payload=True, with_vectors=False, limit=10,
    )
    assert len(records) == 0, "Điểm vẫn còn trong DB sau delete"


# ── T09: query/clients connection singleton ──────────────────────────────────
def test_T09_clients_singleton():
    from query.clients import get_qdrant_client, get_collection
    c1 = get_qdrant_client()
    c2 = get_qdrant_client()   # singleton check
    assert c1 is c2, "get_qdrant_client() phải trả về cùng singleton Qdrant client"

    # get_collection returns (client, name) tuple
    client_obj, col_name = get_collection("rag_docs")
    assert col_name == "rag_docs"
    assert hasattr(client_obj, "query_points")


# ── T10: reranker scores format ───────────────────────────────────────────────
def test_T10_reranker_scores_format():
    from query.reranker import rerank_results

    raw_docs  = ["NOMA is a multiple access technique.", "PB-NOMA improves throughput."]
    raw_metas = [
        {"file_name": "a.pdf", "page": 1},
        {"file_name": "a.pdf", "page": 2},
    ]
    scores = [0.85, 0.72]   # Qdrant similarity scores

    ranked, pages, files = rerank_results(
        question="What is NOMA?",
        raw_docs=raw_docs,
        raw_metas=raw_metas,
        scores=scores,
        top_n=2,
        use_rerank=False,
    )

    assert len(ranked) == 2
    for doc, meta, sc in ranked:
        assert isinstance(sc, float), "Score phải là float"
        # No 1-dist inversion — score should be original similarity
        assert 0.0 <= sc <= 1.01, f"Score out of range (1-dist bug?): {sc}"

    assert 1 in pages and 2 in pages
    assert "a.pdf" in files


# ── T11: full pipeline smoke test ────────────────────────────────────────────
def test_T11_full_pipeline_smoke():
    """
    Smoke test: query pipeline returns valid structure.
    Requires Qdrant with at least 1 ingested document.
    """
    try:
        from query.engine import rag_query
        result = rag_query(
            question="What is NOMA?",
            retrieve_k=5,
            top_n=2,
            use_rerank=False,
            use_cache=False,
        )
        assert "answer" in result, "rag_query() phải trả về dict có key 'answer'"
        assert isinstance(result["answer"], str)
    except RuntimeError as e:
        if "chưa tồn tại" in str(e) or "Collection" in str(e):
            pytest.skip("Chưa ingest dữ liệu — bỏ qua smoke test")
        raise


# ── Cleanup ───────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True, scope="session")
def cleanup(client):
    yield
    # Xóa test data sau khi toàn bộ session xong
    for col in ["rag_docs", "rag_visuals"]:
        try:
            client.delete(
                col,
                points_selector=Filter(must=[FieldCondition(
                    key="file_name",
                    match=MatchAny(any=["__test__.pdf", "__delete_test__.pdf",
                                        "paper_a.pdf", "paper_b.pdf"]),
                )]),
                wait=True,
            )
        except Exception:
            pass
