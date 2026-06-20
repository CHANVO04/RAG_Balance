"""
kg_neo4j_traversal.py — Layer 3: query-time KG context retrieval via BFS.
Split from kg_neo4j.py (God Module refactor). kg_neo4j.py remains as backward-compat facade.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

from kg_neo4j_config import (
    KG_LLM_PROVIDER, KG_MAX_TRIPLETS,
    BFS_CONTEXT_CYPHER, GET_ALL_ENTITY_IDS_CYPHER,
)
from kg_neo4j_extractor import _call_llm, _normalize_entity
from kg_neo4j_manager import get_neo4j_manager


# ══════════════════════════════════════════════════════════════════════════════
# ENTITY EXTRACTION FROM QUERY
# ══════════════════════════════════════════════════════════════════════════════

_ENTITY_EXTRACT_PROMPT = """\
List key entities from this question for knowledge graph lookup.
Return ONLY a JSON object with key "entities" containing an array of strings, max 6 items.
Normalize: uppercase abbreviations, title-case proper nouns.

Question: {question}

Format: {{"entities": ["entity1", "entity2"]}}

JSON object only:"""


def _parse_entity_list_response(raw: str) -> List[str]:
    """Parse {"entities": [...]} or fallback plain array."""
    import json
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if isinstance(data, dict) and "entities" in data:
        result = data["entities"]
        return result if isinstance(result, list) else []
    if isinstance(data, list):
        return data
    return []


def _safe_graph_id_part(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "").strip())
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^A-Za-z0-9_.:-]", "", value)
    return value or "unknown"


def _graph_edge_id(from_id: str, relation: str, to_id: str) -> str:
    """Match graph visualization edge ids so KG citations can focus edges."""
    return "::".join([
        _safe_graph_id_part(from_id),
        "edge",
        _safe_graph_id_part(relation),
        _safe_graph_id_part(to_id),
    ])


def _extract_query_entities_llm(question: str) -> List[str]:
    prompt = _ENTITY_EXTRACT_PROMPT.format(question=question)
    try:
        raw      = _call_llm(prompt, max_tokens=150)
        entities = _parse_entity_list_response(raw)
        result: List[str] = []
        for e in entities:
            if isinstance(e, str) and e.strip():
                result.append(_normalize_entity(e.strip()))
        return result[:6]
    except Exception:
        return []


def _extract_query_entities_keywords(question: str, entities: List[Dict[str, str]]) -> List[str]:
    STOP = {
        "THE", "IS", "ARE", "WAS", "WHAT", "HOW", "DOES", "DID", "WILL",
        "AND", "FOR", "WITH", "FROM", "THIS", "THAT", "HAVE", "HAS",
        "NOT", "CAN", "ABOUT", "WHICH", "WHO", "WHERE", "WHEN", "WHY",
    }
    question_upper = question.upper()
    matched: List[str] = []

    for entity in entities:
        node_id = str(entity.get("id", ""))
        label = str(entity.get("label", ""))
        label_up = label.upper()
        node_up = node_id.upper()
        if len(label_up) >= 3 and label_up not in STOP and label_up in question_upper:
            matched.append(node_id)
        elif len(node_up) >= 3 and node_up not in STOP and node_up in question_upper:
            matched.append(node_id)

    if not matched:
        q_words = {w.upper() for w in re.findall(r"[A-Za-z0-9]{4,}", question)
                   if w.upper() not in STOP}
        for entity in entities:
            node_id = str(entity.get("id", ""))
            label = str(entity.get("label", ""))
            node_words = set(re.findall(r"[A-Za-z0-9]+", f"{node_id} {label}".upper()))
            if q_words & node_words:
                matched.append(node_id)

    return matched[:8]


def _normalize_selected_files(selected_files: Optional[List[str]]) -> Optional[List[str]]:
    if not selected_files:
        return None

    normalized = [str(source).strip() for source in selected_files if str(source).strip()]
    return normalized or None


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _choose_citation_provenance(
    row: Dict[str, Any],
    selected_files: Optional[List[str]],
) -> Dict[str, Any]:
    source_files = [str(source) for source in row.get("source_files") or [] if str(source)]
    source_file = ""

    if selected_files:
        selected_set = set(selected_files)
        for candidate in source_files:
            if candidate in selected_set:
                source_file = candidate
                break
    elif source_files:
        source_file = source_files[0]

    # Relationship metadata stores unique arrays, not per-source records. On
    # multi-source edges we can focus the graph edge/source, but cannot safely
    # infer which page/chunk belongs to that source.
    if len(source_files) != 1:
        return {
            "source_file": source_file,
            "page": 0,
            "chunk_id": "",
            "evidence_preview": "",
            "has_document_evidence": False,
        }

    pages = row.get("pages") or []
    chunk_ids = row.get("chunk_ids") or []
    page = _positive_int(pages[0] if pages else 0)
    has_document_evidence = bool(source_file and page > 0)
    chunk_id = str(chunk_ids[0] or "") if chunk_ids and has_document_evidence else ""
    evidence_preview = str(row.get("evidence_preview", "") or "") if has_document_evidence else ""

    return {
        "source_file": source_file,
        "page": page,
        "chunk_id": chunk_id,
        "evidence_preview": evidence_preview,
        "has_document_evidence": has_document_evidence,
    }


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — QUERY-TIME BFS TRAVERSAL
# ══════════════════════════════════════════════════════════════════════════════

def lookup_kg_context(
    question: str,
    use_llm_entity_extract: bool = True,
    max_hops: int = 2,
    max_triplets: int = 20,
    verbose: bool = True,
    workspace_id: str = "default",
    selected_files: Optional[List[str]] = None,
) -> Tuple[str, List[Dict]]:
    """
    Neo4j-native KG context lookup.

    Flow:
      question
        → extract entities (LLM or keyword matching)
        → find seed Entity nodes in Neo4j
        → Cypher BFS 1-2 hops
        → format triplets as context text

    Returns empty context/sources when no seed entities match the question,
    avoiding injection of unrelated top-degree graph content.
    """
    manager = get_neo4j_manager()
    workspace_id = workspace_id or "default"
    selected_files = _normalize_selected_files(selected_files)

    try:
        with manager.session() as session:
            count_result = session.run(
                "MATCH (n:Entity {workspace_id: $workspace_id}) RETURN count(n) AS cnt",
                workspace_id=workspace_id,
            )
            node_count = count_result.single()["cnt"]
            if node_count == 0:
                if verbose:
                    print("[KG] Graph rỗng — chưa có Entity nodes")
                return "", []

            all_ids_result = session.run(
                GET_ALL_ENTITY_IDS_CYPHER,
                workspace_id=workspace_id,
            )
            entities = [
                {"id": r["id"], "label": r["label"] or ""}
                for r in all_ids_result
            ]
            all_node_ids = [entity["id"] for entity in entities]
            labels_by_id = {entity["id"]: entity["label"] for entity in entities}

    except Exception as e:
        if verbose:
            print(f"[KG][WARN] Không kết nối được Neo4j: {e}")
        raise

    # ── STEP 1: Extract entities from query ──────────────────────────────────
    seed_ids: List[str] = []

    if use_llm_entity_extract and KG_LLM_PROVIDER == "openai":
        llm_entities = _extract_query_entities_llm(question)
        if verbose and llm_entities:
            print(f"[KG] LLM extracted entities: {llm_entities}")
        for entity in llm_entities:
            entity_up = entity.upper()
            if entity in all_node_ids:
                seed_ids.append(entity)
            else:
                for nid in all_node_ids:
                    if str(nid).upper() == entity_up or labels_by_id.get(nid, "").upper() == entity_up:
                        seed_ids.append(nid)
                        break

    # Keyword fallback / supplement
    kw_seeds = _extract_query_entities_keywords(question, entities)
    for s in kw_seeds:
        if s not in seed_ids:
            seed_ids.append(s)

    # If neither LLM nor keyword matching found any seed entity, skip KG context.
    # The previous top-degree fallback injected potentially irrelevant triplets as
    # highest-priority context, causing LLM position-bias on unrelated content.
    if not seed_ids:
        if verbose:
            print("[KG] Không tìm thấy seed entity phù hợp — bỏ qua KG context để tránh nhiễu")
        return "", []

    # ── STEP 2: Cypher BFS ───────────────────────────────────────────────────
    try:
        with manager.session() as session:
            result = session.run(
                BFS_CONTEXT_CYPHER,
                seed_ids=seed_ids,
                workspace_id=workspace_id,
                selected_files=selected_files,
                max_triplets=max_triplets,
            )
            rows = [
                {
                    "from_id":    r["from_id"],
                    "from_label": r["from_label"],
                    "relation":   r["relation"],
                    "weight":     r["weight"],
                    "to_id":      r["to_id"],
                    "to_label":   r["to_label"],
                    "source_files": r["source_files"],
                    "pages": r["pages"],
                    "chunk_ids": r["chunk_ids"],
                    "evidence_preview": r["evidence_preview"],
                }
                for r in result
            ]
    except Exception as e:
        if verbose:
            print(f"[KG][ERR] BFS query failed: {e}")
        raise

    if not rows:
        if verbose:
            print("[KG] BFS returned 0 triplets")
        return "", []

    # ── STEP 3: Format context ───────────────────────────────────────────────
    seed_set = set(seed_ids)
    lines_seed:   List[Tuple[float, str]] = []
    lines_expand: List[Tuple[float, str]] = []
    seen: Set[Tuple] = set()
    kg_sources: List[Dict] = []

    for idx, row in enumerate(rows, start=1):
        provenance = _choose_citation_provenance(row, selected_files)
        kg_sources.append({
            "id": f"KG-{idx:02d}",
            "subject": row["from_label"],
            "relation": row["relation"],
            "object": row["to_label"],
            "subject_id": row["from_id"],
            "object_id": row["to_id"],
            "edge_id": _graph_edge_id(row["from_id"], row["relation"], row["to_id"]),
            "source_file": provenance["source_file"],
            "page": provenance["page"],
            "chunk_id": provenance["chunk_id"],
            "weight": float(row["weight"] or 1),
            "evidence_preview": provenance["evidence_preview"],
            "has_document_evidence": provenance["has_document_evidence"],
        })

    for row, source in zip(rows, kg_sources):
        key = (row["from_id"], row["relation"], row["to_id"])
        if key in seen:
            continue
        seen.add(key)
        weight = float(row["weight"] or 1)
        line = (
            f"  • [{source['id']}] "
            f"{row['from_label']} —[{row['relation']}]→ {row['to_label']}"
        )
        if row["from_id"] in seed_set or row["to_id"] in seed_set:
            lines_seed.append((weight, line))
        else:
            lines_expand.append((weight, line))

    lines_seed.sort(key=lambda x: x[0], reverse=True)
    lines_expand.sort(key=lambda x: x[0], reverse=True)

    all_lines = [line for _, line in lines_seed + lines_expand][:max_triplets]

    if not all_lines:
        return "", []

    degree_count: Dict[str, int] = {}
    for row in rows:
        degree_count[row["from_id"]] = degree_count.get(row["from_id"], 0) + 1
        degree_count[row["to_id"]]   = degree_count.get(row["to_id"],   0) + 1

    key_entities = sorted(
        [(nid, degree_count.get(nid, 0)) for nid in seed_ids if nid in degree_count],
        key=lambda x: x[1], reverse=True,
    )[:4]

    header = ""
    if key_entities:
        entity_str = ", ".join(f"{n} (degree={d})" for n, d in key_entities)
        header = f"Key entities: {entity_str}\n"

    if verbose:
        print(
            f"[KG] {len(seed_ids)} seed nodes → "
            f"{len(rows)} BFS triplets → "
            f"context={'có' if all_lines else 'rỗng'}"
        )

    return (
        "## Knowledge Graph — Entities & Relationships\n"
        + header
        + "\n".join(all_lines)
    ), kg_sources
