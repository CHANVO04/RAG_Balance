"""
kg_neo4j_extractor.py — Layer 1 (LLM extraction) + Layer 2 (entity normalization) + upsert.
Split from kg_neo4j.py (God Module refactor). kg_neo4j.py remains as backward-compat facade.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from types import SimpleNamespace
from typing import Any, Dict, List

from kg_neo4j_config import (
    KG_LLM_PROVIDER, KG_LLM_MODEL, KG_OLLAMA_BASE_URL,
    KG_MAX_TRIPLETS, KG_ENABLED, KG_CALL_DELAY_SEC,
)
from kg_neo4j_manager import KGTriplet, get_neo4j_manager, usage_tracker
from kg_scientific_schema import (
    canonical_entity_key,
    normalize_entity_label,
    normalize_entity_type,
    normalize_relation_name,
)


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — LLM EXTRACTION PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

_SCIENTIFIC_GRAPH_PROMPT = """\
You extract a compact scientific knowledge graph from research text.
Context: document="{title}", section="{section}"

Return JSON only:
{{
  "triplets": [
    {{
      "subject": "CNN Model",
      "subject_type": "Model",
      "relation": "RUNS_ON",
      "object": "K210 KPU",
      "object_type": "Hardware",
      "evidence": "short evidence phrase from the chunk",
      "chunk_id": "chunk id provided by the system",
      "confidence": 0.86,
      "visual_ids": []
    }}
  ]
}}

Allowed node types:
Method, Model, Dataset, Metric, Result, Hardware, Signal, Parameter, Formula,
Table, Figure, Problem, Limitation, Contribution, Concept.

Relation rules:
- Use short active UPPER_SNAKE_CASE verb phrases.
- Prefer specific relations such as TRAINED_ON, EVALUATED_ON, OUTPERFORMS,
  IMPROVES, REDUCES, INCREASES, MITIGATES, PREDICTS, MEASURES,
  TRANSFORMS_INTO, RUNS_ON, REPORTS, DEFINES, ILLUSTRATES, CAUSES,
  DEPENDS_ON, ENABLES, LIMITED_BY.
- Never output RELATED_TO, ASSOCIATED_WITH, CONNECTED_TO, IS_A, HAS,
  MENTIONS, INVOLVES, or USES.
- Direction must be subject -> action -> object.
- Include only claims supported by this chunk.
- Skip claims without evidence.
- Max {max_triplets} most informative triplets.
- Include chunk_id exactly as provided for each claim.

Text:
\"\"\"{text}\"\"\"

JSON object only, no explanation:"""


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — JSON PARSERS
# ══════════════════════════════════════════════════════════════════════════════

def _parse_triplets_response(raw: str) -> List[Dict]:
    """Parse JSON from LLM; handles {"triplets":[...]} or fallback plain array."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
            data = json.loads(cleaned)
        except Exception as e:
            print(f"[KG][ERR] JSON parsing failed: {e}")
            if len(raw) > 100:
                print(f"[KG][DEBUG] Raw start: {raw[:100]}...")
                print(f"[KG][DEBUG] Raw end: ...{raw[-100:]}")
            else:
                print(f"[KG][DEBUG] Raw: {raw}")
            return []

    if isinstance(data, dict) and "triplets" in data:
        result = data["triplets"]
        return result if isinstance(result, list) else []
    if isinstance(data, list):
        return data
    return []


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — LLM CALLERS
# ══════════════════════════════════════════════════════════════════════════════

def _call_openai(prompt: str, model: str, max_tokens: int = 512) -> str:
    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("[KG] Missing OPENAI_API_KEY in .env")
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.05,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        usage_tracker.add(resp.usage)
        finish = resp.choices[0].finish_reason
        if finish == "length":
            print("[KG][WARN] OpenAI output truncated (finish_reason=length)")
        return resp.choices[0].message.content.strip()
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"[KG] OpenAI failed: {e}")


def _call_ollama(prompt: str, model: str, max_tokens: int = 512) -> str:
    try:
        import requests
        payload = {
            "model":  model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.05, "num_predict": max_tokens},
        }
        resp = requests.post(
            f"{KG_OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        print(f"[KG][ERR] Ollama call failed: {e}")
        return "{}"


def _call_llm(prompt: str, max_tokens: int = 512) -> str:
    if KG_LLM_PROVIDER == "openai":
        return _call_openai(prompt, KG_LLM_MODEL, max_tokens)
    elif KG_LLM_PROVIDER == "ollama":
        return _call_ollama(prompt, KG_LLM_MODEL, max_tokens)
    else:
        raise ValueError(f"[KG] Unknown provider: '{KG_LLM_PROVIDER}'")


def _truncate_to_sentence_boundary(text: str, max_chars: int = 2000) -> str:
    if len(text) <= max_chars:
        return text
    search_start = max(0, max_chars - 200)
    window = text[search_start:max_chars]
    last_sentence_end = -1
    for i, ch in enumerate(window):
        if ch in ".!?":
            last_sentence_end = i
    if last_sentence_end >= 0:
        return text[:search_start + last_sentence_end + 1].strip()
    last_space = text.rfind(" ", 0, max_chars)
    if last_space > 0:
        return text[:last_space].strip()
    return text[:max_chars]


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — ENTITY NORMALIZATION
# ══════════════════════════════════════════════════════════════════════════════

_KEEP_SUFFIX_S = {
    "corpus", "status", "focus", "nexus", "bonus", "campus",
    "bias", "thesis", "basis", "axis", "analysis", "synthesis",
    "process", "access", "address", "lass", "class",
}


def _normalize_entity(name: str) -> str:
    name = unicodedata.normalize("NFKC", name.strip())
    name = re.sub(r"^[^a-zA-Z0-9À-ɏ]+|[^a-zA-Z0-9À-ɏ]+$", "", name)
    name = re.sub(r"\s+", " ", name)
    if not name:
        return ""

    if (name.lower() not in _KEEP_SUFFIX_S
            and name.lower().endswith("ies")
            and len(name) > 5
            and not name.isupper()):
        candidate = name[:-3] + "y"
        if candidate.istitle() or candidate[0].isupper():
            name = candidate
        elif name[0].islower():
            name = name[:-3] + "y"
    elif (name.lower() not in _KEEP_SUFFIX_S
            and name.endswith("s")
            and len(name) > 4
            and not name.isupper()):
        singular = name[:-1]
        if singular.istitle() or singular.isupper():
            name = singular

    if len(name) <= 5 and re.match(r"^[A-Za-z]+$", name):
        name = name.upper()
    else:
        name = name.title()

    return name


def _normalize_relation(rel: str) -> str:
    return re.sub(r"\s+", " ", rel.strip().lower())


def _safe_graph_id_part(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "").strip())
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^A-Za-z0-9_.:-]", "", value)
    return value or "unknown"


def _entity_node_id(workspace_id: str, label: str) -> str:
    return f"{_safe_graph_id_part(workspace_id)}::entity::{_safe_graph_id_part(label.lower())}"


def _document_node_id(workspace_id: str, file_name: str) -> str:
    return f"{_safe_graph_id_part(workspace_id)}::document::{_safe_graph_id_part(file_name)}"


def _chunk_source_file(chunk: Any) -> str:
    return str(getattr(chunk, "file_name", "") or getattr(chunk, "source_file", "") or "")


def _as_visual_ids(value: Any) -> List[str]:
    if not value:
        return []
    if not isinstance(value, list):
        value = [value]
    return [str(item) for item in value if item]


def _as_confidence(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _build_triplet(
    item: Dict[str, Any],
    chunk: Any,
    force_chunk_id: bool = False,
) -> KGTriplet | None:
    subject = normalize_entity_label(item.get("subject"))
    obj = normalize_entity_label(item.get("object"))
    relation = normalize_relation_name(item.get("relation"))
    evidence = normalize_entity_label(item.get("evidence"))

    if not subject or not obj or not relation or not evidence:
        return None
    if len(subject) < 2 or len(obj) < 2:
        return None
    if len(subject) > 150 or len(obj) > 150:
        return None
    if subject == obj:
        return None

    return KGTriplet(
        subject=subject,
        relation=relation,
        object=obj,
        source=_chunk_source_file(chunk),
        page=getattr(chunk, "page", None),
        chunk_id=str(getattr(chunk, "chunk_id", "") if force_chunk_id else item.get("chunk_id") or getattr(chunk, "chunk_id", "") or ""),
        workspace_id=str(getattr(chunk, "workspace_id", "default") or "default"),
        subject_type=normalize_entity_type(item.get("subject_type")),
        object_type=normalize_entity_type(item.get("object_type")),
        subject_key=canonical_entity_key(subject),
        object_key=canonical_entity_key(obj),
        evidence_preview=evidence[:240],
        confidence=_as_confidence(item.get("confidence")),
        visual_ids=_as_visual_ids(item.get("visual_ids")),
    )


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — INGEST SIDE
# ══════════════════════════════════════════════════════════════════════════════

def extract_triplets_llm(chunk: Any) -> List[KGTriplet]:
    """Per-chunk LLM extraction."""
    if not KG_ENABLED:
        return []

    text = getattr(chunk, "text", "")
    if len(text.strip()) < 150:
        return []

    stripped = text.strip()
    if stripped.startswith("|") and stripped.count("\n") > stripped.count(" ") / 3:
        return []

    text_for_llm = _truncate_to_sentence_boundary(text, max_chars=2000)
    section = getattr(chunk, "section_label", "general") or "general"
    title   = getattr(chunk, "title", "") or ""

    prompt = _SCIENTIFIC_GRAPH_PROMPT.format(
        text=text_for_llm,
        max_triplets=KG_MAX_TRIPLETS,
        section=section,
        title=title,
    )

    if KG_CALL_DELAY_SEC > 0:
        time.sleep(KG_CALL_DELAY_SEC)

    raw      = _call_llm(prompt, max_tokens=512)
    raw_list = _parse_triplets_response(raw)

    triplets: List[KGTriplet] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        triplet = _build_triplet(item, chunk, force_chunk_id=True)
        if triplet is None:
            continue
        triplets.append(triplet)

    print(f"[KG] Chunk '{getattr(chunk, 'chunk_id', '')[:8]}...' → {len(triplets)} triplets")
    return triplets


def extract_triplets_batch_llm(chunks: List[Any], max_chars: int = 6000) -> List[KGTriplet]:
    """Batch extraction — multiple chunks in one LLM call."""
    if not KG_ENABLED or not chunks:
        return []

    first     = chunks[0]
    section   = getattr(first, "section_label", "general") or "general"
    title     = getattr(first, "title", "") or ""
    parts: List[str] = []
    total_chars = 0
    cid_to_chunk: Dict[str, Any] = {}

    for chunk in chunks:
        text = getattr(chunk, "text", "").strip()
        if len(text) < 150:
            continue
        cid  = getattr(chunk, "chunk_id", "")
        text = _truncate_to_sentence_boundary(text, max_chars=1800)
        entry = f"[ChunkID: {cid}]\n{text}"
        if total_chars + len(entry) > max_chars and parts:
            break
        parts.append(entry)
        cid_to_chunk[cid] = chunk
        total_chars += len(entry)

    if not parts:
        return []

    combined_text = "\n\n".join(parts)

    prompt = _SCIENTIFIC_GRAPH_PROMPT.format(
        text=combined_text,
        max_triplets=KG_MAX_TRIPLETS,
        section=section,
        title=title,
    )

    if KG_CALL_DELAY_SEC > 0:
        time.sleep(KG_CALL_DELAY_SEC)

    raw      = _call_llm(prompt, max_tokens=1024)
    raw_list = _parse_triplets_response(raw)

    triplets: List[KGTriplet] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        raw_cid       = str(item.get("chunk_id", "")).strip()
        if not raw_cid or raw_cid not in cid_to_chunk:
            continue
        matched_chunk = cid_to_chunk[raw_cid]
        triplet = _build_triplet(item, matched_chunk)
        if triplet is None:
            continue
        triplets.append(triplet)

    print(f"[KG] Batch {len(parts)} chunks → {len(triplets)} triplets (1 LLM call)")
    return triplets


def upsert_triplets(triplets: List[KGTriplet]) -> int:
    """Backward-compatible facade for writing triplets into the anchored graph."""
    if not triplets:
        return 0
    from kg_neo4j_ops import upsert_hybrid_chunk_graph

    grouped: Dict[tuple[str, str], List[KGTriplet]] = {}
    skipped = 0
    for triplet in triplets:
        relation = normalize_relation_name(triplet.relation)
        if relation is None:
            skipped += 1
            continue
        workspace_id = triplet.workspace_id or "default"
        source = triplet.source or ""
        triplet.relation = relation
        grouped.setdefault((workspace_id, source), []).append(triplet)

    if not grouped:
        print(f"[KG][Neo4j] Upserted 0 triplets; skipped {skipped} invalid/forbidden triplet(s)")
        return 0

    manager = get_neo4j_manager()
    written = 0
    with manager.session() as session:
        for (workspace_id, source), group in grouped.items():
            chunks = [
                SimpleNamespace(
                    chunk_id=triplet.chunk_id,
                    text=triplet.evidence_preview or f"{triplet.subject} {triplet.relation} {triplet.object}",
                    page=triplet.page,
                    section_label="kg",
                    content_type="text",
                    has_table=False,
                    has_formula=False,
                    has_image=False,
                )
                for triplet in group
                if triplet.chunk_id
            ]
            written += upsert_hybrid_chunk_graph(
                session=session,
                chunks=chunks,
                triplets=group,
                file_name=source,
                workspace_id=workspace_id,
            )
    print(f"[KG][Neo4j] Upserted {written} triplets; skipped {skipped} invalid/forbidden triplet(s)")
    return written
