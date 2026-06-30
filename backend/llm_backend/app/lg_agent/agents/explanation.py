"""Explanation Agent.

GraphRAG participates in every answer through GraphRAGExplanationTool. The
tool itself is responsible for safe fallback when GraphRAG is unavailable.
"""

from __future__ import annotations

from typing import Any, Dict

from app.core.logger import get_logger
from app.lg_agent.observability.trace import trace_event
from app.lg_agent.tools.graphrag_explanation_tool import GraphRAGExplanationTool

logger = get_logger(service="explanation_agent")


def create_explanation_node(tool: GraphRAGExplanationTool | None = None):
    explanation_tool = tool or GraphRAGExplanationTool()

    async def explanation(state: Dict[str, Any]) -> Dict[str, Any]:
        query = state.get("retriever_task") or state.get("task") or _last_user_message(state)
        retrieval_context = state.get("retrieval_context") or {}
        retrieval_candidates = retrieval_context.get("candidates") or []
        recommendations = state.get("recommendation_results") or []

        logger.info(f"Explanation Agent: explain answer for {query[:80]}")
        result = await explanation_tool.explain(query, retrieval_candidates, recommendations)

        # Collect product names mentioned in the explanation for Critic consistency checks.
        all_names = {
            item.get("product_name") or ""
            for item in retrieval_candidates + recommendations
        }
        mentioned = [n for n in all_names if n and n in (result.get("text") or "")]
        if mentioned:
            result["mentioned_product_names"] = mentioned

        trace_event("Explanation", {
            "source": result.get("source"),
            "used_graphrag": result.get("source") == "graphrag",
            "used_qdrant_evidence": result.get("source") == "lightweight_graphrag_qdrant",
            "fallback_reason": result.get("fallback_reason"),
        })

        return {
            "explanation_context": result,
            "explanation_answer": result["text"],
            "steps": ["explanation"],
        }

    return explanation


def _last_user_message(state: Dict[str, Any]) -> str:
    messages = state.get("messages", [])
    if not messages:
        return ""
    last = messages[-1]
    return getattr(last, "content", str(last))
