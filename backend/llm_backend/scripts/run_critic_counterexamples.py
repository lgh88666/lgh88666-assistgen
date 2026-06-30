"""Critic counterexample pressure tests.

Feed the deterministic Critic realistic bad-answer drafts and verify that
the expected blocking_issues and decision are produced.  Run standalone::

    python -B scripts/run_critic_counterexamples.py
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List

from app.lg_agent.agents.critic import _deterministic_review


def _state(draft_answer: str, **overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "draft_answer": draft_answer,
        "shopping_state": {},
        "retrieval_context": {"candidates": [], "constraints": {}},
        "recommendation_results": [],
        "explanation_answer": "",
        "explanation_context": {},
        "recommendation_context": {},
        "supervisor_decision": {},
        "task": "",
        "raw_query": "",
    }
    base.update(overrides)
    return base


def _run_one(name: str, state: Dict[str, Any], expected_decision: str,
             expected_blocking: List[str] | None = None) -> bool:
    review = _deterministic_review(state)
    decision = review.get("decision", "?")
    blocking = review.get("blocking_issues") or []
    issues = review.get("issues") or []

    ok = True
    if decision != expected_decision:
        print(f"  FAIL  {name}: expected decision={expected_decision}, got {decision}")
        ok = False
    if expected_blocking is not None:
        missing = set(expected_blocking) - set(blocking)
        if missing:
            print(f"  FAIL  {name}: missing blocking_issues={missing}, got {blocking}")
            ok = False
    if ok:
        print(f"  OK   {name}  ->  decision={decision}  blocking={blocking}  issues={issues}")
    return ok


def main() -> int:
    passed = 0
    failed = 0

    def check(name: str, **kwargs: Any) -> None:
        nonlocal passed, failed
        ok = _run_one(name, **kwargs)
        if ok:
            passed += 1
        else:
            failed += 1

    # ── 1. budget mismatch ──────────────────────────────────────────
    check(
        "budget: high-price primary, budget=1000",
        state=_state(
            draft_answer="1. ★★★★☆ 旗舰扫地机\n   ¥5799 | 智能清洁 | 库存 10\n\n搭配推荐\n- ★★★★☆ 空气净化器\n  ¥2499 | 空气净化器",
            shopping_state={"budget_max": 1000},
            retrieval_context={
                "candidates": [
                    {"product_name": "旗舰扫地机", "price": 5799, "category": "智能清洁", "stock": 10},
                ],
                "constraints": {},
            },
        ),
        expected_decision="retry_recommendation",
        expected_blocking=["budget_mismatch"],
    )

    # ── 2. low-price intent dominated by add-ons ─────────────────────
    check(
        "strategy: cheap query with large add-on section",
        state=_state(
            draft_answer="1. ★★★☆☆ 入门扫地机\n   ¥899 | 智能清洁\n\n搭配推荐\n- ★★★★☆ 高端净化器 A\n  ¥2499\n- ★★★★☆ 高端净化器 B\n  ¥2599\n- ★★★★☆ 高端加湿器\n  ¥1899",
            shopping_state={"ranking_objective": "lowest_price"},
            retrieval_context={
                "candidates": [
                    {"product_name": "入门扫地机", "price": 899, "category": "智能清洁", "stock": 10},
                ],
                "constraints": {},
            },
            recommendation_results=[
                {"product_name": "高端净化器 A", "price": 2499},
                {"product_name": "高端净化器 B", "price": 2599},
                {"product_name": "高端加湿器", "price": 1899},
            ],
        ),
        expected_decision="retry_recommendation",
        expected_blocking=["recommendation_strategy_mismatch"],
    )

    # ── 3. complaint scenario ────────────────────────────────────────
    check(
        "support: complaint with normal answer should not force recommendation",
        state=_state(
            draft_answer="东西坏了可以退货，我先帮你查相关商品。\n\n1. ★★★★☆ 智能门锁\n   ¥999 | 智能门锁\n\n搭配推荐\n- ★★★★☆ 摄像头 ¥299",
            retrieval_context={
                "candidates": [
                    {"product_name": "智能门锁", "price": 999, "category": "智能门锁", "stock": 10},
                ],
                "constraints": {},
            },
            recommendation_results=[
                {"product_name": "摄像头", "price": 299},
            ],
            # Complaints should not trigger heavy recommendation, but the current
            # critic doesn't have that check yet.  Still, a budget-free recommendation
            # with no blocking issues should pass as approve or rewrite_only.
        ),
        expected_decision="approve",
    )

    # ── 4. internal score exposure ──────────────────────────────────
    check(
        "score: exposes final_score and retrieval_score",
        state=_state(
            draft_answer="1. ★★★★☆ 门锁\n   推荐分 0.92 | ¥999 | 智能门锁\n\n2. ★★★★☆ 摄像头\n   final_score=0.88 | ¥299",
            retrieval_context={
                "candidates": [
                    {"product_name": "门锁", "price": 999, "category": "智能门锁", "stock": 10},
                    {"product_name": "摄像头", "price": 299, "category": "智能摄像头", "stock": 20},
                ],
                "constraints": {},
            },
        ),
        expected_decision="retry_answer_composition",
        expected_blocking=["exposes_internal_score"],
    )

    # ── 5. unsupported product mention ──────────────────────────────
    check(
        "consistency: explanation mentions product outside candidates",
        state=_state(
            draft_answer="1. ★★★★☆ 智能门锁 A\n   ¥999 | 智能门锁\n\n为什么这样推荐\n智能门锁 A 配合 高端音箱 X 使用体验极佳。",
            retrieval_context={
                "candidates": [
                    {"product_name": "智能门锁 A", "price": 999, "category": "智能门锁", "stock": 10},
                    {"product_name": "摄像头 B", "price": 299, "category": "智能摄像头"},
                ],
                "constraints": {},
            },
            explanation_answer="智能门锁 A 配合 高端音箱 X 使用体验极佳。",
            explanation_context={"mentioned_product_names": ["高端音箱 X"]},
            shopping_state={"ranking_objective": "balanced"},
        ),
        expected_decision="retry_recommendation",
        expected_blocking=["primary_explanation_mismatch"],
        # "高端音箱 X" is outside all candidates → unsupported_explanation_product (issue)
        # AND also triggers primary_explanation_mismatch (explanation talks about products
        # not in the draft — correct behavior)
    )

    # ── 6. dense formatting ─────────────────────────────────────────
    check(
        "format: single-line dense answer",
        state=_state(
            draft_answer="推荐门锁¥999和摄像头¥299搭配使用非常适合家庭安防",
            retrieval_context={
                "candidates": [
                    {"product_name": "门锁", "price": 999, "category": "智能门锁", "stock": 10},
                ],
                "constraints": {},
            },
        ),
        expected_decision="retry_answer_composition",
        expected_blocking=["format_readability_poor"],
    )

    # ── 7. robotic tone only (not blocking) ──────────────────────────
    check(
        "tone: robotic wording should trigger rewrite_only",
        state=_state(
            draft_answer="我根据商品库为你推荐\n\n1. ★★★★☆ 门锁\n   ¥999 | 智能门锁 | 库存 10\n\n搭配关系让这些商品形成互补。\n\n💬 可以告诉我预算。",
            retrieval_context={
                "candidates": [
                    {"product_name": "门锁", "price": 999, "category": "智能门锁", "stock": 10},
                ],
                "constraints": {},
            },
            shopping_state={"ranking_objective": "balanced"},
            explanation_answer="门锁适合家庭安防。",
            explanation_context={"mentioned_product_names": ["门锁"]},
        ),
        expected_decision="rewrite_only",
    )

    # ── 8. clean answer should approve ──────────────────────────────
    check(
        "clean: well-formed multi-product answer",
        state=_state(
            draft_answer="1. ★★★★☆ 智能门锁 A\n   ¥999 | 智能门锁 | 库存 50\n\n搭配推荐\n- ★★★★☆ 摄像头 B\n  ¥299 | 智能摄像头\n  互补关系",
            retrieval_context={
                "candidates": [
                    {"product_name": "智能门锁 A", "price": 999, "category": "智能门锁", "stock": 50},
                ],
                "constraints": {},
            },
            recommendation_results=[
                {"product_name": "摄像头 B", "price": 299, "category": "智能摄像头"},
            ],
            shopping_state={"ranking_objective": "balanced"},
            explanation_answer="智能门锁 A 和摄像头 B 互补。",
            explanation_context={"mentioned_product_names": ["智能门锁 A", "摄像头 B"]},
        ),
        expected_decision="approve",
    )

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
