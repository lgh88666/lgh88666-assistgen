"""Smoke test for the current agent slice.

Run from backend/llm_backend:
    python scripts/test_agent_slice.py "我想买智能门锁和摄像头"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lg_agent.agents.critic import create_critic_node
from app.lg_agent.agents.explanation import create_explanation_node
from app.lg_agent.agents.recommendation import create_recommendation_node
from app.lg_agent.agents.retrieval import create_retrieval_node
from app.lg_agent.agents.supervisor import create_supervisor_node


async def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "我想买智能门锁和摄像头"
    state = {"task": query}

    for node_factory in (
        create_supervisor_node,
        create_retrieval_node,
        create_recommendation_node,
        create_explanation_node,
        create_critic_node,
    ):
        state.update(await node_factory()(state))

    print("supervisor:")
    print(state["supervisor_decision"])
    print()
    print("retrieval:")
    print(state["retriever_answer"])
    print("\nrecommendation:")
    print(state["recommendation_answer"])
    print("\nexplanation:")
    print(state["explanation_answer"])
    print("\ncritic:")
    print(state["critic_context"])


if __name__ == "__main__":
    asyncio.run(main())
