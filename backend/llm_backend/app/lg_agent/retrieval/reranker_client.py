"""External reranker API client.

Supports:
- ``dashscope`` (gte-rerank-v2, Alibaba Cloud DashScope / MaaS)
- Generic OpenAI-compatible format (fallback)

If no reranker API is configured, the client returns candidates sorted by
fusion_score.  This keeps local development usable before API credentials
are provided.
"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.lg_agent.memory.manager import memory_manager
from app.lg_agent.observability.trace import trace_event

logger = get_logger(service="reranker_client")


class RerankerClient:
    def __init__(self, api_url: str | None = None, api_key: str | None = None):
        self.provider = settings.RERANKER_PROVIDER
        self.api_url = api_url if api_url is not None else settings.RERANKER_API_URL
        self.api_key = api_key if api_key is not None else settings.RERANKER_API_KEY
        self.model = settings.RERANKER_MODEL

    async def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        if not self.api_url:
            trace_event("Reranker", {"method": "fallback", "reason": "no_api_url"})
            return self._fallback(candidates, top_k)

        cache_payload = {
            "query": query,
            "candidate_ids": [str(candidate.get("product_id")) for candidate in candidates],
            "top_k": top_k,
        }
        cache_key = memory_manager.cache_key("rerank", cache_payload)
        cached = await memory_manager.get_json(cache_key)
        if cached:
            return cached

        documents = [
            candidate.get("document_text") or _candidate_text(candidate)
            for candidate in candidates
        ]

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Build provider-specific payload.
        if self.provider == "dashscope":
            payload = {
                "model": self.model,
                "input": {
                    "query": query,
                    "documents": documents,
                },
                "parameters": {"top_n": top_k},
            }
        else:
            # Generic / OpenAI-compatible format.
            payload = {
                "query": query,
                "documents": [
                    {"id": str(c.get("product_id")), "text": documents[i], "metadata": c}
                    for i, c in enumerate(candidates)
                ],
                "top_k": top_k,
            }

        try:
            async with httpx.AsyncClient(timeout=settings.RERANKER_TIMEOUT_SECONDS) as client:
                response = await client.post(self.api_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            # Parse provider-specific response.
            if self.provider == "dashscope":
                scores = _parse_dashscope(data, candidates)
            else:
                scores = _parse_generic(data)

            reranked = _apply_scores(candidates, scores)
            trace_event("Reranker", {
                "method": self.provider,
                "model": self.model,
                "status": "ok",
                "reranked_count": len(reranked),
            })

        except Exception as exc:
            trace_event("Reranker", {
                "method": self.provider or "api",
                "model": self.model,
                "status": "error",
                "fallback": "fusion",
                "error": str(exc)[:100],
            })
            logger.info(f"Reranker API failed, fallback to fusion: {exc}")
            reranked = self._fallback(candidates, top_k)

        final = reranked[:top_k]
        await memory_manager.set_json(cache_key, final, ttl=6 * 60 * 60)
        return final

    @staticmethod
    def _fallback(candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        ranked = []
        for candidate in candidates:
            item = dict(candidate)
            item["rerank_score"] = float(item.get("fusion_score", 0.0))
            item["retrieval_score"] = round(
                0.75 * float(item.get("fusion_score", 0.0))
                + 0.25 * float(item.get("metadata_score", 0.0)),
                4,
            )
            ranked.append(item)
        ranked.sort(key=lambda x: x.get("retrieval_score", 0), reverse=True)
        return ranked[:top_k]


# ── response parsers ────────────────────────────────────────────────────


def _parse_dashscope(data: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, float]:
    """Parse DashScope ``output.results[]`` response.

    Each result has ``index`` and ``relevance_score`` (and optionally
    ``document`` text).  Map the index back to the original candidate.
    """
    results = data.get("output", {}).get("results") or []
    scores: Dict[str, float] = {}
    for result in results:
        idx = int(result.get("index", -1))
        if 0 <= idx < len(candidates):
            pid = str(candidates[idx].get("product_id") or idx)
            score = float(result.get("relevance_score") or result.get("score") or 0.0)
            scores[pid] = score
    return scores


def _parse_generic(data: Dict[str, Any]) -> Dict[str, float]:
    """Parse generic / OpenAI-compatible response."""
    raw_results = data.get("results") or data.get("data") or []
    scores: Dict[str, float] = {}
    for result in raw_results:
        pid = str(result.get("id") or result.get("document_id") or result.get("product_id"))
        if not pid or pid == "None":
            continue
        scores[pid] = float(result.get("score") or result.get("relevance_score") or 0.0)
    return scores


# ── helpers ──────────────────────────────────────────────────────────────


def _apply_scores(candidates: List[Dict[str, Any]], scores: Dict[str, float]) -> List[Dict[str, Any]]:
    reranked = []
    for candidate in candidates:
        pid = str(candidate.get("product_id"))
        item = dict(candidate)
        item["rerank_score"] = float(scores.get(pid, item.get("fusion_score", 0.0)))
        item["retrieval_score"] = round(
            0.65 * item["rerank_score"]
            + 0.25 * float(item.get("fusion_score", 0.0))
            + 0.10 * float(item.get("metadata_score", 0.0)),
            4,
        )
        reranked.append(item)
    reranked.sort(key=lambda x: x.get("retrieval_score", 0), reverse=True)
    return reranked


def _candidate_text(candidate: Dict[str, Any]) -> str:
    return "，".join(
        str(part)
        for part in (
            candidate.get("product_name"),
            candidate.get("category"),
            f"价格{candidate.get('price')}",
            f"库存{candidate.get('stock')}",
            candidate.get("supplier"),
        )
        if part not in ("", None)
    )
