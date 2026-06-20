from __future__ import annotations

import re
import unicodedata


ALLOWED_ENTITY_TYPES = {
    "Method",
    "Model",
    "Dataset",
    "Metric",
    "Result",
    "Hardware",
    "Signal",
    "Parameter",
    "Formula",
    "Table",
    "Figure",
    "Problem",
    "Limitation",
    "Contribution",
    "Concept",
}

FORBIDDEN_RELATIONS = {
    "RELATED_TO",
    "ASSOCIATED_WITH",
    "CONNECTED_TO",
    "IS_A",
    "HAS",
    "MENTIONS",
    "INVOLVES",
    "USES",
}


def normalize_entity_type(value: str | None) -> str:
    if not value:
        return "Concept"
    cleaned = str(value).strip()
    return cleaned if cleaned in ALLOWED_ENTITY_TYPES else "Concept"


def normalize_entity_label(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", normalized).strip()


def canonical_entity_key(value: str | None) -> str:
    label = normalize_entity_label(value).lower()
    label = re.sub(r"[^a-z0-9]+", "_", label)
    label = re.sub(r"_+", "_", label).strip("_")
    return label


def normalize_relation_name(value: str | None) -> str | None:
    raw = unicodedata.normalize("NFKC", str(value or ""))
    relation = re.sub(r"[^A-Za-z0-9]+", "_", raw.upper())
    relation = re.sub(r"_+", "_", relation).strip("_")
    if relation != "IS_A" and relation.startswith("IS_"):
        relation = relation[3:]
    if not relation or relation in FORBIDDEN_RELATIONS:
        return None
    return relation
