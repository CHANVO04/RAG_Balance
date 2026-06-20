import os
from dotenv import load_dotenv

load_dotenv()

# ── Directories ───────────────────────────────────────────────────────────────
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTOR_DIR = os.path.join(_BACKEND_DIR, "db")

# ── Qdrant ────────────────────────────────────────────────────────────────────
QDRANT_HOST    = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT    = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "") or None

# ── Models ────────────────────────────────────────────────────────────────────
EMBED_MODEL  = "text-embedding-3-small"
EMBED_DIM    = 1536
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
LLM_MODEL    = "gpt-4.1-mini"

# ── Retrieval tuning ──────────────────────────────────────────────────────────
DEFAULT_RETRIEVE_K  = 15
DEFAULT_TOP_N       = 5
# 0.87: balances hit rate vs. false-positive risk for scientific Q&A.
# text-embedding-3-small gives ~0.88-0.91 for paraphrased questions on the same topic.
# Do not lower below 0.85 to avoid returning wrong cached answers.
CACHE_THRESHOLD     = 0.87

# ── Anchored Knowledge Graph retrieval ───────────────────────────────────────
KG_ENTITY_EXPANSION_HOPS = int(os.getenv("KG_ENTITY_EXPANSION_HOPS", "2"))
KG_MAX_ANCHORED_RELATIONS = int(os.getenv("KG_MAX_ANCHORED_RELATIONS", "20"))
KG_MIN_RELATION_CONFIDENCE = float(os.getenv("KG_MIN_RELATION_CONFIDENCE", "0.0"))

IMAGE_RELEVANCE_THRESHOLD = float(os.getenv("IMAGE_RELEVANCE_THRESHOLD", "0.6"))
# Qdrant returns similarity (high = more relevant); threshold on score directly
IMAGE_SCORE_THRESHOLD = IMAGE_RELEVANCE_THRESHOLD
IMAGE_TOP_K           = 3

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
