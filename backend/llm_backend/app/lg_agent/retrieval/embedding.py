"""Embedding provider abstraction for Qdrant indexing and retrieval.

Supports:
- ``local``: SentenceTransformer (HuggingFace) — offline, no API key needed.
- ``dashscope``: DashScope / Tongyi ``text-embedding-v4`` via OpenAI-compatible API.

Includes a simple JSONL file cache for indexing-time embedding calls so
repeated texts do not re-hit the API.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import List, Optional

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(service="embedding")

# ── cache paths ───────────────────────────────────────────────────────────

_CACHE_DIR = Path(__file__).resolve().parents[4] / ".cache"
_CACHE_FILE = _CACHE_DIR / "embedding_cache.jsonl"


def _cache_key(provider: str, model: str, dimension: int, text: str) -> str:
    """Stable cache key — does NOT include API key."""
    raw = f"{provider}|{model}|{dimension}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_cache() -> dict[str, list[float]]:
    if not settings.EMBEDDING_CACHE_ENABLED:
        return {}
    if not _CACHE_FILE.exists():
        return {}
    cache: dict[str, list[float]] = {}
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    cache[entry["key"]] = entry["vector"]
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception:
        return {}
    return cache


def _write_cache(entries: list[tuple[str, list[float]]]) -> None:
    if not settings.EMBEDDING_CACHE_ENABLED:
        return
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(_CACHE_FILE, "a", encoding="utf-8") as f:
            for key, vector in entries:
                f.write(json.dumps({"key": key, "vector": vector}, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── provider dispatch ─────────────────────────────────────────────────────


def _provider_label() -> str:
    return (
        f"{settings.EMBEDDING_PROVIDER}/{settings.EMBEDDING_MODEL}"
        f"@{settings.EMBEDDING_DIMENSION}"
    )


# ── public API ────────────────────────────────────────────────────────────


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a batch of texts and return vectors of ``EMBEDDING_DIMENSION``."""
    if not texts:
        return []

    provider = settings.EMBEDDING_PROVIDER
    if provider == "dashscope":
        vectors = _embed_dashscope(texts)
    else:
        vectors = _embed_local(texts)

    # Validate dimension.
    for i, vec in enumerate(vectors):
        if len(vec) != settings.EMBEDDING_DIMENSION:
            raise RuntimeError(
                f"Embedding dimension mismatch: got {len(vec)}, expected {settings.EMBEDDING_DIMENSION} "
                f"(text index {i}: {texts[i][:60]}...)"
            )
    return vectors


def embed_query(query: str) -> List[float]:
    """Embed a single query string. Returns a flat list of floats."""
    return embed_texts([query])[0]


# ── dashscope provider ────────────────────────────────────────────────────


def _embed_dashscope(texts: List[str]) -> List[List[float]]:
    """Call DashScope ``text-embedding-v4`` with caching."""
    api_key = settings.EMBEDDING_API_KEY
    base_url = settings.EMBEDDING_BASE_URL.rstrip("/")
    model = settings.EMBEDDING_MODEL
    dimension = settings.EMBEDDING_DIMENSION
    batch_size = max(1, settings.EMBEDDING_BATCH_SIZE)

    if not api_key:
        raise RuntimeError(
            "EMBEDDING_API_KEY is not set. "
            "Set EMBEDDING_PROVIDER=dashscope EMBEDDING_API_KEY=... in .env"
        )

    cache = _read_cache()
    results: list[Optional[list[float]]] = [None] * len(texts)
    cache_hits = 0
    to_embed: list[tuple[int, str]] = []

    for i, text in enumerate(texts):
        key = _cache_key("dashscope", model, dimension, text)
        if key in cache:
            results[i] = cache[key]
            cache_hits += 1
        else:
            to_embed.append((i, text))

    if cache_hits:
        logger.info(
            f"Embedding cache hits: {cache_hits}/{len(texts)} "
            f"({cache_hits * 100 // len(texts)}%)"
        )

    if to_embed:
        import httpx

        endpoint = f"{base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        new_entries: list[tuple[str, list[float]]] = []

        for batch_start in range(0, len(to_embed), batch_size):
            batch = to_embed[batch_start : batch_start + batch_size]
            payload = {
                "model": model,
                "input": [text for _, text in batch],
                "dimensions": dimension,
            }

            # Retry once on transient errors.
            response = None
            last_error = None
            for attempt in range(2):
                try:
                    with httpx.Client(timeout=30.0) as client:
                        resp = client.post(endpoint, json=payload, headers=headers)
                        resp.raise_for_status()
                        response = resp.json()
                        last_error = None
                        break
                except Exception as exc:
                    last_error = exc
                    if attempt == 0:
                        time.sleep(1.0)

            if last_error is not None:
                raise RuntimeError(
                    f"DashScope embedding API failed after 2 attempts: {last_error}"
                )

            data_list = response.get("data") or []
            for j, item in enumerate(data_list):
                idx, text = batch[j]
                vec = item.get("embedding") or []
                results[idx] = vec
                key = _cache_key("dashscope", model, dimension, text)
                new_entries.append((key, vec))

            logger.info(
                f"Embedded {batch_start + len(batch)}/{len(to_embed)} "
                f"via {_provider_label()}"
            )

        _write_cache(new_entries)

    # Every slot must be filled.
    for i, vec in enumerate(results):
        if vec is None:
            raise RuntimeError(f"Missing embedding for text index {i}: {texts[i][:60]}...")
    return [v for v in results if v is not None]  # type narrowing


# ── local provider ────────────────────────────────────────────────────────


def _embed_local(texts: List[str]) -> List[List[float]]:
    """Use local SentenceTransformer model."""
    model = _get_local_model()
    vectors = model.encode(texts, normalize_embeddings=True)
    dimension = settings.EMBEDDING_DIMENSION

    # Truncate or pad to configured dimension.
    result = []
    for vec in vectors:
        v = vec.tolist()
        if len(v) > dimension:
            v = v[:dimension]
        elif len(v) < dimension:
            v = v + [0.0] * (dimension - len(v))
        result.append(v)
    return result


# ── local model singleton ─────────────────────────────────────────────────

_local_model = None


def _get_local_model():
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        model_name = settings.QDRANT_EMBEDDING_MODEL
        _local_model = SentenceTransformer(model_name)
        logger.info(f"Loaded local embedding model: {model_name}")
    return _local_model
