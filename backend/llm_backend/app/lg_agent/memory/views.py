"""每个 Agent 的记忆视角。

每个 Agent 只接收其任务所需的字段。
避免完整的聊天记录或原始评分数据泄露到
不该出现的 Agent 提示词中。
"""

from __future__ import annotations

from typing import Any, Dict


def supervisor_view(memory_context: Dict[str, Any]) -> Dict[str, Any]:
    """Supervisor 的记忆视角：意图 / 对话延续信号。"""
    ss = memory_context.get("shopping_state") or {}
    return {
        "is_continuing_task": bool(memory_context.get("memory_used")),
        "active_category": ss.get("active_category"),
        "product_categories": ss.get("product_categories") or [],
        "shopping_stage": ss.get("shopping_stage", "discovering"),
        "user_emotion": ss.get("user_emotion", "neutral"),
        "effective_query": memory_context.get("effective_query", ""),
    }


def retrieval_view(memory_context: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieval 的记忆视角：搜索条件与过滤参数。"""
    ss = memory_context.get("shopping_state") or {}
    return {
        "effective_query": memory_context.get("effective_query", ""),
        "category": ss.get("active_category"),
        "product_categories": ss.get("product_categories") or [],
        "budget_min": ss.get("budget_min"),
        "budget_max": ss.get("budget_max"),
        "ranking_objective": ss.get("ranking_objective", "balanced"),
        "preferred_brands": ss.get("preferred_brands") or [],
        "rejected_brands": ss.get("rejected_brands") or [],
        "filters": {"in_stock": True},
    }


def recommendation_view(memory_context: Dict[str, Any]) -> Dict[str, Any]:
    """Recommendation 的记忆视角：搭配推荐 / 避坑信息。"""
    ss = memory_context.get("shopping_state") or {}
    return {
        "main_product_category": ss.get("active_category"),
        "product_categories": ss.get("product_categories") or [],
        "soft_preferences": ss.get("soft_preferences") or [],
        "hard_constraints": ss.get("hard_constraints") or [],
        "last_recommended_ids": memory_context.get("last_recommended_ids") or [],
        "rejected_products": ss.get("rejected_products") or [],
        "preferred_ecosystem": (ss.get("preferred_brands") or [None])[0],
        "budget_max": ss.get("budget_max"),
        "ranking_objective": ss.get("ranking_objective", "balanced"),
    }


def explanation_view(memory_context: Dict[str, Any]) -> Dict[str, Any]:
    """Explanation 的记忆视角：用户关心的维度。"""
    ss = memory_context.get("shopping_state") or {}
    user_cares: list[str] = []
    if ss.get("ranking_objective") == "best_value":
        user_cares.append("性价比")
    if ss.get("soft_preferences"):
        user_cares.extend(ss["soft_preferences"][:3])
    return {
        "user_cares_about": user_cares or ["综合体验"],
        "summary": memory_context.get("effective_query", ""),
    }


def critic_view(memory_context: Dict[str, Any]) -> Dict[str, Any]:
    """Critic 的记忆视角：硬约束 + 语气提示。"""
    ss = memory_context.get("shopping_state") or {}
    return {
        "hard_constraints": ss.get("hard_constraints") or [],
        "budget_max": ss.get("budget_max"),
        "user_emotion": ss.get("user_emotion", "neutral"),
        "ranking_objective": ss.get("ranking_objective", "balanced"),
        "last_user_query": memory_context.get("raw_query", ""),
        "rejected_brands": ss.get("rejected_brands") or [],
    }
