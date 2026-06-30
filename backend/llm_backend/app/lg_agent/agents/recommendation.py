"""Recommendation Agent.

This Agent decides recommendation candidates from retrieved product facts. It
does not call an LLM; emotion and timing decisions can be added by Supervisor.
"""

from __future__ import annotations

from typing import Any, Dict

from app.core.logger import get_logger
from app.lg_agent.observability.trace import trace_event
from app.lg_agent.tools.recommendation_tool import KGRecommendationTool

logger = get_logger(service="recommendation_agent")


def create_recommendation_node(tool: KGRecommendationTool | None = None):
    recommendation_tool = tool or KGRecommendationTool()

    async def recommendation(state: Dict[str, Any]) -> Dict[str, Any]:
        query = state.get("retriever_task") or state.get("task") or _last_user_message(state)
        retrieval_context = state.get("retrieval_context") or {}
        retrieval_candidates = retrieval_context.get("candidates") or []
        supervisor_decision = state.get("supervisor_decision") or {}
        shopping_state = state.get("shopping_state") or {}

        if supervisor_decision.get("recommendation_allowed") is False:
            return {
                "recommendation_context": {"source": "gate", "anchors": [], "items": [], "summary": "当前场景不主动推荐商品。"},
                "recommendation_results": [],
                "recommendation_answer": "当前场景不主动推荐商品。",
                "steps": ["recommendation"],
            }

        logger.info(f"Recommendation Agent: build recommendations for {query[:80]}")
        result = recommendation_tool.recommend(query, retrieval_candidates, shopping_state=shopping_state)

        trace_event("Recommendation", {
            "source": result.get("source"),
            "mode": "bundle" if (result.get("estimated_bundle_total") or {}).get("items") else "single",
            "relation_count": len(result.get("items") or []),
            "recommended_products": result.get("items") or [],
            "budget": result.get("budget"),
        })

        return {
            "recommendation_context": result,
            "recommendation_results": result["items"],
            "recommendation_answer": result["summary"],
            "steps": ["recommendation"],
        }

    return recommendation


def _last_user_message(state: Dict[str, Any]) -> str:
    messages = state.get("messages", [])
    if not messages:
        return ""
    last = messages[-1]
    return getattr(last, "content", str(last))
