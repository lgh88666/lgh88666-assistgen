"""Smoke test for Retrieval Agent + Recommendation Agent.

Run from backend/llm_backend:
    python scripts/test_recommendation_flow.py "我想买智能门锁和摄像头"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lg_agent.agents.recommendation import create_recommendation_node
from app.lg_agent.agents.retrieval import create_retrieval_node


async def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "我想买智能门锁和摄像头"
    state = {"task": query}

    retrieval_node = create_retrieval_node()
    recommendation_node = create_recommendation_node()

    state.update(await retrieval_node(state))
    state.update(await recommendation_node(state))

    print("retrieval:")
    print(state["retriever_answer"])
    print("\nrecommendation:")
    print(state["recommendation_answer"])


if __name__ == "__main__":
    asyncio.run(main())
