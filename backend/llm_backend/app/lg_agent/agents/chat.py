"""Chat Agent for non-retrieval conversation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.logger import get_logger
from app.lg_agent.llm_client import generate_text, llm_config_label

logger = get_logger(service="chat_agent")


def create_chat_node():
    async def chat(state: Dict[str, Any]) -> Dict[str, Any]:
        query = state.get("task") or _last_user_message(state)
        supervisor_decision = state.get("supervisor_decision") or {}

        fallback = deterministic_chat_answer(query, supervisor_decision.get("intent"))
        try:
            answer = await generate_text(
                _build_messages(query, state.get("messages") or [], supervisor_decision, fallback),
                temperature=0.35,
                max_tokens=420,
                tags=["commerce_chat_agent"],
            )
            if not answer:
                answer = fallback
            source = "llm"
        except Exception as exc:
            logger.info(f"Chat Agent LLM unavailable, fallback to deterministic answer: {exc}")
            answer = fallback
            source = "fallback"

        return {
            "chat_answer": answer,
            "chat_context": {"source": source, "model": llm_config_label()},
            "steps": ["chat"],
        }

    return chat


def deterministic_chat_answer(query: str, intent: Optional[str] = None) -> str:
    text = query.strip()
    if intent == "support" or any(word in text for word in ("故障", "坏了", "退货", "投诉", "差评", "售后", "修")):
        return (
            "我先按售后问题处理，不主动做商品推荐。你可以告诉我订单信息、购买时间和具体故障现象，"
            "我会帮你整理退换货、维修或客服沟通路径。"
        )
    if intent == "store_scope" or any(word in text for word in ("卖什么", "卖啥", "有什么商品", "有什么产品", "主营", "经营什么", "你家是卖什么", "你们是卖什么")):
        return (
            "我们主要卖智能家居和家庭安防类商品，包括智能门锁、摄像头、人体/门窗传感器、智能灯具、智能插座、音箱、扫地机器人、空气净化器等。\n"
            "如果你不知道买什么，可以直接说场景，比如“给爸妈配一套家庭安防”“新房想做全屋智能”“预算 1500 以内”，我会帮你查商品并搭配推荐。"
        )
    if _asks_model(text):
        return f"当前对话大模型配置是 {llm_config_label()}。商品检索和推荐分数由本地 RAG 与商品关系图计算，不会把 API key 暴露给用户。"
    if any(word in text for word in ("你好", "您好", "hello", "hi", "嗨")):
        return "你好，我是 AssistGen。你可以直接告诉我想买什么、预算多少、给谁用，我会帮你查商品并做搭配推荐。"
    if any(word in text for word in ("你是谁", "介绍", "能做什么")):
        return "我是一个智能电商客服 Agent，主要能做商品问答、搭配推荐、方案生成和推荐解释。比如你可以问：帮我配一套家庭安防方案。"
    return "我在。你可以和我闲聊，也可以直接说购买需求；如果进入商品场景，我会自动调用检索、推荐和解释链路。"


def _build_messages(
    query: str,
    history: List[Dict[str, str]],
    supervisor_decision: Dict[str, Any],
    fallback: str,
) -> List[Dict[str, str]]:
    compact_history = []
    for message in history[-6:]:
        role = message.get("role")
        content = message.get("content")
        if role in {"user", "assistant"} and content:
            compact_history.append({"role": role, "content": str(content)[:500]})

    system = (
        "你是 AssistGen，一个智能电商客服多智能体系统里的 Chat Agent。\n"
        "职责：回答闲聊、能力介绍、系统模型说明、售后安抚、店铺经营范围等非检索问题。\n"
        "边界：不要编造具体商品库存和价格；需要商品推荐时，引导用户说预算、场景、人群，由检索推荐链路处理。\n"
        "语气：自然、简洁、像导购客服，不要机械复述系统架构。\n"
        f"当前模型配置：{llm_config_label()}。\n"
        f"Supervisor 判断：{supervisor_decision}。\n"
        f"确定性兜底答案：{fallback}"
    )
    return [{"role": "system", "content": system}, *compact_history, {"role": "user", "content": query}]


def _asks_model(text: str) -> bool:
    return any(word in text for word in ("什么大模型", "哪个大模型", "什么模型", "用的模型", "llm", "deepseek", "gpt"))


def _last_user_message(state: Dict[str, Any]) -> str:
    messages = state.get("messages", [])
    if not messages:
        return ""
    last = messages[-1]
    if isinstance(last, dict):
        return str(last.get("content") or "")
    return getattr(last, "content", str(last))
