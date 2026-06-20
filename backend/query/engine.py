import time
import json
import secrets
from typing import Any, Dict, List, Optional, Tuple

from query.config import DEFAULT_RETRIEVE_K, DEFAULT_TOP_N
from query.cache import check_semantic_cache, add_to_cache
from query.kg_retriever import KGSearchResult, retrieve_kg
from query.vector_retriever import retrieve_vectors
from query.retrieval_selection import select_retrieval_context
from query.prompt_builder import build_prompt
from query.generator import generate_answer
from query.visuals import (
    retrieve_full_visual_context,
    should_fetch_full_visual_context,
    should_skip_kg_for_visual_question,
)
from query.document_inventory import (
    build_document_inventory_context,
    should_include_document_inventory,
)


_MEDIA_PREFIX = {
    "image": "IMG",
    "formula": "FORM",
    "table": "TBL",
}


def _loads_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str) or not value.strip():
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _short_id(seed: str, used: set[str]) -> str:
    """Create a unique random 4-char id for one answer source."""
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    for _ in range(200):
        token = "".join(secrets.choice(alphabet) for _ in range(4))
        if token not in used:
            used.add(token)
            return token
    token = seed.replace(":", "")[-4:].lower().ljust(4, "0")[:4]
    while token in used:
        token = "".join(secrets.choice(alphabet) for _ in range(4))
    used.add(token)
    return token


def _visual_kind(visual: Dict[str, Any]) -> str:
    kind = str(visual.get("type", "")).lower().strip()
    if kind in _MEDIA_PREFIX:
        return kind
    visual_id = str(visual.get("id", "")).lower()
    if visual_id.startswith("img"):
        return "image"
    if visual_id.startswith("formula"):
        return "formula"
    if visual_id.startswith("table"):
        return "table"
    return "image"


def _source_base(
    source_id: int,
    meta: Dict[str, Any],
    score: float,
    ref_id: str,
    kind: str = "text",
    visual_id: str = "",
    asset_path: str = "",
    content: str = "",
) -> Dict[str, Any]:
    return {
        "id": source_id,
        "citation_id": ref_id,
        "ref_id": ref_id,
        "kind": kind,
        "visual_id": visual_id,
        "asset_path": asset_path,
        "content": content,
        "file_name": meta.get("file_name", ""),
        "page": int(meta.get("page", 0) or 0),
        "score": float(score),
        "section_label": meta.get("section_label", ""),
        "has_table": kind == "table" or bool(meta.get("has_table", False)),
        "has_formula": kind == "formula" or bool(meta.get("has_formula", False)),
        "has_image": kind == "image" or bool(meta.get("has_image", False)),
        "table_refs": meta.get("table_refs", "[]"),
        "image_refs": meta.get("image_refs", "[]"),
        "formula_refs": meta.get("formula_refs", "[]"),
        "visual_assets": meta.get("visual_assets", "[]"),
    }


def _attach_citation_ids(ranked_results: List[Tuple[str, Dict, float]]) -> List[Dict[str, Any]]:
    """Attach NexusRAG-style text and media citation ids after retrieval."""
    used_tokens: set[str] = set()
    sources: List[Dict[str, Any]] = []

    for index, (doc, meta, score) in enumerate(ranked_results):
        source_id = index + 1
        seed = f"{meta.get('chunk_id', '')}:{meta.get('file_name', '')}:{meta.get('page', '')}:{source_id}"
        text_ref = _short_id(seed, used_tokens)
        meta["citation_id"] = text_ref
        media_refs: List[str] = []
        sources.append(_source_base(source_id, meta, score, text_ref, content=doc))

        visual_refs = _loads_json(meta.get("visual_refs", "[]"), [])
        if not isinstance(visual_refs, list):
            visual_refs = []
        for visual in visual_refs:
            if not isinstance(visual, dict):
                continue
            visual_id = str(visual.get("id", "")).strip()
            if not visual_id:
                continue
            kind = _visual_kind(visual)
            prefix = _MEDIA_PREFIX[kind]
            token = _short_id(f"{seed}:{kind}:{visual_id}", used_tokens)
            ref_id = f"{prefix}-{token}"
            media_refs.append(ref_id)
            media_meta = dict(meta)
            media_meta["page"] = visual.get("page") or meta.get("page", 0)
            media_meta["section_label"] = f"visual:{kind}"
            sources.append(_source_base(
                source_id=source_id,
                meta=media_meta,
                score=score,
                ref_id=ref_id,
                kind=kind,
                visual_id=visual_id,
                asset_path=str(visual.get("path", "") or ""),
                content=doc,
            ))

        meta["media_citation_refs"] = media_refs

    return sources


def _build_retrieval_trace(
    *,
    question: str,
    workspace_id: str,
    selected_files: Optional[List],
    retrieve_k: int,
    top_n: int,
    kg_mode: str,
    use_rerank: bool,
    use_visuals: bool,
    raw_count: int,
    ranked_results: List[Tuple[str, Dict, float]],
    sources_structured: List[Dict[str, Any]],
    kg_context: str,
    image_context: str,
    document_inventory_context: str,
    kg_sources: List[Dict[str, Any]],
    kg_unavailable_reason: str,
    kg_trace: Dict[str, Any],
    selection_trace: Dict[str, Any],
) -> Dict[str, Any]:
    """Build compact JSON for low-cost manual retrieval debugging."""
    sources = []
    selection_reasons = {
        str(source.get("chunk_id")): source.get("selection_reason", "")
        for source in selection_trace.get("selected_sources", [])
        if source.get("chunk_id")
    }
    text_sources = {
        int(source.get("id", 0)): source
        for source in sources_structured
        if source.get("kind", "text") == "text"
    }
    for rank, (doc, meta, score) in enumerate(ranked_results, start=1):
        source = text_sources.get(rank, {})
        sources.append({
            "rank": rank,
            "citation_id": source.get("citation_id", ""),
            "file_name": meta.get("file_name", ""),
            "page": meta.get("page", 0),
            "score": float(score or 0.0),
            "chunk_id": meta.get("chunk_id", ""),
            "section_label": meta.get("section_label", ""),
            "content_type": meta.get("content_type", "text"),
            "has_table": bool(meta.get("has_table")),
            "has_formula": bool(meta.get("has_formula")),
            "has_image": bool(meta.get("has_image")),
            "visual_refs": _loads_json(meta.get("visual_refs", "[]"), []),
            "media_citation_refs": meta.get("media_citation_refs", []),
            "selection_reason": selection_reasons.get(str(meta.get("chunk_id")), "selected"),
            "preview": (doc or "")[:240],
        })

    return {
        "question": question,
        "workspace_id": workspace_id,
        "selected_files": selected_files or [],
        "settings": {
            "retrieve_k": retrieve_k,
            "top_n": top_n,
            "kg_mode": kg_mode,
            "use_rerank": False,
            "use_visuals": use_visuals,
            "qdrant_limit": retrieve_k,
            "score_threshold": selection_trace.get("score_threshold", 0.0),
            "min_chunks": selection_trace.get("min_chunks", 2),
            "max_chunks": selection_trace.get("max_chunks", 8),
        },
        "counts": {
            "raw_docs": raw_count,
            "ranked_docs": len(ranked_results),
            "passed_threshold": int(selection_trace.get("passed_threshold_count", 0) or 0),
            "final_context": int(selection_trace.get("final_context_count", len(ranked_results)) or 0),
            "filtered_out": int(selection_trace.get("filtered_out_count", 0) or 0),
            "sources": len(sources_structured),
            "kg_sources": len(kg_sources),
            "graph_relationships_traversed": int(kg_trace.get("graph_relationships_traversed", 0) or 0),
            "graph_relationships_used_in_prompt": int(kg_trace.get("graph_relationships_used_in_prompt", 0) or 0),
        },
        "context_used": {
            "kg": bool(kg_context),
            "visual": bool(image_context),
            "document_inventory": bool(document_inventory_context),
        },
        "kg_sources": kg_sources,
        "kg_unavailable_reason": kg_unavailable_reason,
        "kg_trace": kg_trace,
        "selection": selection_trace,
        "sources": sources,
    }


def _coerce_kg_search_result(result: Any) -> KGSearchResult:
    if isinstance(result, KGSearchResult):
        return result
    if isinstance(result, tuple):
        context, sources = result
        return KGSearchResult(context=context or "", sources=sources or [])
    return KGSearchResult(context=result or "")


def rag_prepare(
    question: str,
    retrieve_k: int = DEFAULT_RETRIEVE_K,
    top_n: int = DEFAULT_TOP_N,
    use_rerank: bool = True,
    use_cache: bool = True,
    kg_mode: str = "default",
    selected_files: Optional[List] = None,
    workspace_id: str = "default",
    use_visuals: bool = True,
    score_threshold: float = 0.58,
    custom_system_instruction: str | None = None,
    user_prompt_template: str | None = None,
) -> Dict[str, Any]:
    """
    Retrieval phase: cache → vector → threshold/fallback/cap → citations → anchored KG → augment → prompt.
    Does NOT call LLM. Used by both rag_query() and the FastAPI SSE endpoint.

    Return dict keys:
      cache_hit=True  → {"cache_hit": True, "cached_answer": str, "kg_context": ""}
      error           → {"cache_hit": False, "error": str, "kg_context": str}
      success         → {"cache_hit": False, "system_prompt": str, "user_prompt": str,
                          "sources_info": List[str],        # legacy string format
                          "sources_structured": List[dict], # structured for FastAPI
                          "kg_context": str, "formula_context": str,
                          "use_cache": bool, "question": str}
    """
    # 1. Semantic Cache
    if use_cache:
        cached_ans = check_semantic_cache(question, workspace_id=workspace_id, file_names=selected_files)
        if cached_ans:
            return {"cache_hit": True, "cached_answer": cached_ans,
                    "kg_context": "", "kg_sources": [], "formula_context": ""}

    kg_context = ""
    kg_sources: List[Dict[str, Any]] = []
    kg_unavailable_reason = ""
    kg_trace: Dict[str, Any] = {}

    # 2. Vector Search
    try:
        raw_docs, raw_metas, distances, q_emb = retrieve_vectors(
            question, retrieve_k, selected_files, workspace_id=workspace_id
        )
    except Exception as e:
        err_msg = str(e)
        print(f"[ERROR] Vector search: {err_msg}")
        return {"cache_hit": False, "error": err_msg,
                "kg_context": "", "kg_sources": [],
                "kg_unavailable_reason": "", "formula_context": ""}

    if not raw_docs:
        return {
            "cache_hit": False,
            "error": "Không tìm thấy tài liệu nào trong cơ sở dữ liệu.",
            "kg_context": "", "kg_sources": [],
            "kg_unavailable_reason": "", "formula_context": "",
        }

    # 3. Select final context directly from Qdrant similarity scores. The previous
    # reranker path was removed from online querying to keep responses fast.
    ranked_results, selection_trace = select_retrieval_context(
        raw_docs,
        raw_metas,
        distances,
        score_threshold=score_threshold,
        min_chunks=2,
        max_chunks=top_n,
    )

    # 4. Attach citations before anchored KG so graph evidence can point back
    # to the same text chunk ids used in the final answer.
    sources_structured = _attach_citation_ids(ranked_results)
    chunk_ids = [
        str(meta.get("chunk_id"))
        for _doc, meta, _score in ranked_results
        if meta.get("chunk_id")
    ]
    chunk_citations = {
        str(meta.get("chunk_id")): str(meta.get("citation_id"))
        for _doc, meta, _score in ranked_results
        if meta.get("chunk_id") and meta.get("citation_id")
    }
    visual_intent = use_visuals and should_fetch_full_visual_context(question, ranked_results)

    # 5. Knowledge Graph anchored by ranked vector chunks.
    if should_skip_kg_for_visual_question(question, ranked_results):
        kg_result = KGSearchResult(
            unavailable_reason="visual_question_prefers_visual_context",
            trace={"kg_mode": kg_mode, "reason": "visual_question_prefers_visual_context"},
        )
    else:
        kg_result = _coerce_kg_search_result(retrieve_kg(
            question,
            kg_mode=kg_mode,
            workspace_id=workspace_id,
            selected_files=selected_files,
            chunk_ids=chunk_ids,
            visual_intent=visual_intent,
            chunk_citations=chunk_citations,
        ))
    kg_context = kg_result.context
    kg_sources = kg_result.sources
    kg_unavailable_reason = kg_result.unavailable_reason
    kg_trace = kg_result.trace

    # 6. Compact visual summaries are embedded inline. Fetch full analyses only
    # when the question explicitly needs detailed visual/table/formula evidence.
    table_context   = ""
    formula_context = ""
    image_context = ""
    if use_visuals:
        image_context = retrieve_full_visual_context(
            question,
            ranked_results,
            workspace_id=workspace_id,
        )
    document_inventory_context = ""
    if should_include_document_inventory(question):
        document_inventory_context = build_document_inventory_context(workspace_id)

    retrieval_trace = _build_retrieval_trace(
        question=question,
        workspace_id=workspace_id,
        selected_files=selected_files,
        retrieve_k=retrieve_k,
        top_n=top_n,
        kg_mode=kg_mode,
        use_rerank=use_rerank,
        use_visuals=use_visuals,
        raw_count=len(raw_docs),
        ranked_results=ranked_results,
        sources_structured=sources_structured,
        kg_context=kg_context,
        image_context=image_context,
        document_inventory_context=document_inventory_context,
        kg_sources=kg_sources,
        kg_unavailable_reason=kg_unavailable_reason,
        kg_trace=kg_trace,
        selection_trace=selection_trace,
    )

    # 7. Build Prompt
    system_prompt, user_prompt, sources_info = build_prompt(
        question=question,
        kg_context=kg_context,
        formula_context=formula_context,
        table_context=table_context,
        image_context=image_context,
        ranked_results=ranked_results,
        document_inventory_context=document_inventory_context,
        kg_sources=kg_sources,
        custom_system_instruction=custom_system_instruction,
        user_prompt_template=user_prompt_template,
    )
    retrieval_trace["prompt"] = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "custom_system_instruction": custom_system_instruction or "",
        "user_prompt_template": user_prompt_template or "",
    }

    return {
        "cache_hit":          False,
        "system_prompt":      system_prompt,
        "user_prompt":        user_prompt,
        "sources_info":       sources_info,
        "sources_structured": sources_structured,
        "kg_context":         kg_context,
        "kg_sources":         kg_sources,
        "kg_unavailable_reason": kg_unavailable_reason,
        "formula_context":    formula_context,
        "retrieval_trace":    retrieval_trace,
        "use_cache":          use_cache,
        "question":           question,
    }


def rag_query(
    question: str,
    retrieve_k: int = DEFAULT_RETRIEVE_K,
    top_n: int = DEFAULT_TOP_N,
    use_rerank: bool = True,
    use_cache: bool = True,
    kg_mode: str = "default",
    selected_files: Optional[List] = None,
    workspace_id: str = "default",
    use_visuals: bool = True,
) -> Dict[str, Any]:

    t_start = time.time()
    print("\n" + "="*60)
    print(f"[QUERY] QUESTION: {question}")
    print("="*60)

    prep = rag_prepare(
        question,
        retrieve_k,
        top_n,
        use_rerank,
        use_cache,
        kg_mode,
        selected_files,
        workspace_id,
        use_visuals,
    )

    if prep.get("cache_hit"):
        print(f"[TIME] Cache hit trong {time.time() - t_start:.2f}s")
        return {"answer": prep["cached_answer"], "sources": [], "kg_context": "", "kg_sources": []}

    if prep.get("error"):
        return {
            "answer": prep["error"],
            "sources": [],
            "kg_context": prep.get("kg_context", ""),
            "kg_sources": prep.get("kg_sources", []),
        }

    # 7. LLM Generation
    try:
        answer = generate_answer(prep["system_prompt"], prep["user_prompt"])

        if use_cache:
            add_to_cache(question, answer, workspace_id=workspace_id, file_names=selected_files)

        print("\n" + "="*60)
        print("[QUERY] ANSWER:\n")
        print(answer)
        print("\n" + "="*60)
        print("[QUERY] SOURCES:")
        for s in prep["sources_info"]:
            print(s)
        print(f"[TIME] Total: {time.time() - t_start:.2f}s")
        print("="*60)

        return {
            "answer":          answer,
            "sources":         prep["sources_info"],
            "kg_context":      prep["kg_context"],
            "kg_sources":      prep.get("kg_sources", []),
            "formula_context": prep["formula_context"],
            "retrieval_trace": prep.get("retrieval_trace", {}),
        }
    except Exception as e:
        err_msg = f"Lỗi gọi LLM: {e}"
        print(f"[ERROR] {err_msg}")
        return {"answer": err_msg, "sources": []}
