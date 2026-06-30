"""Session memory store with automatic Redis → InMemory fallback.

Exports a singleton ``session_store`` that backs ``build_memory_context``
in context.py.  Callers do not need to know which backend is active.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(service="memory_store")

# Schema version bump when the shape of SessionMemory changes.
SCHEMA_VERSION = 1


class SessionMemory:
    """In-memory representation of one session's accumulated context."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at: float = time.time()
        self.updated_at: float = time.time()
        self.schema_version: int = SCHEMA_VERSION

        # Accumulated shopping state (see handoff schema).
        self.shopping_state: Dict[str, Any] = {}
        # Recent messages kept for the deterministic memory layer.
        self.messages: list[Dict[str, str]] = []
        # LLM-compressed summary (future).
        self.summary: Optional[Dict[str, Any]] = None
        # Last few recommended product ids (for dedup).
        self.last_recommended_ids: list[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version,
            "shopping_state": self.shopping_state,
            "messages": self.messages,
            "summary": self.summary,
            "last_recommended_ids": self.last_recommended_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMemory":
        inst = cls(session_id=data.get("session_id", ""))
        inst.created_at = float(data.get("created_at", time.time()))
        inst.updated_at = float(data.get("updated_at", time.time()))
        inst.schema_version = int(data.get("schema_version", SCHEMA_VERSION))
        inst.shopping_state = data.get("shopping_state") or {}
        inst.messages = data.get("messages") or []
        inst.summary = data.get("summary")
        inst.last_recommended_ids = data.get("last_recommended_ids") or []
        return inst


# ── store interface ────────────────────────────────────────────────────


class BaseSessionStore:
    async def load(self, session_id: str) -> Optional[SessionMemory]:
        raise NotImplementedError

    async def save(self, memory: SessionMemory) -> None:
        raise NotImplementedError

    async def delete(self, session_id: str) -> None:
        raise NotImplementedError


# ── InMemory fallback ──────────────────────────────────────────────────


class InMemorySessionStore(BaseSessionStore):
    def __init__(self) -> None:
        self._store: Dict[str, SessionMemory] = {}

    async def load(self, session_id: str) -> Optional[SessionMemory]:
        return self._store.get(session_id)

    async def save(self, memory: SessionMemory) -> None:
        memory.updated_at = time.time()
        self._store[memory.session_id] = memory
        # Keep bounded (FIFO eviction).
        if len(self._store) > 500:
            oldest = min(self._store, key=lambda k: self._store[k].updated_at)  # type: ignore[type-var]
            del self._store[oldest]

    async def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)


# ── Redis store ────────────────────────────────────────────────────────


class RedisSessionStore(BaseSessionStore):
    def __init__(self) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
        )
        self._ttl = getattr(settings, "MEMORY_TTL_SECONDS", 6 * 3600)

    def _key(self, session_id: str) -> str:
        return f"assistgen:session:{session_id}"

    async def load(self, session_id: str) -> Optional[SessionMemory]:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        try:
            return SessionMemory.from_dict(json.loads(raw))
        except Exception:
            return None

    async def save(self, memory: SessionMemory) -> None:
        memory.updated_at = time.time()
        await self._redis.setex(
            self._key(memory.session_id),
            self._ttl,
            json.dumps(memory.to_dict(), ensure_ascii=False, default=str),
        )

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))


# ── auto-fallback singleton ────────────────────────────────────────────


async def _create_store() -> BaseSessionStore:
    """Try Redis; fall back to InMemory on any failure."""
    redis_host = getattr(settings, "REDIS_HOST", None)
    if redis_host:
        try:
            store = RedisSessionStore()
            # Quick connectivity check.
            await store._redis.ping()
            logger.info("Memory store: Redis (connected)")
            return store
        except Exception as exc:
            logger.info(f"Memory store: Redis unavailable ({exc}), using InMemory fallback")
    else:
        logger.info("Memory store: InMemory (no Redis configured)")
    return InMemorySessionStore()


_session_store: Optional[BaseSessionStore] = None


async def get_session_store() -> BaseSessionStore:
    global _session_store
    if _session_store is None:
        _session_store = await _create_store()
    return _session_store


# For testing / reset.
def _reset_store() -> None:
    global _session_store
    _session_store = None
