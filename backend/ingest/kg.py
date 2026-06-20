"""
ingest/kg.py — Thin wrapper around kg_neo4j functions.
"""
from __future__ import annotations

import math
from typing import Any, List

from kg_neo4j import (
    KGTriplet,
    extract_triplets_llm,
    extract_triplets_batch_llm,
    upsert_visual_nodes,
)
from kg_neo4j_manager import get_neo4j_manager
from kg_neo4j_ops import upsert_hybrid_chunk_graph
from ingest.config import KG_INCLUDE_VISUALS, KG_BATCH_SIZE, KG_MAX_CHARS_PER_BATCH
from ingest.models import Chunk


def run_kg_step(
    chunks: List[Chunk],
    parsed: Any,
    source_file: str,
    workspace_id: str = "default",
) -> int:
    """
    Extract triplets from all chunks of one file and upsert to Neo4j.

    Mode controlled by KG_BATCH_SIZE (env var, default=6):
      KG_BATCH_SIZE=1  → per-chunk mode: 1 LLM call per chunk, highest accuracy.
                          Trade-off: N API calls for N chunks.
      KG_BATCH_SIZE>1  → batch mode: KG_BATCH_SIZE chunks per LLM call.
                          Saves ~25-50% on KG cost. Slight accuracy decrease for
                          cross-chunk relations, acceptable for most papers.

    Returns: number of triplets extracted.
    """
    all_triplets: List[KGTriplet] = []

    if KG_BATCH_SIZE > 1:
        n_batches = math.ceil(len(chunks) / KG_BATCH_SIZE)
        print(
            f"[KG] {source_file}: {len(chunks)} chunks → "
            f"{n_batches} batch(es) of {KG_BATCH_SIZE} (KG_BATCH_SIZE={KG_BATCH_SIZE})"
        )
        for i in range(0, len(chunks), KG_BATCH_SIZE):
            batch = chunks[i:i + KG_BATCH_SIZE]
            triplets = extract_triplets_batch_llm(batch, max_chars=KG_MAX_CHARS_PER_BATCH)
            all_triplets.extend(triplets)
    else:
        print(f"[KG] {source_file}: processing {len(chunks)} chunks individually (KG_BATCH_SIZE=1)")
        for chunk in chunks:
            triplets = extract_triplets_llm(chunk)
            all_triplets.extend(triplets)

    if KG_INCLUDE_VISUALS:
        upsert_visual_nodes(parsed, source_file, workspace_id=workspace_id)

    for triplet in all_triplets:
        triplet.workspace_id = workspace_id
        if not triplet.source:
            triplet.source = source_file

    file_hash = getattr(parsed, "file_hash", "") or ""
    metadata = getattr(parsed, "metadata", {}) or {}
    total_pages = int(metadata.get("total_pages", 0) or 0)

    manager = get_neo4j_manager()
    with manager.session() as session:
        written = upsert_hybrid_chunk_graph(
            session=session,
            chunks=chunks,
            triplets=all_triplets,
            file_name=source_file,
            workspace_id=workspace_id,
            file_hash=file_hash,
            total_pages=total_pages,
        )

    print(
        f"[KG] {source_file}: {len(chunks)} chunk anchors, "
        f"{written}/{len(all_triplets)} triplets -> Neo4j"
    )

    return len(all_triplets)
