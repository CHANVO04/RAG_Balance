"""
ingest/config.py — Constants và cấu hình cho toàn bộ ingest pipeline.
Gọi load_dotenv() một lần duy nhất tại đây — các module khác không cần gọi lại.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# ── Directories ──────────────────────────────────────────────────────────────
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(_BACKEND_DIR, "data")
VECTOR_DIR = os.path.join(_BACKEND_DIR, "db")

# ── Embedding ─────────────────────────────────────────────────────────────────
EMBED_MODEL      = "text-embedding-3-small"   # OpenAI embedding model (Cheaper, high accuracy)
EMBED_DIM        = 1536                         # default dimension of text-embedding-3-small
EMBED_BATCH_SIZE = 100                          # OpenAI allows up to 2048; 100 is safe default
EMBED_PRICE_PER_1M_TOKENS = float(os.getenv("EMBED_PRICE_PER_1M_TOKENS", "0.02"))

# Tokenizer for Docling HybridChunker. Use OpenAI/tiktoken to align chunk
# accounting with text-embedding-3-small.
CHUNK_TOKENIZER  = "cl100k_base"

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ── Chunking ──────────────────────────────────────────────────────────────────

CHUNK_MAX_TOKENS    = 512
CHUNK_OVERLAP_RATIO = 0.15
MIN_CHUNK_CHARS     = 30

# ── Supported file extensions ─────────────────────────────────────────────────
SUPPORTED_EXTS = {".pdf", ".docx", ".pptx", ".html", ".htm"}

# ── Qdrant ────────────────────────────────────────────────────────────────────
QDRANT_HOST    = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT    = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "") or None   # None disables auth header

# ── Vision / LLM ──────────────────────────────────────────────────────────────
IMAGE_VLM_MODEL           = os.getenv("IMAGE_VLM_MODEL", "gpt-4.1-mini")
FORMULA_VLM_MODEL         = os.getenv("FORMULA_VLM_MODEL", "gpt-4.1-mini")
TABLE_LLM_MODEL           = os.getenv("TABLE_LLM_MODEL", "gpt-4.1-mini")
IMAGE_RELEVANCE_THRESHOLD = 0.6
LLM_MODEL                 = "gpt-4.1-mini"

# ── Knowledge Graph ───────────────────────────────────────────────────────────
KG_MODE                = os.getenv("KG_MODE", "light")
KG_BATCH_SIZE          = int(os.getenv("KG_BATCH_SIZE", "1"))
KG_MAX_CHARS_PER_BATCH = int(os.getenv("KG_MAX_CHARS_PER_BATCH", "10000"))
KG_INCLUDE_VISUALS     = os.getenv("KG_INCLUDE_VISUALS", "false").lower() == "true"

# ── Paths ─────────────────────────────────────────────────────────────────────
REGISTRY_PATH  = os.path.join(VECTOR_DIR, "registry.json")
DOC_STORE_PATH = os.path.join(VECTOR_DIR, "documents_store.json")

# ── Neo4j Knowledge Graph ─────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "rag_password")
