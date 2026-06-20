from query.config import (
    EMBED_MODEL, RERANK_MODEL, OPENAI_API_KEY,
    QDRANT_HOST, QDRANT_PORT, QDRANT_API_KEY,
)

_models = {}


def get_embedder():
    if "embedder" not in _models:
        from ingest.embedder import get_embedding_model
        print(f"[INIT] Loading Embedder: {EMBED_MODEL} (OpenAI)...")
        _models["embedder"] = get_embedding_model(EMBED_MODEL)
    return _models["embedder"]


def get_reranker():
    if "reranker" not in _models:
        from sentence_transformers import CrossEncoder
        print(f"[INIT] Loading Reranker: {RERANK_MODEL}...")
        _models["reranker"] = CrossEncoder(RERANK_MODEL)
    return _models["reranker"]


def get_llm_client():
    if "llm" not in _models:
        from openai import OpenAI
        if not OPENAI_API_KEY:
            raise ValueError("Không tìm thấy OPENAI_API_KEY trong file .env")
        _models["llm"] = OpenAI(api_key=OPENAI_API_KEY)
    return _models["llm"]


def get_qdrant_client():
    if "qdrant" not in _models:
        from qdrant_client import QdrantClient
        print(f"[INIT] Connecting Qdrant → {QDRANT_HOST}:{QDRANT_PORT}")
        _models["qdrant"] = QdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            api_key=QDRANT_API_KEY,
        )
    return _models["qdrant"]


def get_collection(name: str):
    """
    Return (client, name) tuple — downstream code calls client methods with name.
    Raises RuntimeError if collection does not exist (intentional: detect missing ingest).
    """
    client = get_qdrant_client()
    try:
        client.get_collection(name)   # raises if missing
        return client, name
    except Exception as e:
        raise RuntimeError(
            f"Collection '{name}' chưa tồn tại ({e}). Hãy chạy ingest trước."
        )


# Backward-compat alias used by legacy code referencing get_chroma_client
def get_chroma_client():
    return get_qdrant_client()
