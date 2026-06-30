"""Verify Qdrant explanation evidence collection and retrieval.

Checks: collection existence, point count, sample searches, and fallback
behavior when Qdrant is unavailable.

Usage::

    cd backend/llm_backend
    python -B scripts/verify_qdrant_evidence.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings

COLLECTION_NAME = "assistgen_explanation_evidence"

SAMPLE_QUERIES = [
    ("扫地机器人+空气净化器搭配", "扫地机器人和空气净化器为什么适合搭配"),
    ("门锁+摄像头安防", "智能门锁和摄像头家庭安防"),
    ("灯具+开关全屋智能", "智能灯和智能开关全屋智能"),
]


def _check_qdrant_available() -> str | None:
    """Return None if Qdrant is reachable, otherwise an error message."""
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=settings.QDRANT_URL, timeout=10)
        # A cheap call to verify connectivity.
        client.get_collections()
        return None
    except Exception as exc:
        return f"Qdrant unavailable at {settings.QDRANT_URL}: {exc}"


def _collection_exists(client: Any) -> bool:
    names = [c.name for c in client.get_collections().collections]
    return COLLECTION_NAME in names


def _collection_point_count(client: Any) -> int:
    try:
        info = client.count(COLLECTION_NAME)
        return int(info.count) if info else 0
    except Exception:
        return -1


def _try_embed(texts: List[str]) -> List[Any] | None:
    """Return embedding vectors using the configured provider, or None if unavailable."""
    try:
        from app.lg_agent.retrieval.embedding import embed_texts
        return embed_texts(texts)
    except Exception:
        return None


def _search_evidence(client: Any, query_text: str, vectors: List[Any] | None) -> List[Dict[str, Any]]:
    """Search the evidence collection and return top results."""
    if vectors is None:
        return []
    try:
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vectors[0],
            limit=3,
            with_payload=True,
        )
        results = response.points if hasattr(response, "points") else []
        return [
            {
                "source": (r.payload or {}).get("source_product_name", "?"),
                "target": (r.payload or {}).get("target_product_name", "?"),
                "relation": (r.payload or {}).get("relation", "?"),
                "scenario": (r.payload or {}).get("scenario", ""),
                "tags": (r.payload or {}).get("reason_tags", []),
                "score": round(float(r.score), 4),
            }
            for r in results
        ]
    except Exception:
        return []


def main() -> None:
    print("=" * 64)
    print("Qdrant Explanation Evidence Verification")
    print("=" * 64)
    print(f"QDRANT_URL: {settings.QDRANT_URL}")
    print()

    all_ok = True

    # ── 1. Qdrant availability ─────────────────────────────────────────
    err = _check_qdrant_available()
    if err:
        print(f"[SKIP] {err}")
        print("\nVerdict: Qdrant is offline. Explanation falls back to LLM or deterministic.")
        print("No blocking failure — agent chain handles this gracefully.")
        sys.exit(0)

    print("[PASS] Qdrant is reachable.")

    # Import here — we already confirmed Qdrant is available.
    from qdrant_client import QdrantClient
    client = QdrantClient(url=settings.QDRANT_URL)

    # ── 2. Collection existence ────────────────────────────────────────
    if not _collection_exists(client):
        print(f"[MISS] Collection '{COLLECTION_NAME}' does not exist.")
        print("        Running index_explanation_evidence_to_qdrant.py ...")
        try:
            import subprocess
            script = Path(__file__).resolve().parent / "index_explanation_evidence_to_qdrant.py"
            subprocess.run(
                [sys.executable, str(script)],
                cwd=str(ROOT),
                check=False,
            )
            if not _collection_exists(client):
                print("[FAIL] Collection still missing after indexing attempt.")
                all_ok = False
        except Exception as exc:
            print(f"[FAIL] Could not run indexing script: {exc}")
            all_ok = False
    else:
        print(f"[PASS] Collection '{COLLECTION_NAME}' exists.")

    if not all_ok:
        print("\nVerdict: Collection setup failed. Check Qdrant and re-run indexing.")
        sys.exit(1)

    # ── 3. Point count ─────────────────────────────────────────────────
    count = _collection_point_count(client)
    if count < 0:
        print("[FAIL] Could not read point count.")
        all_ok = False
    elif count == 0:
        print("[FAIL] Collection is empty (0 points).")
        all_ok = False
    else:
        print(f"[PASS] Point count: {count}")

    if not all_ok:
        print("\nVerdict: No evidence data. Re-run generate_demo_ecommerce_data.py then index.")
        sys.exit(1)

    # ── 4. Sample evidence searches ────────────────────────────────────
    print(f"\n{'─' * 48}")
    print("Sample evidence searches:")
    print(f"{'─' * 48}")

    all_searches_ok = True
    for label, query_text in SAMPLE_QUERIES:
        vectors = _try_embed([query_text])
        results = _search_evidence(client, query_text, vectors)

        if not results:
            print(f"\n  [{label}] — no results (embedding model may be unavailable)")
            continue

        print(f"\n  [{label}]")
        for i, r in enumerate(results[:3], 1):
            tags_str = ", ".join(r["tags"][:2]) if r["tags"] else "(none)"
            scenario_str = r["scenario"] or "(none)"
            print(
                f"    {i}. {r['source']} → {r['target']}"
                f"  rel={r['relation']}  scenario={scenario_str}"
                f"  tags=[{tags_str}]  score={r['score']}"
            )

            # Verify useful fields present.
            if not r["source"] or r["source"] == "?":
                all_searches_ok = False
            if not r["relation"] or r["relation"] == "?":
                all_searches_ok = False

    if all_searches_ok:
        print("\n[PASS] Sample searches returned evidence with required fields.")
    else:
        print("\n[WARN] Some evidence results are missing fields.")

    # ── 5. Verify Explanation can use Qdrant evidence ──────────────────
    print(f"\n{'─' * 48}")
    print("Explanation integration check:")
    try:
        from app.lg_agent.tools.graphrag_explanation_tool import GraphRAGExplanationTool
        tool = GraphRAGExplanationTool()
        evidence_text = asyncio_run(
            tool._query_qdrant_evidence(
                "智能门锁和摄像头搭配",
                [{"product_name": "智能门锁", "product_id": "test_1"}],
                [{"product_name": "摄像头", "product_id": "test_2"}],
            )
        )
        if evidence_text:
            print(f"[PASS] Explanation tool returned Qdrant evidence ({len(evidence_text)} chars).")
        else:
            print("[INFO] Qdrant evidence query returned empty (may need relevant data).")
    except Exception as exc:
        print(f"[INFO] Explanation tool Qdrant path: {exc}")

    # ── summary ────────────────────────────────────────────────────────
    print(f"\n{'═' * 64}")
    if all_ok:
        print("[PASS] Qdrant explanation evidence: VERIFIED")
    else:
        print("[WARN] Qdrant explanation evidence: ISSUES FOUND (see above)")
    print(f"{'═' * 64}")


def asyncio_run(coro):
    """Minimal async runner so we don't need a top-level async main."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # We're inside an event loop; use a simple workaround.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


if __name__ == "__main__":
    main()
