"""Unit tests for Critic Quality Gate deterministic checks."""
from app.lg_agent.agents.critic import _deterministic_review


def _state(**overrides):
    base = {
        "draft_answer": "",
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


def test_approve_clean_answer():
    """A well-formed answer with no issues should get 'approve'."""
    review = _deterministic_review(_state(
        draft_answer="为你推荐\n\n1. ★★★★☆ 智能门锁 A\n   ¥999 | 智能门锁 | 库存 50\n\n搭配推荐\n- ★★★★☆ 摄像头 B\n  ¥299 | 智能摄像头\n  互补关系\n\n💬 可以告诉我预算。",
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
    ))
    assert review["decision"] == "approve", f"Expected approve, got {review['decision']}: {review['blocking_issues']}"
    assert review["approved"] is True
    print("  OK  test_approve_clean_answer")


def test_budget_mismatch_blocked():
    """Primary product way over budget should be blocked."""
    review = _deterministic_review(_state(
        draft_answer="为你推荐\n\n1. ★★★★☆ 旗舰扫地机\n   ¥5799 | 智能清洁 | 库存 30",
        retrieval_context={
            "candidates": [
                {"product_name": "旗舰扫地机", "price": 5799, "category": "智能清洁", "stock": 30},
            ],
            "constraints": {},
        },
        shopping_state={"budget_max": 1000, "ranking_objective": "best_value"},
    ))
    assert "budget_mismatch" in review["blocking_issues"], f"Expected budget_mismatch: {review}"
    assert review["approved"] is False
    print("  OK  test_budget_mismatch_blocked")


def test_budget_within_range_not_blocked():
    """Product within budget should not trigger budget_mismatch."""
    review = _deterministic_review(_state(
        draft_answer="为你推荐\n\n1. ★★★★☆ 平价扫地机\n   ¥899 | 智能清洁 | 库存 30",
        retrieval_context={
            "candidates": [
                {"product_name": "平价扫地机", "price": 899, "category": "智能清洁", "stock": 30},
            ],
            "constraints": {},
        },
        shopping_state={"budget_max": 1000, "ranking_objective": "best_value"},
    ))
    assert "budget_mismatch" not in review.get("blocking_issues", []), f"Should not block: {review}"
    print("  OK  test_budget_within_range_not_blocked")


def test_primary_explanation_mismatch():
    """Explanation discusses different products than the draft."""
    review = _deterministic_review(_state(
        draft_answer="为你推荐\n\n1. ★★★★☆ 智能门锁 A\n   ¥999 | 智能门锁",
        retrieval_context={
            "candidates": [
                {"product_name": "智能门锁 A", "price": 999, "category": "智能门锁", "stock": 50},
                {"product_name": "摄像头 B", "price": 299, "category": "智能摄像头"},
                {"product_name": "传感器 C", "price": 129, "category": "智能传感器"},
            ],
            "constraints": {},
        },
        explanation_answer="摄像头 B 和传感器 C 是非常好的搭配选择。",
        explanation_context={"mentioned_product_names": ["摄像头 B", "传感器 C"]},
        shopping_state={"ranking_objective": "balanced"},
    ))
    assert "primary_explanation_mismatch" in review["blocking_issues"], f"Expected mismatch: {review}"
    print("  OK  test_primary_explanation_mismatch")


def test_low_price_no_over_promote_addons():
    """Low-price intent should not let add-ons dominate the answer."""
    primary_section = "为你推荐\n\n1. ★★★☆☆ 入门扫地机\n   ¥899 | 智能清洁 | 库存 10"
    rec_section = "搭配推荐\n" + "\n".join(
        f"- ★★★★☆ 高端净化器 {i}\n  ¥{2000+i*100} | 空气净化器\n  推荐理由"
        for i in range(1, 4)
    )
    review = _deterministic_review(_state(
        draft_answer=f"{primary_section}\n{rec_section}",
        retrieval_context={
            "candidates": [
                {"product_name": "入门扫地机", "price": 899, "category": "智能清洁", "stock": 10},
            ],
            "constraints": {},
        },
        recommendation_results=[
            {"product_name": f"高端净化器 {i}", "price": 2000 + i * 100, "category": "空气净化器"}
            for i in range(1, 4)
        ],
        shopping_state={"ranking_objective": "lowest_price"},
    ))
    assert "recommendation_strategy_mismatch" in review["blocking_issues"], f"Expected strategy mismatch: {review}"
    print("  OK  test_low_price_no_over_promote_addons")


def test_format_too_short_blocked():
    """Answer with fewer than 3 lines should be flagged."""
    review = _deterministic_review(_state(
        draft_answer="为你推荐\n1. 门锁 ¥999",
        retrieval_context={
            "candidates": [{"product_name": "门锁", "price": 999, "category": "智能门锁", "stock": 10}],
            "constraints": {},
        },
    ))
    assert "format_readability_poor" in review["blocking_issues"]
    print("  OK  test_format_too_short_blocked")


def test_exposes_internal_score_blocked():
    """Answer exposing internal_score should be blocked."""
    review = _deterministic_review(_state(
        draft_answer="为你推荐\n\n1. ★★★★☆ 门锁\n   推荐分 0.92 | ¥999 | 智能门锁\n\n2. ★★★★☆ 摄像头\n   final_score=0.88 | ¥299",
        retrieval_context={
            "candidates": [
                {"product_name": "门锁", "price": 999, "category": "智能门锁", "stock": 10},
                {"product_name": "摄像头", "price": 299, "category": "智能摄像头", "stock": 20},
            ],
            "constraints": {},
        },
    ))
    assert "exposes_internal_score" in review["blocking_issues"]
    print("  OK  test_exposes_internal_score_blocked")


def test_tone_only_triggers_rewrite():
    """Robotic tone with no blocking issues → rewrite_only."""
    review = _deterministic_review(_state(
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
    ))
    assert review["decision"] == "rewrite_only", f"Expected rewrite_only, got {review['decision']}: {review}"
    assert review["rewrite_needed"] is True
    assert review["approved"] is True
    print("  OK  test_tone_only_triggers_rewrite")


def test_retry_recommendation_on_budget():
    """Budget mismatch → retry_recommendation."""
    review = _deterministic_review(_state(
        draft_answer="为你推荐\n\n1. ★★★★☆ 旗舰机\n   ¥5799 | 智能清洁 | 库存 10",
        retrieval_context={
            "candidates": [
                {"product_name": "旗舰机", "price": 5799, "category": "智能清洁", "stock": 10},
            ],
            "constraints": {},
        },
        shopping_state={"budget_max": 1000},
    ))
    assert review["decision"] == "retry_recommendation", f"Expected retry_recommendation: {review}"
    assert review["retry_needed"] is True
    print("  OK  test_retry_recommendation_on_budget")


if __name__ == "__main__":
    test_approve_clean_answer()
    test_budget_mismatch_blocked()
    test_budget_within_range_not_blocked()
    test_primary_explanation_mismatch()
    test_low_price_no_over_promote_addons()
    test_format_too_short_blocked()
    test_exposes_internal_score_blocked()
    test_tone_only_triggers_rewrite()
    test_retry_recommendation_on_budget()
    print("\nAll Critic Quality Gate tests passed!")
