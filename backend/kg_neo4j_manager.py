"""
kg_neo4j_manager.py — Neo4jManager connection pool, UsageTracker, KGTriplet dataclass.
Split from kg_neo4j.py (God Module refactor). kg_neo4j.py remains as backward-compat facade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from kg_neo4j_config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, INIT_SCHEMA_CYPHER


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN USAGE TRACKER
# ══════════════════════════════════════════════════════════════════════════════

class UsageTracker:
    INPUT_PRICE_PER_1M  = 0.40   # gpt-4.1-mini
    OUTPUT_PRICE_PER_1M = 1.60

    def __init__(self) -> None:
        self.prompt_tokens:     int = 0
        self.completion_tokens: int = 0
        self.calls:             int = 0

    def add(self, usage: Any) -> None:
        if usage is None:
            return
        self.prompt_tokens     += getattr(usage, "prompt_tokens",     0) or 0
        self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
        self.calls             += 1

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.prompt_tokens     / 1_000_000 * self.INPUT_PRICE_PER_1M
            + self.completion_tokens / 1_000_000 * self.OUTPUT_PRICE_PER_1M
        )

    def summary(self) -> Dict[str, Any]:
        return {
            "calls":              self.calls,
            "prompt_tokens":      self.prompt_tokens,
            "completion_tokens":  self.completion_tokens,
            "total_tokens":       self.prompt_tokens + self.completion_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }

    def reset(self) -> None:
        self.prompt_tokens = self.completion_tokens = self.calls = 0


usage_tracker = UsageTracker()  # module-level singleton


# ══════════════════════════════════════════════════════════════════════════════
# DATACLASS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class KGTriplet:
    subject: str
    relation: str
    object: str
    source: str
    page: int | None = None
    chunk_id: str | None = None
    workspace_id: str = "default"
    description: str = ""
    subject_type: str = "Concept"
    object_type: str = "Concept"
    subject_key: str = ""
    object_key: str = ""
    evidence_preview: str = ""
    confidence: float = 0.0
    visual_ids: list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# NEO4J CONNECTION MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class Neo4jManager:
    def __init__(self) -> None:
        self._driver = None

    def connect(self) -> None:
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
        )

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    def init_schema(self) -> None:
        with self.session() as s:
            for stmt in INIT_SCHEMA_CYPHER:
                s.run(stmt)

    def test_connection(self) -> bool:
        try:
            with self.session() as s:
                result = s.run("RETURN 1 AS ping")
                return result.single()["ping"] == 1
        except Exception:
            return False

    def session(self):
        if self._driver is None:
            self.connect()
        return self._driver.session()


_neo4j_manager: Optional[Neo4jManager] = None


def get_neo4j_manager() -> Neo4jManager:
    global _neo4j_manager
    if _neo4j_manager is None:
        _neo4j_manager = Neo4jManager()
        _neo4j_manager.connect()
        _neo4j_manager.init_schema()
        print("[KG][Neo4j] Connected and schema initialized.")
    return _neo4j_manager
