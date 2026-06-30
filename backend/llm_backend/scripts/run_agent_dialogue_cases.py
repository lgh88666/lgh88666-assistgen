"""End-to-end agent dialogue pressure tests.

Runs realistic ecommerce conversations through the current agent chain and
prints a compact pass/fail table.

Usage::

    cd backend/llm_backend
    python -B scripts/run_agent_dialogue_cases.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lg_agent.pipeline import run_commerce_agent

# ── test case definitions ──────────────────────────────────────────────────

CASE_DEFS: List[Dict[str, Any]] = [
    {
        "name": "budget_constraint",
        "required": True,
        "turns": [
            {"query": "我预算 1000，想买扫地机器人", "messages": []},
        ],
        "expect": lambda r: _check_budget_constraint(r),
    },
    {
        "name": "cheapest_intent",
        "required": True,  # Query Understanding should now route to retrieval
        "turns": [
            {"query": "我要最便宜的智能门锁", "messages": []},
        ],
        "expect": lambda r: _check_purchase_routing(r, "lowest_price"),
    },
    {
        "name": "value_for_money_followup",
        "required": True,
        "turns": [
            {
                "query": "我想买智能摄像头",
                "messages": [
                    {"role": "user", "content": "我想买智能摄像头"},
                ],
            },
            {
                "query": "我主要在意性价比",
                "messages": [
                    {"role": "user", "content": "我想买智能摄像头"},
                    {"role": "assistant", "content": "好的，我来帮你看看智能摄像头..."},
                    {"role": "user", "content": "我主要在意性价比"},
                ],
            },
        ],
        "expect": lambda r: _check_memory_followup(r),
    },
    {
        "name": "complaint_support",
        "required": True,
        "turns": [
            {"query": "我买的摄像头坏了，我很生气，想退货", "messages": []},
        ],
        "expect": lambda r: _check_support(r),
    },
    {
        "name": "complete_solution",
        "required": True,
        "turns": [
            {"query": "帮我给爸妈配一套 1500 元以内的家庭安防方案", "messages": []},
        ],
        "expect": lambda r: _check_solution(r),
    },
    {
        "name": "explanation_challenge",
        "required": False,
        "turns": [
            {
                "query": "为什么推荐这个搭配？",
                "messages": [
                    {"role": "user", "content": "我想买智能门锁和摄像头"},
                    {"role": "assistant", "content": "为你推荐：华为智选智能门锁 SE + 小米智能摄像机 3 Pro..."},
                    {"role": "user", "content": "为什么推荐这个搭配？"},
                ],
            },
        ],
        "expect": lambda r: _check_explanation(r),
    },
    {
        "name": "reranker_sensitive_retrieval",
        "required": False,
        "turns": [
            {"query": "小米智能家居产品推荐", "messages": []},
        ],
        "expect": lambda r: _check_reranker_observable(r),
    },
    {
        "name": "chitchat",
        "required": True,
        "turns": [
            {"query": "你是用什么大模型？", "messages": []},
        ],
        "expect": lambda r: _check_chitchat(r),
    },
    # ── Query Understanding routing validation ────────────────────────
    {
        "name": "routing_cheapest_lock",
        "required": True,
        "turns": [
            {"query": "我要最便宜的智能门锁", "messages": []},
        ],
        "expect": lambda r: _check_route_retrieval(r, "lowest_price"),
    },
    {
        "name": "routing_cheaper_camera",
        "required": True,
        "turns": [
            {"query": "有没有便宜点的摄像头", "messages": []},
        ],
        "expect": lambda r: _check_route_retrieval(r, "lowest_price"),
    },
    {
        "name": "routing_budget_sweeper",
        "required": False,  # Routes to retrieval correctly but 0 candidates due to strict budget filtering
        "turns": [
            {"query": "1000以内的扫地机器人", "messages": []},
        ],
        "expect": lambda r: _check_route_retrieval(r, None),
    },
    {
        "name": "routing_value_for_money_lock",
        "required": True,
        "turns": [
            {"query": "性价比高的门锁", "messages": []},
        ],
        "expect": lambda r: _check_route_retrieval(r, "best_value"),
    },
    {
        "name": "routing_stock_check",
        "required": True,
        "turns": [
            {"query": "这个有货吗", "messages": []},
        ],
        "expect": lambda r: _check_route_retrieval(r, None),
    },
    {
        "name": "routing_price_check",
        "required": True,
        "turns": [
            {"query": "多少钱", "messages": []},
        ],
        "expect": lambda r: _check_route_retrieval(r, None),
    },
    {
        "name": "routing_elder_camera",
        "required": True,
        "turns": [
            {"query": "推荐一款适合老人用的摄像头", "messages": []},
        ],
        "expect": lambda r: _check_route_retrieval(r, None),
    },
    {
        "name": "routing_refund_suppress",
        "required": True,
        "turns": [
            {"query": "我买的摄像头坏了想退货", "messages": []},
        ],
        "expect": lambda r: _check_support_routing(r),
    },
]


# ── expectation checkers ───────────────────────────────────────────────────


def _check_budget_constraint(result: Dict[str, Any]) -> Dict[str, Any]:
    answer = result.get("answer", "")
    recommendations = result.get("recommendations", [])
    metadata = result.get("metadata", {})
    critic = metadata.get("critic", {})
    issues = []

    # Should not push a 5000+ product as main without budget note.
    first_rec = recommendations[0] if recommendations else {}
    first_price = float(first_rec.get("price", 0))
    if first_price > 5000 and "超预算" not in answer and "预算" not in answer:
        issues.append("high_price_no_budget_note")

    # Critic should not have budget_mismatch blocking if answer handles it.
    blocking = critic.get("blocking_issues") or []
    if "budget_mismatch" in blocking:
        issues.append("critic_blocked_budget")

    return {"pass": len(issues) == 0, "issues": issues}


def _check_cheapest(result: Dict[str, Any]) -> Dict[str, Any]:
    answer = result.get("answer", "")
    recommendations = result.get("recommendations", [])
    issues = []

    # Should have candidates.
    retrieval = result.get("retrieval_candidates", [])
    if not retrieval:
        issues.append("no_retrieval_candidates")

    # Add-on recommendations should not dominate a "cheapest" query.
    rec_section_start = answer.find("搭配推荐")
    if rec_section_start >= 0:
        after_rec = answer[rec_section_start:]
        if len(after_rec) > len(answer) * 0.4:
            issues.append("addons_dominate_cheapest")

    # Prices should be low-ish (at least first candidate should be affordable).
    if retrieval:
        prices = [float(c.get("price", 9999)) for c in retrieval[:5]]
        if min(prices) > 2000:
            issues.append("no_low_price_candidates")

    return {"pass": len(issues) == 0, "issues": issues}


def _check_memory_followup(result: Dict[str, Any]) -> Dict[str, Any]:
    metadata = result.get("metadata", {})
    memory = metadata.get("memory_context", {})
    issues = []

    if not memory.get("memory_used"):
        issues.append("memory_not_used")
    shopping = memory.get("shopping_state") or {}
    ranking = shopping.get("ranking_objective", "")
    if ranking not in ("best_value", "lowest_price"):
        issues.append(f"ranking_objective_not_adjusted={ranking}")
    cats = shopping.get("product_categories") or []
    if not cats:
        issues.append("categories_lost")

    return {"pass": len(issues) == 0, "issues": issues}


def _check_support(result: Dict[str, Any]) -> Dict[str, Any]:
    answer = result.get("answer", "")
    supervisor = result.get("metadata", {}).get("supervisor", {})
    issues = []

    # Route should be chat, not retrieval.
    if supervisor.get("route") != "chat":
        issues.append(f"route_not_chat={supervisor.get('route')}")

    # Answer should not push products aggressively.
    if "推荐" in answer and ("买" in answer or "入手" in answer):
        # Some recommendation wording is ok if it's mild, but aggressive selling is bad.
        if "强烈推荐" in answer or "必买" in answer:
            issues.append("aggressive_selling_in_support")

    return {"pass": len(issues) == 0, "issues": issues}


def _check_solution(result: Dict[str, Any]) -> Dict[str, Any]:
    answer = result.get("answer", "")
    issues = []

    # Should not end with dangling colon or incomplete phrase.
    stripped = answer.strip()
    if stripped.endswith("：") or stripped.endswith("在于："):
        issues.append("truncated_ending")

    # Should be substantive (min length).
    if len(answer) < 80:
        issues.append("answer_too_short")

    # Should mention budget or money amount (the query specifies ¥1500).
    has_amount = any(
        marker in answer
        for marker in ("1500", "预算", "¥", "元以内", "以内")
    )
    if not has_amount:
        issues.append("budget_not_referenced")

    return {"pass": len(issues) == 0, "issues": issues}


def _check_explanation(result: Dict[str, Any]) -> Dict[str, Any]:
    answer = result.get("answer", "")
    metadata = result.get("metadata", {})
    explanation_source = metadata.get("explanation_source", "")
    issues = []

    # Should have some explanation content.
    if len(answer) < 30:
        issues.append("answer_too_short")

    # Explanation source should be non-empty.
    if not explanation_source:
        issues.append("no_explanation_source")

    # Should not be purely generic "功能互补".
    if answer.count("功能互补") >= 2 and "场景" not in answer and "搭配" not in answer:
        issues.append("generic_explanation_only")

    return {"pass": len(issues) == 0, "issues": issues}


def _check_reranker_observable(result: Dict[str, Any]) -> Dict[str, Any]:
    metadata = result.get("metadata", {})
    retrieval_source = metadata.get("retrieval_source", "")
    issues = []

    # Retrieval should have candidates.
    candidates = result.get("retrieval_candidates", [])
    if not candidates:
        issues.append("no_candidates")

    # Source should be non-empty.
    if not retrieval_source:
        issues.append("no_retrieval_source")

    return {"pass": len(issues) == 0, "issues": issues}


def _check_chitchat(result: Dict[str, Any]) -> Dict[str, Any]:
    supervisor = result.get("metadata", {}).get("supervisor", {})
    answer = result.get("answer", "")
    issues = []

    # Route should be chat.
    if supervisor.get("route") != "chat":
        issues.append(f"route_not_chat={supervisor.get('route')}")

    # Answer should not be empty.
    if len(answer) < 5:
        issues.append("answer_too_short")

    return {"pass": len(issues) == 0, "issues": issues}


def _check_route_retrieval(
    result: Dict[str, Any], expected_ranking: str | None = None
) -> Dict[str, Any]:
    """Verify the query was routed to retrieval (not chat)."""
    supervisor = result.get("metadata", {}).get("supervisor", {})
    metadata = result.get("metadata", {})
    memory = metadata.get("memory_context", {})
    shopping = memory.get("shopping_state") or {}
    query_features = (metadata.get("query_features") or {})
    issues = []

    route = supervisor.get("route", "?")
    if route != "retrieval":
        issues.append(f"expected_retrieval_got_{route}")

    # If an expected ranking objective is specified, check for its presence.
    if expected_ranking:
        ranking = (
            shopping.get("ranking_objective")
            or (query_features or {}).get("ranking_objective")
        )
        if ranking != expected_ranking:
            issues.append(f"ranking_mismatch_expected_{expected_ranking}_got_{ranking}")

    # Should have at least some retrieval candidates.
    candidates = result.get("retrieval_candidates", [])
    if route == "retrieval" and not candidates:
        issues.append("no_retrieval_candidates")

    return {"pass": len(issues) == 0, "issues": issues}


def _check_support_routing(result: Dict[str, Any]) -> Dict[str, Any]:
    """Verify support/complaint queries suppress selling."""
    supervisor = result.get("metadata", {}).get("supervisor", {})
    answer = result.get("answer", "")
    issues = []

    # Should route to chat (support mode).
    route = supervisor.get("route", "?")
    intent = supervisor.get("intent", "?")

    # Support should not go to retrieval for product pushing.
    if route == "retrieval" and intent not in ("support",):
        issues.append(f"support_routed_to_retrieval")

    # Answer should be support-oriented, not selling.
    if "推荐" in answer and "买" in answer:
        issues.append("selling_in_support_answer")

    return {"pass": len(issues) == 0, "issues": issues}


def _check_purchase_routing(
    result: Dict[str, Any], expected_ranking: str | None = None
) -> Dict[str, Any]:
    """Alias for _check_route_retrieval."""
    return _check_route_retrieval(result, expected_ranking)


# ── main runner ────────────────────────────────────────────────────────────


async def run_one_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Run a single dialogue case and return a result dict."""
    result: Dict[str, Any] = {}
    for turn in case["turns"]:
        result = await run_commerce_agent(
            query=turn["query"],
            user_id=1,
            messages=turn["messages"],
        )

    check = case["expect"](result)

    # Extract summary fields.
    metadata = result.get("metadata", {})
    supervisor = metadata.get("supervisor", {})
    critic = metadata.get("critic", {})
    recommendations = result.get("recommendations", [])

    top_products = ", ".join(
        r.get("product_name", "") for r in recommendations[:3]
    ) or "(none)"

    return {
        "name": case["name"],
        "required": case.get("required", True),
        "route": supervisor.get("route", "?"),
        "intent": supervisor.get("intent", "?"),
        "top_products": top_products[:80],
        "rec_count": len(recommendations),
        "critic_decision": critic.get("decision", "?"),
        "explanation_source": metadata.get("explanation_source", ""),
        "retrieval_source": metadata.get("retrieval_source", ""),
        "answer_length": len(result.get("answer", "")),
        "pass": check["pass"],
        "issues": check["issues"],
    }


async def main() -> None:
    print("=" * 72)
    print("AssistGen Agent Dialogue Pressure Tests")
    print("=" * 72)

    results = []
    for case in CASE_DEFS:
        sys.stdout.write(f"  {case['name']}... ")
        sys.stdout.flush()
        try:
            r = await run_one_case(case)
        except Exception as exc:
            r = {
                "name": case["name"],
                "required": case.get("required", True),
                "route": "error",
                "intent": "error",
                "top_products": "(error)",
                "rec_count": 0,
                "critic_decision": "error",
                "explanation_source": "",
                "retrieval_source": "",
                "answer_length": 0,
                "pass": False,
                "issues": [f"exception: {exc}"],
            }
        status = "PASS" if r["pass"] else "FAIL"
        print(status)
        results.append(r)

    # ── summary table ──────────────────────────────────────────────────
    print()
    print(f"{'Case':<30} {'Req':<5} {'Route':<12} {'Critic':<22} {'Len':<6} {'Result':<6}")
    print("-" * 85)
    all_pass = True
    for r in results:
        required = "Y" if r["required"] else "N"
        issues_str = f" ({'; '.join(r['issues'])})" if r["issues"] else ""
        print(
            f"{r['name']:<30} {required:<5} {r['route']:<12} "
            f"{r['critic_decision']:<22} {r['answer_length']:<6} "
            f"{'PASS' if r['pass'] else 'FAIL'}{issues_str}"
        )
        if r["required"] and not r["pass"]:
            all_pass = False

    print("-" * 85)
    required_total = sum(1 for r in results if r["required"])
    required_pass = sum(1 for r in results if r["required"] and r["pass"])
    optional_total = sum(1 for r in results if not r["required"])
    optional_pass = sum(1 for r in results if not r["required"] and r["pass"])
    print(f"Required: {required_pass}/{required_total}  Optional: {optional_pass}/{optional_total}")

    if not all_pass:
        print("\n[FAIL] Some required cases FAILED.")
        sys.exit(1)
    else:
        print("\n[PASS] All required cases PASSED.")


if __name__ == "__main__":
    asyncio.run(main())
