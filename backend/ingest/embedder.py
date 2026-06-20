"""
ingest/embedder.py — OpenAIEmbedderWrapper + singleton cache.

Replaces SentenceTransformerWrapper (BAAI/bge-m3) with OpenAI text-embedding-3-small.

INTERFACE CONTRACT (matches SentenceTransformer.encode() behavior):
  encode(str)        → np.ndarray shape (dim,)      — 1D, used by query/cache + vector_retriever
  encode(List[str])  → np.ndarray shape (n, dim)    — 2D, used by embed_chunks + upsert_images
This dual behavior is critical: the query layer passes a single string, ingest passes a list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Union

import numpy as np

from ingest.config import EMBED_MODEL, EMBED_DIM, EMBED_BATCH_SIZE, OPENAI_API_KEY
from ingest.models import Chunk

# OpenAI text-embedding-3-small hard limit.
# NOTE: HybridChunker uses BAAI/bge-m3 tokenizer (WordPiece) to count tokens,
# but OpenAI uses cl100k_base (tiktoken). For LaTeX-heavy academic text the
# token counts can diverge. This guard ensures we never hit a 400 error from
# OpenAI regardless of tokenizer differences.
_OPENAI_EMBED_TOKEN_LIMIT = 8100  # conservative, actual limit is 8191


@dataclass
class EmbeddingUsage:
    model: str
    input_tokens: int = 0


def _safe_truncate_for_openai(text: str) -> str:
    """Truncate text to stay within OpenAI embedding token limit.

    Uses cl100k_base (tiktoken) for accurate counting. Falls back to
    char-based truncation (~4 chars/token) if tiktoken is unavailable.
    Only activates for texts that are suspiciously long (>6000 chars),
    so normal chunks pass through with zero overhead.
    """
    if len(text) <= 6000:
        return text
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        if len(tokens) <= _OPENAI_EMBED_TOKEN_LIMIT:
            return text
        truncated = enc.decode(tokens[:_OPENAI_EMBED_TOKEN_LIMIT])
        print(f"[EMBED][WARN] Chunk truncated {len(tokens)} → {_OPENAI_EMBED_TOKEN_LIMIT} tokens "
              f"(OpenAI limit). Chunker/embedder tokenizer mismatch.")
        return truncated
    except ImportError:
        # tiktoken not installed — char-based fallback (~4 chars/token)
        char_limit = _OPENAI_EMBED_TOKEN_LIMIT * 4
        if len(text) > char_limit:
            print(f"[EMBED][WARN] Chunk truncated by char fallback (tiktoken not installed)")
            return text[:char_limit]
        return text


class OpenAIEmbedderWrapper:
    """
    Thin wrapper around openai.embeddings.create() that mirrors the
    SentenceTransformer.encode() interface so all downstream callers work unchanged.

    Key design decisions:
    - Single string input → returns 1D array (dim,), matching ST behavior for query side.
    - List input → returns 2D array (n, dim), matching ST behavior for ingest side.
    - OpenAI embeddings are already L2-normalized; normalize_embeddings param kept for compat.
    - Batching is handled internally; callers can pass any batch_size up to 2048.
    """

    def __init__(self, model_name: str = EMBED_MODEL, dim: int = EMBED_DIM):
        from openai import OpenAI
        if not OPENAI_API_KEY:
            raise ValueError("[EMBED][ERR] OPENAI_API_KEY không tìm thấy trong .env")
        self._client    = OpenAI(api_key=OPENAI_API_KEY)
        self._model     = model_name
        self._dim       = dim
        self.last_usage = EmbeddingUsage(model=model_name)
        print(f"[EMBED] OpenAI Embedder ready | model={model_name} | dim={dim}")

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = EMBED_BATCH_SIZE,
        normalize_embeddings: bool = True,  # noqa: kept for SentenceTransformer API compat; OpenAI vecs are pre-normalized
    ) -> np.ndarray:
        """
        Embed texts via OpenAI API.
        - str input  → returns np.ndarray shape (dim,)
        - list input → returns np.ndarray shape (n, dim)
        """
        single_input = isinstance(texts, str)
        if single_input:
            texts = [texts]

        # Guard against tokenizer mismatch (bge-m3 vs cl100k_base).
        texts = [_safe_truncate_for_openai(t) for t in texts]

        all_embeddings: List[List[float]] = []
        total = len(texts)
        total_batches = (total - 1) // batch_size + 1

        for i in range(0, total, batch_size):
            batch     = texts[i: i + batch_size]
            batch_num = i // batch_size + 1
            if total_batches > 1:
                print(f"[EMBED] Batch {batch_num}/{total_batches} ({len(batch)} texts) → OpenAI API")

            response = self._client.embeddings.create(
                model=self._model,
                input=batch,
                dimensions=self._dim,
            )
            usage = getattr(response, "usage", None)
            input_tokens = (
                getattr(usage, "prompt_tokens", None)
                or getattr(usage, "total_tokens", None)
                or 0
            )
            self.last_usage.input_tokens += int(input_tokens or 0)
            # Sort by index to guarantee order (OpenAI docs say order is preserved but be safe)
            sorted_data = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend([item.embedding for item in sorted_data])

        arr = np.array(all_embeddings, dtype=np.float32)  # shape (n, dim)

        if single_input:
            return arr[0]   # shape (dim,) — 1D for query-side callers
        return arr          # shape (n, dim) — 2D for ingest-side callers


# ── Singleton cache — one OpenAI client per process ──────────────────────────
_embedding_model_cache: dict = {}


def get_embedding_model(model_name: str = EMBED_MODEL) -> OpenAIEmbedderWrapper:
    """
    Return singleton OpenAIEmbedderWrapper. model_name kept for API compat with pipeline CLI.
    """
    if model_name not in _embedding_model_cache:
        _embedding_model_cache[model_name] = OpenAIEmbedderWrapper(model_name, dim=EMBED_DIM)
    return _embedding_model_cache[model_name]


def embed_chunks(chunks: List[Chunk], model: OpenAIEmbedderWrapper,
                 batch_size: int = EMBED_BATCH_SIZE) -> np.ndarray:
    """
    Embed list of chunks. Returns np.ndarray shape (n, dim).
    Batching is delegated to model.encode() internally.
    """
    texts = [c.text for c in chunks]
    print(f"[EMBED] Embedding {len(texts)} chunks via OpenAI API ({model._model})...")
    return model.encode(texts, batch_size=batch_size)
