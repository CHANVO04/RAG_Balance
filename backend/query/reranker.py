from typing import List, Tuple, Dict, Set
from query.clients import get_reranker


def rerank_results(
    question: str,
    raw_docs: List[str],
    raw_metas: List[Dict],
    scores: List[float],      # Qdrant similarities [0,1], higher = more relevant
    top_n: int,
    use_rerank: bool,
) -> Tuple[List[Tuple[str, Dict, float]], Set[int], Set[str]]:

    ranked_results = []
    if use_rerank:
        print(f"[RERANK] Đang chấm điểm lại (Cross-Encoder) lấy Top-{top_n}...")
        reranker = get_reranker()
        pairs    = [[question, doc] for doc in raw_docs]
        ce_scores = reranker.predict(pairs)
        combined  = sorted(zip(ce_scores, raw_docs, raw_metas), key=lambda x: x[0], reverse=True)
        for score, doc, meta in combined[:top_n]:
            ranked_results.append((doc, meta, float(score)))
    else:
        # scores are already similarities from Qdrant — use directly (no 1-dist inversion)
        for doc, meta, score in zip(raw_docs, raw_metas, scores):
            ranked_results.append((doc, meta, score))
        ranked_results = ranked_results[:top_n]

    pages_needed = set(
        int(m.get("page", 0))
        for _, m, _ in ranked_results
        if m.get("page") is not None
    )
    files_needed = set(
        m.get("file_name", "")
        for _, m, _ in ranked_results
        if m.get("file_name", "")
    )

    return ranked_results, pages_needed, files_needed
