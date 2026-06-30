"""Commerce Agent pipeline used by the HTTP API.

This is the first wired version of the new 5-Agent slice. It keeps the
implementation lightweight and deterministic so the frontend can work even
when Neo4j, Qdrant, Redis, GraphRAG, or an external reranker are offline.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from app.lg_agent.agents.chat import create_chat_node, deterministic_chat_answer
from app.lg_agent.agents.critic import create_critic_node
from app.lg_agent.agents.explanation import create_explanation_node
from app.lg_agent.agents.recommendation import create_recommendation_node
from app.lg_agent.agents.retrieval import create_retrieval_node
from app.lg_agent.agents.supervisor import create_supervisor_node
from app.lg_agent.llm_client import generate_text
from app.lg_agent.memory.context import build_memory_context
from app.lg_agent.observability.trace import trace_event
from app.lg_agent.understanding.query_features import extract_query_features
from app.lg_agent.retrieval.product_loader import load_products


AGENT_SEQUENCE = (
    ("Supervisor", create_supervisor_node),
    ("Retrieval", create_retrieval_node),
    ("Recommendation", create_recommendation_node),
    ("Explanation", create_explanation_node),
)


async def run_commerce_agent(
    query: str,
    *,
    user_id: int = 1,
    conversation_id: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    event_sink: Optional[Callable[[str], None]] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the currently available commerce multi-agent chain.

    If *event_sink* is provided it receives SSE-ready event strings at each
    pipeline stage so the caller can stream progress to the frontend.
    """

    from app.lg_agent.memory import views as memory_views
    from app.lg_agent.observability.stream import sse_event

    async def _emit(event_type: str, payload: Dict[str, Any]) -> None:
        if event_sink is None:
            return
        try:
            await event_sink(sse_event(event_type, payload))
        except Exception:
            pass  # never let SSE failure kill the pipeline

    clean_query = (query or "").strip() or _last_user_message(messages or [])
    msgs = messages or [{"role": "user", "content": clean_query}]

    # ── Memory Layer (before Supervisor) ──
    t0 = time.time()
    await _emit("stage", {"stage": "Memory", "status": "running", "message": "正在分析对话上下文"})
    memory_context = await build_memory_context(clean_query, msgs, session_id=session_id)

    if memory_context.get("needs_compression"):
        await _emit("stage", {"stage": "Memory", "status": "compressing", "message": "正在整理上下文..."})

    await _emit("stage", {
        "stage": "Memory", "status": "compressed" if memory_context.get("needs_compression") else "done",
        "summary": f"effective_query={memory_context['effective_query'][:60]}" if memory_context["memory_used"] else "无需合并历史",
        "duration_ms": round((time.time() - t0) * 1000),
    })

    state: Dict[str, Any] = {
        "task": memory_context["effective_query"],
        "raw_query": memory_context["raw_query"],
        "messages": msgs,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "session_id": session_id,
        "memory_context": memory_context,
        "shopping_state": memory_context["shopping_state"],
        # V3 per-agent memory views.
        "supervisor_memory": memory_views.supervisor_view(memory_context),
        "retrieval_memory": memory_views.retrieval_view(memory_context),
        "recommendation_memory": memory_views.recommendation_view(memory_context),
        "explanation_memory": memory_views.explanation_view(memory_context),
        "critic_memory": memory_views.critic_view(memory_context),
    }
    trace: List[Dict[str, Any]] = []

    trace_event("Memory", {
        "raw_query": memory_context["raw_query"],
        "effective_query": memory_context["effective_query"],
        "memory_used": memory_context["memory_used"],
        "shopping_state": memory_context["shopping_state"] or None,
    })

    # ── Query Understanding Layer (before Supervisor) ──
    t0_qu = time.time()
    await _emit("stage", {"stage": "QueryUnderstanding", "status": "running", "message": "正在分析查询特征"})
    try:
        products = load_products()
    except Exception:
        products = []
    query_features = extract_query_features(
        memory_context["effective_query"],
        products=products,
        shopping_state=memory_context["shopping_state"],
    )
    state["query_features"] = query_features
    await _emit("stage", {
        "stage": "QueryUnderstanding", "status": "done",
        "summary": f"purchase_intent={query_features['has_purchase_intent']}, ranking={query_features.get('ranking_objective')}, categories={query_features.get('product_categories')}",
        "duration_ms": round((time.time() - t0_qu) * 1000),
    })
    trace_event("QueryUnderstanding", {
        "has_purchase_intent": query_features["has_purchase_intent"],
        "ranking_objective": query_features.get("ranking_objective"),
        "product_categories": query_features.get("product_categories"),
        "budget_max": query_features.get("budget_max"),
        "support_intent": query_features.get("support_intent"),
        "intent_signals": query_features.get("intent_signals"),
    })

    t0 = time.time()
    await _emit("stage", {"stage": "Supervisor", "status": "running", "message": "正在理解意图"})
    supervisor = create_supervisor_node()
    state.update(await supervisor(state))
    trace.append(_trace_agent("Supervisor", state))
    decision = state.get("supervisor_decision") or {}
    await _emit("stage", {
        "stage": "Supervisor", "status": "done",
        "summary": f"route={decision.get('route')}, intent={decision.get('intent')}",
        "duration_ms": round((time.time() - t0) * 1000),
    })

    supervisor_decision = state.get("supervisor_decision") or {}
    if supervisor_decision.get("route") == "chat":
        t0 = time.time()
        await _emit("stage", {"stage": "Chat", "status": "running", "message": "正在生成回复"})
        chat_node = create_chat_node()
        state.update(await chat_node(state))
        trace.append(_trace_agent("Chat", state))
        await _emit("stage", {
            "stage": "Chat", "status": "done",
            "summary": "已生成回复",
            "duration_ms": round((time.time() - t0) * 1000),
        })
        result = {
            "answer": state.get("chat_answer") or deterministic_chat_answer(clean_query, supervisor_decision.get("intent")),
            "recommendations": [],
            "retrieval_candidates": [],
            "agent_trace": trace,
            "metadata": {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "supervisor": supervisor_decision,
                "critic": {"approved": True, "score": 1.0, "issues": []},
                "retrieval_source": "",
                "recommendation_source": "",
                "explanation_source": "",
                "chat_source": (state.get("chat_context") or {}).get("source", ""),
                "chat_model": (state.get("chat_context") or {}).get("model", ""),
                "memory_context": state.get("memory_context") or {},
                "query_features": state.get("query_features") or {},
            },
        }
        await _emit("final", result)
        _schedule_session_save(session_id, memory_context, msgs, result)
        return result

    # ── retrieval + recommendation + explanation ──────────────────────
    for agent_name, node_factory in AGENT_SEQUENCE[1:]:
        t0 = time.time()
        await _emit("stage", {"stage": agent_name, "status": "running", "message": _stage_message(agent_name)})
        node = node_factory()
        patch = await node(state)
        state.update(patch)
        trace.append(_trace_agent(agent_name, state))
        await _emit("stage", {
            "stage": agent_name, "status": "done",
            "summary": _trace_agent(agent_name, state).get("summary", ""),
            "duration_ms": round((time.time() - t0) * 1000),
        })

    recommendations = _normalize_items(state.get("recommendation_results") or [])
    retrieval_candidates = _normalize_items((state.get("retrieval_context") or {}).get("candidates") or [])
    draft_answer = _compose_answer(state, retrieval_candidates, recommendations)
    state["draft_answer"] = draft_answer

    t0 = time.time()
    await _emit("stage", {"stage": "Critic", "status": "running", "message": "正在质检回答"})
    critic_node = create_critic_node()
    state.update(await critic_node(state))
    trace.append(_trace_agent("Critic", state))
    answer = await _handle_critic_decision(state, draft_answer, retrieval_candidates, recommendations)
    critic_ctx = state.get("critic_context") or {}
    await _emit("stage", {
        "stage": "Critic", "status": "done",
        "summary": f"decision={critic_ctx.get('decision')}, score={critic_ctx.get('score')}",
        "duration_ms": round((time.time() - t0) * 1000),
    })

    trace_event("Final", {
        "answer_length": len(answer),
        "decision": critic_ctx.get("decision", "unknown"),
    })

    result = {
        "answer": answer,
        "recommendations": recommendations[:6],
        "retrieval_candidates": retrieval_candidates[:8],
        "agent_trace": trace,
        "metadata": {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "supervisor": state.get("supervisor_decision") or {},
            "critic": state.get("critic_context") or {},
            "retrieval_source": _retrieval_source(retrieval_candidates),
            "recommendation_source": (state.get("recommendation_context") or {}).get("source", ""),
            "explanation_source": (state.get("explanation_context") or {}).get("source", ""),
            "final_rewrite_source": (state.get("final_rewrite_context") or {}).get("source", ""),
            "memory_context": state.get("memory_context") or {},
            "query_features": state.get("query_features") or {},
        },
    }
    await _emit("final", result)
    _schedule_session_save(session_id, memory_context, msgs, result)
    return result


def _stage_message(agent_name: str) -> str:
    return {
        "Retrieval": "正在检索商品",
        "Recommendation": "正在生成搭配推荐",
        "Explanation": "正在解释推荐理由",
        "Critic": "正在质检回答",
    }.get(agent_name, f"正在执行{agent_name}")


def _compose_answer(
    state: Dict[str, Any],
    retrieval_candidates: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
) -> str:
    supervisor = state.get("supervisor_decision") or {}
    intent = supervisor.get("intent")
    recommendation_context = state.get("recommendation_context") or {}
    explanation_context = state.get("explanation_context") or {}
    retrieval_context = state.get("retrieval_context") or {}
    constraints = retrieval_context.get("constraints") or {}
    shopping_state = state.get("shopping_state") or {}
    budget = _answer_budget(shopping_state, constraints, state.get("recommendation_context") or {})

    if intent == "chat" and not retrieval_candidates:
        return "你好，我是 AssistGen。你可以告诉我预算、使用场景或已有商品，我会帮你查商品、做搭配推荐，并解释为什么这样配。"

    if intent == "solution_plan":
        return _compose_solution_plan(retrieval_candidates, recommendations, recommendation_context, explanation_context)

    if constraints.get("prefer_low_price"):
        return _compose_low_price_answer(retrieval_candidates, explanation_context)

    display_candidates = _select_display_candidates(retrieval_candidates, budget)
    primary = display_candidates[0] if display_candidates else None
    budget_constrained = budget is not None

    lines = ["为你推荐"]
    if budget_constrained:
        lines.append(f"预算参考：{_money(budget)}以内")
        if primary and _safe_float(primary.get("price")) > float(budget):
            lines.append("说明：当前没有完全落在预算内的强匹配商品，先按“最接近预算 + 相关度”给你排。")

    if display_candidates:
        for index, item in enumerate(display_candidates[:3], start=1):
            budget_note = _budget_note(item, budget)
            lines.append(
                f"{index}. {_stars(item)} {item.get('product_name')}\n"
                f"   {_money(item.get('price'))} | {item.get('category')} | 库存 {item.get('stock')}{budget_note}"
            )
    elif retrieval_candidates:
        top = retrieval_candidates[0]
        lines.append(
            f"1. {_stars(top)} {top.get('product_name')}\n"
            f"   {_money(top.get('price'))} | {top.get('category')} | 库存 {top.get('stock')}"
        )

    show_pairings = recommendations and not (
        budget_constrained and primary and _safe_float(primary.get("price")) > float(budget)
    )
    if show_pairings:
        rec_lines = ["搭配推荐"]
        for item in _filter_recommendations_for_budget(recommendations, budget)[:3]:
            reason = _strip_sentence_end(item.get("reason") or "和当前需求存在场景互补关系")
            rec_lines.append(
                f"- {_stars(item)} {item.get('product_name')}\n"
                f"  {_money(item.get('price'))} | {item.get('category')}\n"
                f"   {reason}"
            )
        lines.extend(rec_lines)

    reason = _compose_grounded_reason(display_candidates[:3], recommendations, budget)
    if reason:
        lines.append("为什么这样推荐")
        lines.append(reason)
    else:
        explanation = _usable_explanation(explanation_context, state.get("explanation_answer"))
        if explanation:
            lines.append("为什么这样推荐")
            lines.append(explanation)

    if intent == "recommendation":
        lines.append("你也可以继续告诉我品牌偏好、功能重点或预算是否能上浮，我再帮你收窄到最合适的 1-2 款。")

    return "\n".join(line for line in lines if line)


async def _maybe_rewrite_answer(
    state: Dict[str, Any],
    draft_answer: str,
    retrieval_candidates: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
) -> str:
    critic = state.get("critic_context") or {}
    if not critic.get("rewrite_needed"):
        return draft_answer

    # Do not rewrite when the critic found factual/constraint issues; keep the
    # grounded draft instead of allowing style rewriting to change facts.
    if critic.get("blocking_issues"):
        return draft_answer

    try:
        # Use higher max_tokens so longer multi-product answers are not cut off
        # mid-sentence (e.g. ending with "在于：").
        rewritten = await generate_text(
            [
                {
                    "role": "system",
                    "content": (
                        "你是智能电商客服的最终话术润色器。\n"
                        "只允许把语气改得更自然、更像真人导购；不能新增商品，不能修改商品名、价格、库存、星级、排序。\n"
                        "保留原来的列表结构和关键信息，不要输出解释过程，不要使用 Markdown 粗体符号。\n"
                        "避免'我根据商品库'、'搭配关系'这类系统腔，改成自然导购表达。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"用户问题：{state.get('task')}\n"
                        f"Critic 语气建议：{critic.get('suggestion')}\n"
                        f"候选商品：{_compact_public_items(retrieval_candidates)}\n"
                        f"推荐商品：{_compact_public_items(recommendations)}\n"
                        f"草稿回答：\n{draft_answer}"
                    ),
                },
            ],
            temperature=0.35,
            max_tokens=1200,
            tags=["commerce_final_rewriter"],
        )
        if _is_truncated(rewritten):
            # LLM output appears cut off — keep the original draft instead of
            # returning an incomplete sentence.
            state["final_rewrite_context"] = {"source": "fallback", "fallback_reason": "truncated_rewrite"}
            return draft_answer
        state["final_rewrite_context"] = {"source": "llm"}
        return rewritten or draft_answer
    except Exception:
        state["final_rewrite_context"] = {"source": "fallback"}
        return draft_answer


async def _handle_critic_decision(
    state: Dict[str, Any],
    draft_answer: str,
    retrieval_candidates: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
) -> str:
    """Route to the right handler based on Critic ``decision``."""
    critic = state.get("critic_context") or {}
    decision = critic.get("decision", "approve")

    if decision == "approve":
        return draft_answer

    if decision == "rewrite_only":
        return await _maybe_rewrite_answer(state, draft_answer, retrieval_candidates, recommendations)

    if decision == "retry_answer_composition":
        return _compose_safe_answer(
            retrieval_candidates,
            recommendations,
            reason=_safe_reason(retrieval_candidates, recommendations),
        )

    if decision == "retry_recommendation":
        budget = (state.get("shopping_state") or {}).get("budget_max")
        return _compose_fallback_answer(
            retrieval_candidates,
            reason=_safe_reason(retrieval_candidates, recommendations),
            budget=budget,
        )

    # "block_and_fallback" or unknown
    return _compose_fallback_answer(
        retrieval_candidates,
        reason="当前暂时无法给出完整的推荐解释，你可以先看看下面这几款，也可以告诉我更多偏好我再帮你细筛。",
    )


def _compose_safe_answer(
    candidates: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
    *,
    reason: str = "",
) -> str:
    """Conservative answer for ``retry_answer_composition``."""
    lines = ["为你推荐"]
    for index, item in enumerate(candidates[:3], start=1):
        lines.append(
            f"{index}. {_stars(item)} {item.get('product_name')}\n"
            f"   {_money(item.get('price'))} | {item.get('category')} | 库存 {item.get('stock')}"
        )
    if reason:
        lines.append(f"\n{reason}")
    lines.append("\n💬 可以告诉我预算、品牌偏好或使用场景，我再帮你收窄。")
    return "\n".join(lines)


def _compose_fallback_answer(
    candidates: List[Dict[str, Any]],
    *,
    reason: str = "",
    budget: float | None = None,
) -> str:
    """Safe fallback for ``retry_recommendation`` / ``block_and_fallback``."""
    lines = ["为你推荐"]
    if budget is not None:
        lines.append(f"预算参考：{_money(budget)}以内")

    display = candidates[:3]
    if budget is not None:
        display = sorted(
            display,
            key=lambda item: (_safe_float(item.get("price")) > budget, _safe_float(item.get("price"))),
        )
    for index, item in enumerate(display, start=1):
        over = " ⚠️ 超预算" if budget is not None and _safe_float(item.get("price")) > budget else ""
        lines.append(
            f"{index}. {_stars(item)} {item.get('product_name')}\n"
            f"   {_money(item.get('price'))} | {item.get('category')} | 库存 {item.get('stock')}{over}"
        )
    if reason:
        lines.append(f"\n{reason}")
    lines.append("\n💬 可以告诉我更多需求细节，我再帮你精确筛选。")
    return "\n".join(lines)


def _schedule_session_save(
    session_id: Optional[str],
    memory_context: Dict[str, Any],
    messages: List[Dict[str, str]],
    result: Dict[str, Any],
) -> None:
    """Persist updated session memory in the background (fire-and-forget)."""
    if not session_id:
        return
    try:
        import asyncio
        from app.lg_agent.memory.store import SessionMemory, get_session_store

        async def _save() -> None:
            store = await get_session_store()
            mem = SessionMemory(session_id)
            # Merge latest shopping state.
            mem.shopping_state = dict(memory_context.get("shopping_state") or {})
            # Keep recent messages for next-turn context extraction.
            mem.messages = list(messages[-6:]) if messages else []
            # Store last recommended product ids for dedup.
            recs = result.get("recommendations") or []
            mem.last_recommended_ids = [
                str(item.get("product_id")) for item in recs[:5] if item.get("product_id")
            ]
            await store.save(mem)

        asyncio.ensure_future(_save())
    except Exception:
        pass  # never let memory save failure break the response


def _safe_reason(
    candidates: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
) -> str:
    """Build a short, safe reason line from available data."""
    parts: list[str] = []
    names = [item.get("product_name", "") for item in (candidates[:2] + recommendations[:2]) if item.get("product_name")]
    if len(names) >= 2:
        parts.append(f"{'、'.join(names[:3])} 在功能上可以互补")
    return "；".join(parts)


def _compact_public_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "product_name": item.get("product_name"),
            "category": item.get("category"),
            "price": item.get("price"),
            "stock": item.get("stock"),
        }
        for item in items[:6]
    ]


def _compose_low_price_answer(
    retrieval_candidates: List[Dict[str, Any]],
    explanation_context: Dict[str, Any],
) -> str:
    lines = ["**低价优选**"]

    for index, item in enumerate(retrieval_candidates[:4], start=1):
        lines.append(
            f"\n{index}. {_stars(item)}  {item.get('product_name')}\n"
            f"   {_money(item.get('price'))}  |  {item.get('category')}  |  库存 {item.get('stock')}"
        )

    lines.append(
        "\n---\n"
        "💬 如果还在意拖地、自清洁、避障或宠物毛发清理，可以告诉我预算，我再帮你筛掉体验明显弱的款。"
    )
    return "\n".join(line for line in lines if line)


def _answer_budget(
    shopping_state: Dict[str, Any],
    constraints: Dict[str, Any],
    recommendation_context: Dict[str, Any],
) -> Optional[float]:
    for value in (
        shopping_state.get("budget_max"),
        constraints.get("price_max"),
        recommendation_context.get("budget"),
    ):
        amount = _safe_float(value, default=None)
        if amount is not None and amount > 0:
            return amount
    return None


def _select_display_candidates(
    candidates: List[Dict[str, Any]],
    budget: Optional[float],
) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    if budget is None:
        return candidates

    def key(item: Dict[str, Any]) -> tuple:
        price = _safe_float(item.get("price"))
        score = _safe_float(item.get("retrieval_score")) or _safe_float(item.get("final_score"))
        over_budget = price > float(budget)
        if over_budget:
            return (1, price - float(budget), price, -score)
        return (0, -score, abs(float(budget) - price), price)

    return sorted(candidates, key=key)


def _filter_recommendations_for_budget(
    recommendations: List[Dict[str, Any]],
    budget: Optional[float],
) -> List[Dict[str, Any]]:
    if budget is None:
        return recommendations
    affordable = [item for item in recommendations if _safe_float(item.get("price")) <= float(budget)]
    return affordable or recommendations


def _budget_note(item: Dict[str, Any], budget: Optional[float]) -> str:
    if budget is None:
        return ""
    price = _safe_float(item.get("price"))
    if price <= float(budget):
        return " | 预算内"
    diff = price - float(budget)
    return f" | 超预算约{_money(diff)}"


def _compose_grounded_reason(
    candidates: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
    budget: Optional[float],
) -> str:
    if not candidates:
        return ""

    first = candidates[0]
    first_price = _safe_float(first.get("price"))
    if budget is not None:
        if first_price <= float(budget):
            return (
                f"这几款优先围绕你的预算筛选，先保证价格不跑偏，再看库存和相关度。"
                f"其中 {first.get('product_name')} 在当前候选里更贴近你的需求。"
            )
        return (
            f"你的预算是 {_money(budget)}以内，但当前强相关商品普遍高于这个区间。"
            f"所以我没有硬推高价款，而是先列出最接近预算的选择；如果预算不能上浮，建议继续降低功能要求或换入门款。"
        )

    if recommendations:
        return "主商品先满足当前购买需求，搭配项只作为可选补充；如果你不想加购，可以直接只看主推清单。"
    return "这几款是按商品相关度、库存和基础性价比综合排序后的候选。"


def _compose_solution_plan(
    retrieval_candidates: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
    recommendation_context: Dict[str, Any],
    explanation_context: Dict[str, Any],
) -> str:
    lines = ["**为你搭配方案**"]

    bundle = recommendation_context.get("estimated_bundle_total") or {}
    bundle_items = bundle.get("items") or []

    if bundle_items:
        total = bundle.get("total")
        budget_note = "，在预算内" if bundle.get("within_budget") else "，可能超预算"

        lines.append("\n**方案组合**")
        for item in bundle_items[:4]:
            lines.append(
                f"\n{_stars(item)}  {item.get('product_name')}\n"
                f"   {_money(item.get('price'))}  |  {item.get('category', '')}"
            )
        lines.append(f"\n📊 预估合计：{_money(total)}{budget_note}")
    elif retrieval_candidates:
        top = retrieval_candidates[0]
        lines.append(
            f"\n**核心单品**\n\n"
            f"{_stars(top)}  {top.get('product_name')}\n"
            f"   {_money(top.get('price'))}  |  {top.get('category', '')}"
        )

    if recommendations:
        selected_ids = {str(item.get("product_id")) for item in bundle_items if item.get("product_id")}
        budget = recommendation_context.get("budget")
        current_total = float(bundle.get("total") or 0)

        add_ons = []
        upgrades = []
        for item in recommendations:
            if str(item.get("product_id")) in selected_ids:
                continue
            price = _safe_float(item.get("price"))
            if budget and current_total + price > float(budget):
                upgrades.append(item)
            else:
                add_ons.append(item)
            if len(add_ons) >= 3:
                break

        if add_ons:
            lines.append("\n**预算内可加购**")
            for item in add_ons:
                lines.append(
                    f"\n{_stars(item)}  {item.get('product_name')}\n"
                    f"   {_money(item.get('price'))}  |  {item.get('category', '')}"
                )

        if upgrades:
            lines.append("\n**预算放宽后可考虑**")
            for item in upgrades[:2]:
                lines.append(
                    f"\n{_stars(item)}  {item.get('product_name')}\n"
                    f"   {_money(item.get('price'))}  |  {item.get('category', '')}"
                )

        reasons = []
        for item in recommendations[:2]:
            if item.get("reason"):
                reasons.append(_strip_sentence_end(str(item["reason"])))
        if reasons:
            lines.append("\n**为什么这样配**\n" + "\n".join(reasons))

    explanation = _usable_explanation(explanation_context, None)
    if explanation and not (recommendations and any(item.get("reason") for item in recommendations[:2])):
        lines.append(f"\n**为什么这样配**\n{explanation}")

    lines.append(
        "\n---\n"
        "💬 也可以告诉我房型、安装条件或生态偏好（小米/华为），我再帮你收敛到最终清单。"
    )
    return "\n".join(line for line in lines if line)


def _usable_explanation(explanation_context: Dict[str, Any], fallback_text: Optional[str]) -> str:
    """Avoid repeating the deterministic fallback; keep real GraphRAG output."""

    if explanation_context.get("source") in {"graphrag", "llm"}:
        return str(explanation_context.get("text") or fallback_text or "").strip()
    return ""


def _money(value: Any) -> str:
    amount = _safe_float(value, default=None)
    if amount is None:
        return "价格待确认"
    if amount.is_integer():
        return f"¥{int(amount)}"
    return f"¥{amount:.2f}"


def _strip_sentence_end(text: str) -> str:
    return str(text).strip().rstrip("。.!！")


def _stars(item: Dict[str, Any]) -> str:
    score = (
        _safe_float(item.get("final_score"), default=None)
        or _safe_float(item.get("graph_score"), default=None)
        or _safe_float(item.get("retrieval_score"), default=None)
        or 0.0
    )
    if score >= 0.85:
        count = 5
    elif score >= 0.70:
        count = 4
    elif score >= 0.55:
        count = 3
    elif score >= 0.40:
        count = 2
    else:
        count = 1
    return "★" * count + "☆" * (5 - count)


def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for item in items:
        normalized.append(
            {
                "product_id": str(item.get("product_id") or item.get("ProductID") or ""),
                "product_name": item.get("product_name") or item.get("ProductName") or "",
                "category": item.get("category") or item.get("CategoryName") or "",
                "price": item.get("price") or item.get("UnitPrice") or 0,
                "stock": item.get("stock") or item.get("UnitsInStock") or 0,
                "supplier": item.get("supplier") or item.get("SupplierName") or "",
                "relation": item.get("relation") or item.get("Relation") or "",
                "reason": item.get("reason") or "",
                "retrieval_score": item.get("retrieval_score") or item.get("RetrievalScore") or 0,
                "graph_score": item.get("graph_score") or item.get("GraphScore") or 0,
                "business_score": item.get("business_score") or 0,
                "final_score": item.get("final_score") or item.get("FinalScore") or 0,
                "source": item.get("source") or item.get("Strategy") or "",
            }
        )
    return normalized


def _trace_agent(agent_name: str, state: Dict[str, Any]) -> Dict[str, Any]:
    if agent_name == "Supervisor":
        decision = state.get("supervisor_decision") or {}
        return {
            "name": agent_name,
            "status": "done",
            "summary": (
                f"intent={decision.get('intent')}, method={decision.get('route_method')}, "
                f"confidence={decision.get('confidence')}, sales={decision.get('sales_intensity')}"
            ),
        }

    if agent_name == "Retrieval":
        candidates = (state.get("retrieval_context") or {}).get("candidates") or []
        return {
            "name": agent_name,
            "status": "done",
            "summary": f"hybrid candidates={len(candidates)}",
        }

    if agent_name == "Chat":
        context = state.get("chat_context") or {}
        return {
            "name": agent_name,
            "status": "done",
            "summary": f"source={context.get('source', '')}, model={context.get('model', '')}",
        }

    if agent_name == "Recommendation":
        context = state.get("recommendation_context") or {}
        items = context.get("items") or []
        return {
            "name": agent_name,
            "status": "done",
            "summary": f"source={context.get('source', '')}, items={len(items)}",
        }

    if agent_name == "Explanation":
        context = state.get("explanation_context") or {}
        return {
            "name": agent_name,
            "status": "done",
            "summary": f"source={context.get('source', '')}",
        }

    critic = state.get("critic_context") or {}
    return {
        "name": agent_name,
        "status": "done" if critic.get("approved", True) else "warning",
        "summary": f"score={critic.get('score')}, issues={len(critic.get('issues') or [])}",
    }


def _retrieval_source(items: List[Dict[str, Any]]) -> str:
    sources = sorted({str(item.get("source")) for item in items if item.get("source")})
    return "+".join(sources)


def _is_truncated(text: str) -> bool:
    """Detect LLM output that appears cut off mid-sentence.

    Returns True when *text* is non-empty and ends with a pattern that suggests
    the generation stopped before completing the thought (e.g. trailing colon,
    common hedge phrases without closure).
    """
    if not text or not text.strip():
        return False
    stripped = text.strip()
    # Trailing colon — almost certainly an incomplete list/item intro.
    if stripped.endswith("："):
        return True
    # Common incomplete sentence endings in Chinese ecommerce answers.
    for marker in ("在于：", "如下：", "包括：", "例如：", "几点：", "主要是：", "特别是："):
        if stripped.endswith(marker):
            return True
    # Dangling connector words.
    for marker in ("另外，", "此外，", "同时，", "而且，", "所以，", "因此，", "不过，", "但是，"):
        if stripped.endswith(marker):
            return True
    return False


def _last_user_message(messages: List[Dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user" and message.get("content"):
            return str(message["content"]).strip()
    return ""
