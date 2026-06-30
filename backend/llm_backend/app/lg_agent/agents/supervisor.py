"""Supervisor Agent.

Routes user queries to Chat or Retrieval based on intent routing and
optional Query Understanding features.
"""

from __future__ import annotations

from typing import Any, Dict

from app.lg_agent.intent_router import analyze_query, analyze_query_async
from app.lg_agent.observability.trace import trace_event


def create_supervisor_node():
    async def supervisor(state: Dict[str, Any]) -> Dict[str, Any]:
        query = state.get("task") or _last_user_message(state)
        decision = await analyze_query_async(query)
        shopping_state = state.get("shopping_state") or {}
        query_features = state.get("query_features") or {}

        # ── Query-Understanding override ──────────────────────────────
        # If deterministic Query Understanding detected a clear purchase
        # intent but the classifier routed to chat, fix the route.
        if query_features:
            qf_has_purchase = query_features.get("has_purchase_intent", False)
            qf_support = query_features.get("support_intent", False)
            qf_categories = query_features.get("product_categories") or []
            qf_ranking = query_features.get("ranking_objective")
            qf_need_price = query_features.get("need_price", False)
            qf_need_stock = query_features.get("need_stock", False)

            if qf_support:
                # Override: support/complaint should suppress selling.
                decision["route"] = "chat"
                decision["intent"] = "support"
                decision["recommendation_allowed"] = False
                decision["sales_intensity"] = "none"
                decision["route_method"] = "query_understanding"
                decision["reason"] = "Query Understanding detected support/complaint intent."
            elif decision.get("route") == "chat" and (
                qf_has_purchase or qf_categories or qf_ranking or qf_need_price or qf_need_stock
            ):
                # Override: Query Understanding sees commerce signals that
                # the classifier missed. Route to retrieval.
                decision["route"] = "retrieval"
                if not decision.get("intent") or decision.get("intent") == "chat":
                    decision["intent"] = "recommendation"
                decision["recommendation_allowed"] = True
                if not decision.get("sales_intensity") or decision.get("sales_intensity") == "none":
                    decision["sales_intensity"] = "soft"
                decision["route_method"] = (decision.get("route_method") or "rule") + "+query_understanding"
                decision["reason"] = (
                    decision.get("reason", "") +
                    " Query Understanding detected purchase intent; route overridden to retrieval."
                ).strip()

            # Merge ranking_objective and product_categories into shopping_state
            # so downstream agents can consume them.
            if qf_ranking and not shopping_state.get("ranking_objective"):
                shopping_state["ranking_objective"] = qf_ranking
            if qf_categories and not shopping_state.get("product_categories"):
                shopping_state["product_categories"] = qf_categories
            if qf_need_price:
                shopping_state["need_price"] = True
            if qf_need_stock:
                shopping_state["need_stock"] = True

            state["shopping_state"] = shopping_state

        trace_event("Supervisor", {
            "route": decision.get("route"),
            "intent": decision.get("intent"),
            "method": decision.get("route_method"),
            "confidence": decision.get("confidence"),
            "sales": decision.get("sales_intensity"),
            "ranking_objective": shopping_state.get("ranking_objective"),
            "product_categories": shopping_state.get("product_categories"),
            "qf_override": bool(query_features and query_features.get("has_purchase_intent") and decision.get("route") == "retrieval"),
        })

        return {
            "supervisor_decision": decision,
            "retriever_task": query,
            "steps": ["supervisor"],
        }

    return supervisor


def _last_user_message(state: Dict[str, Any]) -> str:
    messages = state.get("messages", [])
    if not messages:
        return ""
    last = messages[-1]
    return getattr(last, "content", str(last))
