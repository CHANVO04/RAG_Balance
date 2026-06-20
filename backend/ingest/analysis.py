"""
Utilities for deriving compact retrieval summaries from full visual analyses.
"""

from __future__ import annotations

import re
from typing import Dict


_SECTION_BY_TYPE: Dict[str, str] = {
    "table": "SEMANTIC SUMMARY",
    "formula": "RETRIEVAL SUMMARY",
    "image": "COMPREHENSIVE SEMANTIC SUMMARY",
}


def extract_analysis_short(visual_type: str, analysis_markdown: str, max_chars: int = 900) -> str:
    """Extract the retrieval-focused section from a full visual analysis."""
    text = (analysis_markdown or "").strip()
    if not text:
        return ""

    section = _SECTION_BY_TYPE.get((visual_type or "").lower())
    if not section:
        return _compact_fallback(text, max_chars)

    pattern = re.compile(
        rf"^###\s*\d+\.\s*{re.escape(section)}\s*$"
        rf"(?P<body>.*?)"
        rf"(?=^###\s*\d+\.|\Z)",
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return _compact_fallback(text, max_chars)

    return _compact_fallback(match.group("body"), max_chars)


def ensure_analysis_short(visual: dict, visual_type: str) -> str:
    """Populate and return visual['analysis_short'] without extra LLM calls."""
    short = (visual.get("analysis_short") or "").strip()
    if short:
        return short
    short = extract_analysis_short(visual_type, visual.get("analysis_markdown", ""))
    visual["analysis_short"] = short
    return short


def _compact_fallback(text: str, max_chars: int) -> str:
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0].strip()
