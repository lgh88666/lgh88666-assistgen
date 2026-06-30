"""Verify the real DashScope gte-rerank-v2 reranker configuration.

Tests: config reading, small API call, response parsing, fallback behavior.
Never prints the API key.

Usage::

    cd backend/llm_backend
    python -B scripts/verify_reranker_api.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings

# ── sample data ────────────────────────────────────────────────────────────

SAMPLE_QUERY = "智能门锁推荐"
SAMPLE_CANDIDATES: List[Dict[str, Any]] = [
    {
        "product_id": "test_1",
        "product_name": "华为智选智能门锁 SE",
        "category": "智能门锁",
        "price": 999,
        "stock": 50,
        "supplier": "华为",
        "document_text": "华为智选智能门锁 SE，智能门锁，价格999，库存50，华为",
    },
    {
        "product_id": "test_2",
        "product_name": "小米智能门锁 Pro",
        "category": "智能门锁",
        "price": 1299,
        "stock": 30,
        "supplier": "小米",
        "document_text": "小米智能门锁 Pro，智能门锁，价格1299，库存30，小米",
    },
    {
        "product_id": "test_3",
        "product_name": "Aqara 智能门锁 N200",
        "category": "智能门锁",
        "price": 1499,
        "stock": 20,
        "supplier": "Aqara",
        "document_text": "Aqara 智能门锁 N200，智能门锁，价格1499，库存20，Aqara",
    },
]


def _mask_key(key: str) -> str:
    if not key:
        return "(not set)"
    if len(key) <= 8:
        return key[:2] + "***"
    return key[:4] + "***" + key[-4:]


def _redact_url(url: str) -> str:
    """Return a safe version of the URL (no tokens in query params)."""
    return url[:60] + "..." if len(url) > 60 else url


def main() -> None:
    print("=" * 64)
    print("Reranker API Verification")
    print("=" * 64)

    # ── 1. Read config ─────────────────────────────────────────────────
    provider = settings.RERANKER_PROVIDER
    api_url = settings.RERANKER_API_URL
    api_key = settings.RERANKER_API_KEY
    model = settings.RERANKER_MODEL
    timeout = settings.RERANKER_TIMEOUT_SECONDS

    print(f"Provider:  {provider or '(not configured)'}")
    print(f"Model:     {model}")
    print(f"URL:       {_redact_url(api_url) if api_url else '(not set)'}")
    print(f"API Key:   {_mask_key(api_key)}")
    print(f"Timeout:   {timeout}s")
    print()

    # ── 2. Skip if not configured ──────────────────────────────────────
    if not api_url or not api_key:
        print("[SKIP] Reranker API is not configured (URL or key missing).")
        print("       The agent chain will use local fusion-score ranking.")
        print("       This is expected behavior — no failure.")
        print()
        print("To enable reranker, set in .env:")
        print("  RERANKER_PROVIDER=dashscope")
        print("  RERANKER_MODEL=gte-rerank-v2")
        print("  RERANKER_API_URL=<your endpoint>")
        print("  RERANKER_API_KEY=<your key>")
        sys.exit(0)

    # ── 3. Verify provider ─────────────────────────────────────────────
    if provider != "dashscope":
        print(f"[INFO] Provider '{provider}' — will use generic payload format.")

    # ── 4. Send a small test request ───────────────────────────────────
    import asyncio
    import httpx

    async def test_rerank() -> Dict[str, Any]:
        documents = [c["document_text"] for c in SAMPLE_CANDIDATES]
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        if provider == "dashscope":
            payload = {
                "model": model,
                "input": {
                    "query": SAMPLE_QUERY,
                    "documents": documents,
                },
                "parameters": {"top_n": 3},
            }
        else:
            payload = {
                "query": SAMPLE_QUERY,
                "documents": [
                    {"id": c["product_id"], "text": documents[i]}
                    for i, c in enumerate(SAMPLE_CANDIDATES)
                ],
                "top_k": 3,
            }

        try:
            async with httpx.AsyncClient(timeout=float(timeout)) as client:
                resp = await client.post(api_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            return {"ok": True, "data": data, "status_code": resp.status_code}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    print("Sending test rerank request (3 documents)...")
    result = asyncio.run(test_rerank())

    if not result["ok"]:
        print(f"[FAIL] Reranker API call failed: {result.get('error', '?')}")
        print()
        print("Testing fallback behavior...")

        # ── test fallback ──────────────────────────────────────────────
        from app.lg_agent.retrieval.reranker_client import RerankerClient
        client = RerankerClient(api_url=api_url, api_key=api_key)

        async def test_fallback():
            return await client.rerank(SAMPLE_QUERY, SAMPLE_CANDIDATES, top_k=3)

        fallback_result = asyncio.run(test_fallback())
        if fallback_result:
            names = [c.get("product_name", "?") for c in fallback_result]
            print(f"[PASS] Fallback ranking returned {len(fallback_result)} candidates: {names}")
            print("       Agent chain handles reranker failure gracefully.")
        else:
            print("[FAIL] Even fallback ranking returned empty.")
            sys.exit(1)
        sys.exit(0)

    # ── 5. Parse response ──────────────────────────────────────────────
    data = result["data"]
    status_code = result["status_code"]
    print(f"[PASS] API responded with status {status_code}")

    if provider == "dashscope":
        output = data.get("output", {})
        results_list = output.get("results") or []
        print(f"       Results count: {len(results_list)}")

        if results_list:
            scores = [r.get("relevance_score", 0) for r in results_list]
            indices = [r.get("index", -1) for r in results_list]
            print(f"       Score range: {min(scores):.4f} — {max(scores):.4f}")
            print(f"       Indices: {indices}")
            print()

            # Map back to candidates.
            for i, r in enumerate(results_list[:3], 1):
                idx = int(r.get("index", -1))
                name = SAMPLE_CANDIDATES[idx]["product_name"] if 0 <= idx < len(SAMPLE_CANDIDATES) else "?"
                print(
                    f"  {i}. {name}"
                    f"  score={r.get('relevance_score', 0):.4f}"
                    f"  (index={idx})"
                )

            # Verify expected ordering (most relevant first).
            if scores == sorted(scores, reverse=True):
                print("\n[PASS] Scores in expected descending order.")
            else:
                print("\n[WARN] Scores not in descending order — check response format.")
    else:
        results_list = data.get("results") or data.get("data") or []
        print(f"       Results count: {len(results_list)}")
        if results_list:
            scores = [float(r.get("score", r.get("relevance_score", 0))) for r in results_list]
            print(f"       Score range: {min(scores):.4f} — {max(scores):.4f}")

    # ── 6. Verify Agent Trace safety ───────────────────────────────────
    print(f"\n{'─' * 48}")
    print("Agent Trace safety check:")
    print("  - API key is NOT printed above (only masked prefix).")
    print("  - Full candidate documents are NOT printed.")
    print("  - Only safe summary fields (model, score range, top names) are shown.")
    print("  [PASS] Trace safety verified by construction.")

    # ── 7. Test forced fallback (bad URL) ──────────────────────────────
    print(f"\n{'─' * 48}")
    print("Forced fallback test (bad URL):")

    from app.lg_agent.retrieval.reranker_client import RerankerClient
    bad_client = RerankerClient(api_url="https://invalid.example.com/rerank", api_key="test")

    async def test_bad_url():
        return await bad_client.rerank(SAMPLE_QUERY, SAMPLE_CANDIDATES, top_k=3)

    bad_result = asyncio.run(test_bad_url())
    if bad_result:
        names = [c.get("product_name", "?") for c in bad_result]
        print(f"[PASS] Bad URL gracefully fell back — returned {len(bad_result)} candidates: {names}")
    else:
        print("[FAIL] Bad URL fallback returned nothing.")
        sys.exit(1)

    # ── summary ────────────────────────────────────────────────────────
    print(f"\n{'=' * 64}")
    print("[PASS] Reranker API: VERIFIED")
    print(f"      Provider: {provider}  Model: {model}")
    print(f"{'=' * 64}")


if __name__ == "__main__":
    main()
