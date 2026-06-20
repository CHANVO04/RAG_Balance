"""
kg_neo4j.py — Backward-compatibility facade.
═══════════════════════════════════════════════════════════════════════════════
All logic has been split into focused sub-modules:

  kg_neo4j_config.py    — constants, Cypher strings
  kg_neo4j_manager.py   — Neo4jManager, UsageTracker, KGTriplet
  kg_neo4j_extractor.py — Layer 1 (LLM extraction) + Layer 2 (normalization) + upsert_triplets
  kg_neo4j_traversal.py — Layer 3 (lookup_kg_context)
  kg_neo4j_ops.py       — delete_document_kg, upsert_visual_nodes, get_graph_for_viz

This file re-exports everything so that all existing callers
  (pipeline.py, kg.py, kg_retriever.py, app.py, tests/)
continue to work with zero changes.
"""

# ── Config & constants ────────────────────────────────────────────────────────
from kg_neo4j_config import (
    NEO4J_URI,
    NEO4J_USERNAME,
    NEO4J_PASSWORD,
    KG_LLM_PROVIDER,
    KG_LLM_MODEL,
    KG_MAX_TRIPLETS,
    KG_ENABLED,
    KG_CALL_DELAY_SEC,
)

# ── Manager, models, tracker ──────────────────────────────────────────────────
from kg_neo4j_manager import (
    UsageTracker,
    usage_tracker,
    KGTriplet,
    Neo4jManager,
    get_neo4j_manager,
)

# ── Extraction + normalization ────────────────────────────────────────────────
from kg_neo4j_extractor import (
    extract_triplets_llm,
    extract_triplets_batch_llm,
    upsert_triplets,
)

# ── Query-time traversal ──────────────────────────────────────────────────────
from kg_neo4j_traversal import lookup_kg_context

# ── Graph operations ──────────────────────────────────────────────────────────
from kg_neo4j_ops import (
    upsert_visual_nodes,
    delete_document_kg,
    get_graph_for_viz,
)

__all__ = [
    # config
    "NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD",
    "KG_LLM_PROVIDER", "KG_LLM_MODEL",
    "KG_MAX_TRIPLETS", "KG_ENABLED", "KG_CALL_DELAY_SEC",
    # manager
    "UsageTracker", "usage_tracker", "KGTriplet", "Neo4jManager", "get_neo4j_manager",
    # extractor
    "extract_triplets_llm", "extract_triplets_batch_llm", "upsert_triplets",
    # traversal
    "lookup_kg_context",
    # ops
    "upsert_visual_nodes", "delete_document_kg", "get_graph_for_viz",
]