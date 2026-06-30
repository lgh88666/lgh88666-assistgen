"""Critic Agent — Final Answer Quality Gate.

Upgraded from a tone-only reviewer to a real gate that can detect and block
budget mismatch, primary/explanation inconsistency, recommendation strategy
mismatch, and format/readability problems.

Design:
- Deterministic checks are the foundation (always run).
- LLM review supplements tone and helpfulness but cannot be the sole gate.
- ``decision`` drives pipeline behaviour downstream.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.core.logger import get_logger
from app.lg_agent.llm_client import generate_text, llm_config_label
from app.lg_agent.observability.trace import trace_event

logger = get_logger(service="critic_agent")

# ── decision types ──────────────────────────────────────────────────────

Decision = str  # "approve" | "rewrite_only" | "retry_answer_composition" |
#                  "retry_recommendation" | "block_and_fallback"


def create_critic_node():
    async def critic(state: Dict[str, Any]) -> Dict[str, Any]:
        fallback = _deterministic_review(state)
        try:
            llm_review = await _llm_review(state)
            # LLM review can supplement but deterministic blocking issues
            # always take priority.
            review = {**fallback, **llm_review, "source": "llm", "model": llm_config_label()}
            if fallback.get("blocking_issues"):
                review["blocking_issues"] = list(
                    dict.fromkeys((review.get("blocking_issues") or []) + fallback["blocking_issues"])
                )
                review["decision"] = fallback["decision"]
                review["approved"] = False
                review["rewrite_needed"] = False
                review["retry_needed"] = True
        except Exception as exc:
            logger.info(f"Critic Agent LLM JSON unavailable, use deterministic review: {exc}")
            review = {**fallback, "source": "fallback", "llm_error": str(exc)[:200]}

        trace_event("Critic", {
            "source": review.get("source"),
            "decision": review.get("decision"),
            "approved": review.get("approved"),
            "score": review.get("score"),
            "tone_score": review.get("tone_score"),
            "rewrite_needed": review.get("rewrite_needed"),
            "blocking_issues": review.get("blocking_issues") or [],
            "issues": review.get("issues") or [],
        })

        return {
            "critic_context": review,
            "steps": ["critic"],
        }

    return critic


# ── LLM review (supplemental) ───────────────────────────────────────────


async def _llm_review(state: Dict[str, Any]) -> Dict[str, Any]:
    retrieval_candidates = (state.get("retrieval_context") or {}).get("candidates") or []
    recommendations = state.get("recommendation_results") or []
    explanation = state.get("explanation_answer") or ""
    draft_answer = state.get("draft_answer") or ""

    prompt = {
        "user_query": state.get("task") or state.get("retriever_task"),
        "supervisor": state.get("supervisor_decision") or {},
        "retrieval_candidates": _compact_items(retrieval_candidates),
        "recommendations": _compact_items(recommendations),
        "explanation": explanation,
        "draft_answer": draft_answer,
    }
    response = await generate_text(
        [
            {
                "role": "system",
                "content": (
                    "Return valid JSON only. No markdown. No prose.\n"
                    "Schema: {\"approved\": boolean, \"score\": number, \"issues\": string[], "
                    "\"blocking_issues\": string[], \"suggestion\": string, \"tone_score\": number, "
                    "\"tone_issues\": string[], \"rewrite_needed\": boolean}.\n"
                    "You review a Chinese ecommerce agent draft. Check factual grounding, "
                    "recommendation quality, helpfulness, and human tone. "
                    "If wording is robotic but facts are fine, set rewrite_needed=true."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        temperature=0.1,
        max_tokens=400,
        tags=["commerce_critic_agent"],
    )
    data = _parse_json(response)
    return {
        "approved": bool(data.get("approved", True)),
        "score": round(float(data.get("score", 0.8)), 2),
        "issues": list(data.get("issues") or []),
        "blocking_issues": list(data.get("blocking_issues") or []),
        "suggestion": str(data.get("suggestion") or ""),
        "tone_score": round(float(data.get("tone_score", 0.8)), 2),
        "tone_issues": list(data.get("tone_issues") or []),
        "rewrite_needed": bool(data.get("rewrite_needed", False)),
    }


# ── deterministic review (the foundation) ───────────────────────────────


def _deterministic_review(state: Dict[str, Any]) -> Dict[str, Any]:
    """Run all deterministic quality checks and produce a decision."""

    # ── gather context ───────────────────────────────────────────────
    draft_answer = state.get("draft_answer") or ""
    shopping_state = state.get("shopping_state") or {}
    retrieval_context = state.get("retrieval_context") or {}
    retrieval_candidates = retrieval_context.get("candidates") or []
    constraints = retrieval_context.get("constraints") or {}
    recommendations = state.get("recommendation_results") or []
    explanation = state.get("explanation_answer") or ""
    explanation_context = state.get("explanation_context") or {}
    recommendation_context = state.get("recommendation_context") or {}
    supervisor = state.get("supervisor_decision") or {}

    # ── build product-name index ─────────────────────────────────────
    all_candidate_names: set[str] = set()
    for item in retrieval_candidates + recommendations:
        name = item.get("product_name") or ""
        if name:
            all_candidate_names.add(name)

    # Product names that appear in the explanation text.
    explained_names: set[str] = set(explanation_context.get("mentioned_product_names") or [])
    if not explained_names and explanation:
        for name in all_candidate_names:
            if name and name in explanation:
                explained_names.add(name)

    # Product names that appear in the draft answer body.
    draft_names = _names_in_text(draft_answer, all_candidate_names)

    # ── state ────────────────────────────────────────────────────────
    issues: List[str] = []
    blocking_issues: List[str] = []
    tone_issues: List[str] = []
    scores = {"factual": 1.0, "budget": 1.0, "consistency": 1.0, "strategy": 1.0, "format": 1.0, "tone": 1.0}

    # ── 1. budget mismatch ───────────────────────────────────────────
    budget = shopping_state.get("budget_max")
    if budget is None:
        budget = constraints.get("price_max")
    budget = float(budget) if budget is not None else None

    if budget and draft_names:
        primary_name = next(iter(draft_names))
        primary = _find_product(primary_name, retrieval_candidates + recommendations)
        if primary:
            primary_price = _safe_float(primary.get("price"))
            if primary_price > budget * 1.2:
                # Allow if the answer explicitly acknowledges the budget issue.
                if "超预算" not in draft_answer and "超过预算" not in draft_answer and "预算" not in draft_answer.lower():
                    blocking_issues.append("budget_mismatch")
                    scores["budget"] = 0.3

    # ── 2. primary / explanation consistency ─────────────────────────
    if draft_names and explained_names:
        overlap = draft_names & explained_names
        if len(overlap) == 0 and len(explained_names) >= 1:
            blocking_issues.append("primary_explanation_mismatch")
            scores["consistency"] = 0.3
    if explained_names and all_candidate_names:
        unsupported = explained_names - all_candidate_names
        if unsupported:
            issues.append("unsupported_explanation_product")
            scores["consistency"] = min(scores["consistency"], 0.5)

    # ── 3. recommendation strategy mismatch ──────────────────────────
    ranking_obj = shopping_state.get("ranking_objective", "")
    task = state.get("task") or state.get("raw_query") or ""
    is_low_price = ranking_obj == "lowest_price" or any(
        w in (task or "") for w in ("最便宜", "低价", "便宜", "实惠", "入门款")
    )
    if is_low_price and recommendations and draft_answer:
        # If the recommendations section is large relative to the main section,
        # the add-ons may be dominating a low-price query.
        rec_start = draft_answer.find("搭配推荐")
        if rec_start >= 0:
            before_rec = draft_answer[:rec_start]
            after_rec = draft_answer[rec_start:]
            if len(after_rec) > len(before_rec) * 0.6:
                blocking_issues.append("recommendation_strategy_mismatch")
                scores["strategy"] = 0.4

    # ── 4. format / readability ──────────────────────────────────────
    lines = [ln for ln in draft_answer.split("\n") if ln.strip()]
    if len(lines) < 3:
        blocking_issues.append("format_readability_poor")
        scores["format"] = 0.3
    elif any(len(ln) > 200 for ln in lines):
        issues.append("format_readability_poor")
        scores["format"] = 0.6

    # ── 5. exposes internal score ────────────────────────────────────
    if "推荐分" in draft_answer or "retrieval_score" in draft_answer or "final_score" in draft_answer:
        blocking_issues.append("exposes_internal_score")
        scores["factual"] = 0.4

    # ── 6. robotic tone ──────────────────────────────────────────────
    for signal in ("我根据商品库", "搭配关系", "根据知识图谱"):
        if signal in draft_answer:
            tone_issues.append("robotic_tone")
            scores["tone"] = 0.6
            break

    # ── 7. generic issues ────────────────────────────────────────────
    if not retrieval_candidates:
        issues.append("missing_retrieval_candidates")
    if not explanation:
        issues.append("missing_explanation")

    # ── decision logic ───────────────────────────────────────────────
    score = round(sum(scores.values()) / len(scores), 2)
    tone_score = scores["tone"]
    approved = len(blocking_issues) == 0

    if not blocking_issues and not tone_issues:
        decision: Decision = "approve"
    elif not blocking_issues and tone_issues:
        decision = "rewrite_only"
    elif blocking_issues and all(
        b in ("format_readability_poor", "exposes_internal_score") for b in blocking_issues
    ):
        decision = "retry_answer_composition"
    elif any(b in ("budget_mismatch", "primary_explanation_mismatch", "recommendation_strategy_mismatch")
             for b in blocking_issues):
        decision = "retry_recommendation"
    else:
        decision = "block_and_fallback"

    return {
        "approved": approved,
        "decision": decision,
        "score": score,
        "scores": scores,
        "issues": issues,
        "blocking_issues": blocking_issues,
        "suggestion": _build_suggestion(blocking_issues, issues, tone_issues),
        "tone_score": tone_score,
        "tone_issues": tone_issues,
        "rewrite_needed": bool(tone_issues) and not blocking_issues,
        "retry_needed": len(blocking_issues) > 0,
    }


# ── helpers ─────────────────────────────────────────────────────────────


def _find_product(name: str, items: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    for item in items:
        if item.get("product_name") == name:
            return item
    return None


def _names_in_text(text: str, known_names: set[str]) -> set[str]:
    """Return subset of *known_names* that appear literally in *text*."""
    found: set[str] = set()
    for name in known_names:
        if name and name in text:
            found.add(name)
    return found


def _build_suggestion(blocking: List[str], issues: List[str], tone: List[str]) -> str:
    parts: List[str] = []
    if "budget_mismatch" in blocking:
        parts.append("主推商品超预算，请检查候选排序或明确说明预算偏差。")
    if "primary_explanation_mismatch" in blocking:
        parts.append("解释段落讨论的商品与主推商品不一致，请对齐。")
    if "format_readability_poor" in blocking or "format_readability_poor" in issues:
        parts.append("回答格式过密，请增加换行和分段。")
    if "exposes_internal_score" in blocking:
        parts.append("删掉内部评分字段，改用星级展示。")
    if not parts and tone:
        parts.append("把开头改得更像真人导购，减少系统过程描述，保留商品、价格、库存和星级不变。")
    return " ".join(parts)


def _compact_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    compact = []
    for item in items[:6]:
        compact.append(
            {
                "product_name": item.get("product_name"),
                "category": item.get("category"),
                "price": item.get("price"),
                "stock": item.get("stock"),
                "relation": item.get("relation"),
                "reason": item.get("reason"),
            }
        )
    return compact


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)
