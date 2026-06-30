"""Memory and cache manager for AssistGen.

Memory is a cross-cutting layer, not an Agent. This first version focuses on
safe Redis-backed cache helpers with no-op fallback.
"""

from __future__ import annotations

import hashlib
import json
import socket
from typing import Any, Optional

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(service="memory_manager")


class MemoryManager:
    def __init__(self):
        self._redis = None
        self._redis_checked = False

    def cache_key(self, namespace: str, payload: Any) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"assistgen:cache:{namespace}:{digest}"

    async def get_json(self, key: str) -> Optional[Any]:
        redis = await self._get_redis()
        if redis is None:
            return None
        try:
            value = await redis.get(key)
            if not value:
                return None
            return json.loads(value)
        except Exception as e:
            logger.warning(f"Redis get failed: {e}")
            return None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        redis = await self._get_redis()
        if redis is None:
            return
        try:
            await redis.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl or settings.REDIS_CACHE_EXPIRE)
        except Exception as e:
            logger.warning(f"Redis set failed: {e}")

    async def get_session(self, session_id: str) -> Optional[dict]:
        return await self.get_json(f"assistgen:session:{session_id}")

    async def set_session(self, session_id: str, value: dict, ttl: int = 7200) -> None:
        await self.set_json(f"assistgen:session:{session_id}", value, ttl=ttl)

    async def _get_redis(self):
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        if not _is_port_open(settings.REDIS_HOST, settings.REDIS_PORT):
            logger.info("Redis memory/cache disabled: port unavailable")
            self._redis = None
            return self._redis
        try:
            import redis.asyncio as redis

            client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            await client.ping()
            self._redis = client
            logger.info("Redis memory/cache enabled")
        except Exception as e:
            logger.warning(f"Redis unavailable, memory cache disabled: {e}")
            self._redis = None
        return self._redis


memory_manager = MemoryManager()


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=0.2):
            return True
    except OSError:
        return False
