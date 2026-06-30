"""Smoke test for the Hybrid Product RAG pipeline.

Run from backend/llm_backend:
    python scripts/test_hybrid_retrieval.py "我想给爸妈买一套智能安防"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lg_agent.retrieval.hybrid_pipeline import HybridProductRetriever


async def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "我想买智能门锁和摄像头"
    retriever = HybridProductRetriever()
    result = await retriever.retrieve(query)

    print(f"query: {result['query']}")
    print(f"rewritten_query: {result['rewritten_query']}")
    print("candidates:")
    for item in result["candidates"]:
        print(
            "- {name} | {category} | price={price} | stock={stock} | score={score}".format(
                name=item.get("product_name"),
                category=item.get("category"),
                price=item.get("price"),
                stock=item.get("stock"),
                score=item.get("retrieval_score"),
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
