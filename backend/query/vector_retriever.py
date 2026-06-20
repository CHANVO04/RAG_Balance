from typing import Tuple, List, Dict, Optional
from query.clients import get_collection, get_embedder


def retrieve_vectors(
    question: str,
    retrieve_k: int,
    selected_files: Optional[List[str]] = None,
    workspace_id: Optional[str] = None,
) -> Tuple[List[str], List[Dict], List[float], List[float]]:
    """
    Tìm Top-K chunks text từ Qdrant (rag_docs).
    Returns (raw_docs, raw_metas, scores, q_emb)

    Bug 2 fix: query_points() returns ScoredPoint objects.
    We unpack payload["document"] → raw_docs, remaining payload → raw_metas.
    scores are similarities [0,1] (higher = more relevant) — NOT distances.
    """
    from qdrant_client.http import models
    print(f"[VECTOR] Nhúng câu hỏi và tìm Top-{retrieve_k} chunks...")
    client, col_name = get_collection("rag_docs")

    embedder = get_embedder()
    q_emb    = embedder.encode(question, normalize_embeddings=True).tolist()

    must = []
    if workspace_id:
        must.append(models.FieldCondition(
            key="workspace_id",
            match=models.MatchValue(value=workspace_id),
        ))
    if selected_files:
        must.append(models.FieldCondition(
            key="file_name",
            match=models.MatchAny(any=selected_files),
        ))
    query_filter = models.Filter(must=must) if must else None

    results = client.query_points(
        collection_name=col_name,
        query=q_emb,
        query_filter=query_filter,
        limit=retrieve_k,
        with_payload=True,
    )

    raw_docs:  List[str]        = []
    raw_metas: List[Dict]       = []
    scores:    List[float]      = []

    for point in results.points:
        payload = dict(point.payload)                    # shallow copy
        doc     = payload.pop("document", "")            # extract text
        raw_docs.append(doc)
        raw_metas.append(payload)
        scores.append(float(point.score))

    return raw_docs, raw_metas, scores, q_emb
