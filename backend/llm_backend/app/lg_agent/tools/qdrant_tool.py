"""Qdrant dense retrieval tool for product facts."""

from __future__ import annotations

import socket
from urllib.parse import urlparse
from typing import Any, Dict, List

from app.core.config import settings
from app.lg_agent.retrieval.embedding import embed_query


class QdrantProductRetriever:
    """Dense retriever backed by Qdrant."""

    def __init__(self, url: str | None = None, collection: str | None = None):
        self.url = url or settings.QDRANT_URL
        self.collection = collection or settings.QDRANT_COLLECTION_PRODUCTS
        self.client = None
        self._available: bool | None = None

    def search(self, query: str, top_k: int | None = None) -> List[Dict[str, Any]]:
        if not self._collection_available():
            return []

        vector = embed_query(query)
        limit = top_k or settings.RETRIEVAL_DENSE_TOP_K

        try:
            response = self.client.query_points(
                collection_name=self.collection,
                query=vector,
                limit=limit,
                with_payload=True,
            )
            points = response.points if hasattr(response, "points") else []
        except Exception:
            return []

        results = []
        for point in points:
            payload = dict(point.payload or {})
            payload["product_id"] = str(payload.get("product_id") or point.id)
            payload["dense_score"] = float(point.score)
            payload["source"] = "qdrant"
            results.append(payload)
        return results

    def _collection_available(self) -> bool:
        if self._available is not None:
            return self._available
        if not _is_http_port_open(self.url):
            self._available = False
            return False
        if self.client is None:
            try:
                from qdrant_client import QdrantClient

                self.client = QdrantClient(url=self.url, timeout=2.0, check_compatibility=False)
            except ImportError:
                self._available = False
                return False
        try:
            self.client.get_collection(self.collection)
            self._available = True
        except Exception:
            self._available = False
        return self._available


def _is_http_port_open(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False
