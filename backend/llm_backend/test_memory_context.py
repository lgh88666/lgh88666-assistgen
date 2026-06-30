"""Smoke tests for memory context builder."""
import asyncio
from app.lg_agent.memory.context import build_memory_context


def test_standalone_no_history():
    result = asyncio.run(build_memory_context("你用的什么大模型", []))
    assert result["effective_query"] == "你用的什么大模型"
    assert result["memory_used"] is False
    assert result["shopping_state"] == {}
    print("  OK  test_standalone_no_history")


def test_followup_best_value():
    msgs = [
        {"role": "user", "content": "我想买智能门锁和摄像头"},
        {"role": "assistant", "content": "好的，为您推荐几款智能门锁和摄像头..."},
        {"role": "user", "content": "我主要在意性价比"},
    ]
    result = asyncio.run(build_memory_context("我主要在意性价比", msgs))
    assert result["memory_used"] is True, f"memory_used should be True, got {result}"
    ss = result["shopping_state"]
    assert "智能门锁" in str(ss.get("product_categories", [])) or "智能摄像头" in str(ss.get("product_categories", [])), f"Expected product categories, got {ss}"
    assert ss.get("ranking_objective") in ("best_value", "balanced"), f"Expected best_value ranking, got {ss.get('ranking_objective')}"
    print("  OK  test_followup_best_value")


def test_followup_low_price():
    msgs = [
        {"role": "user", "content": "最便宜的扫地机器人推荐一下"},
        {"role": "assistant", "content": "为您找到以下低价扫地机器人..."},
        {"role": "user", "content": "有没有小米的"},
    ]
    result = asyncio.run(build_memory_context("有没有小米的", msgs))
    assert result["memory_used"] is True, f"memory_used should be True, got {result}"
    ss = result["shopping_state"]
    assert "小米" in str(ss.get("preferred_brands", [])) or result["effective_query"] != "有没有小米的", \
        f"Should have picked up Xiaomi preference or enriched query, got {ss}"
    print("  OK  test_followup_low_price")


def test_support_query():
    msgs = [{"role": "user", "content": "东西坏了我要退货"}]
    result = asyncio.run(build_memory_context("东西坏了我要退货", msgs))
    assert result["memory_used"] is False
    assert result["effective_query"] == "东西坏了我要退货"
    print("  OK  test_support_query")


def test_solution_plan():
    msgs = [{"role": "user", "content": "给爸妈配一套1500以内的家庭安防方案"}]
    result = asyncio.run(build_memory_context("给爸妈配一套1500以内的家庭安防方案", msgs))
    assert result["raw_query"] == "给爸妈配一套1500以内的家庭安防方案"
    print("  OK  test_solution_plan")


def test_hint_text():
    msgs = [
        {"role": "user", "content": "我想买智能门锁和摄像头"},
        {"role": "assistant", "content": "为您推荐..."},
        {"role": "user", "content": "我主要在意性价比"},
    ]
    result = asyncio.run(build_memory_context("我主要在意性价比", msgs))
    assert result["memory_used"] is True
    if result.get("hint_text"):
        assert "本轮理解" in result["hint_text"]
        assert "智能" in result["hint_text"]
    print("  OK  test_hint_text")


def test_session_persistence():
    """V3: session_id should be returned in result."""
    result = asyncio.run(build_memory_context("我想买扫地机器人", [], session_id="test_sess_001"))
    assert result["session_id"] == "test_sess_001"
    print("  OK  test_session_persistence")


if __name__ == "__main__":
    test_standalone_no_history()
    test_followup_best_value()
    test_followup_low_price()
    test_support_query()
    test_solution_plan()
    test_hint_text()
    test_session_persistence()
    print("\nAll memory context tests passed!")
