from __future__ import annotations


def test_select_retrieval_context_filters_by_threshold_and_caps_results():
    from query.retrieval_selection import select_retrieval_context

    docs = [f"chunk {i}" for i in range(6)]
    metas = [{"chunk_id": f"c{i}"} for i in range(6)]
    scores = [0.91, 0.72, 0.61, 0.59, 0.51, 0.44]

    selected, trace = select_retrieval_context(
        docs,
        metas,
        scores,
        score_threshold=0.60,
        min_chunks=2,
        max_chunks=3,
    )

    assert [meta["chunk_id"] for _doc, meta, _score in selected] == ["c0", "c1", "c2"]
    assert trace["raw_retrieved_count"] == 6
    assert trace["passed_threshold_count"] == 3
    assert trace["final_context_count"] == 3
    assert trace["fallback_used"] is False
    assert trace["filtered_out_count"] == 3


def test_select_retrieval_context_falls_back_to_top_raw_when_threshold_is_too_strict():
    from query.retrieval_selection import select_retrieval_context

    docs = ["best", "second", "third"]
    metas = [{"chunk_id": "best"}, {"chunk_id": "second"}, {"chunk_id": "third"}]
    scores = [0.57, 0.52, 0.48]

    selected, trace = select_retrieval_context(
        docs,
        metas,
        scores,
        score_threshold=0.80,
        min_chunks=2,
        max_chunks=8,
    )

    assert [meta["chunk_id"] for _doc, meta, _score in selected] == ["best", "second"]
    assert trace["passed_threshold_count"] == 0
    assert trace["final_context_count"] == 2
    assert trace["fallback_used"] is True
    assert trace["selected_sources"][0]["selection_reason"] == "fallback_top_raw"
