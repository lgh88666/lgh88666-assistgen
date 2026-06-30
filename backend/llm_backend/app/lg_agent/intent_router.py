"""Intent routing for the commerce Supervisor.

The router uses three layers:
1. High-confidence rules for obvious operational intents.
2. Semantic example matching with character n-gram cosine similarity.
3. Optional LLM structured classification when local confidence is low.
"""

from __future__ import annotations

import math
import re
import socket
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.core.config import ServiceType, settings


Intent = Literal["chat", "store_scope", "fact_query", "recommendation", "solution_plan", "support"]
Emotion = Literal["neutral", "positive", "hesitant", "angry"]


@dataclass(frozen=True)
class IntentSpec:
    intent: Intent
    description: str
    examples: tuple[str, ...]


INTENT_SPECS: tuple[IntentSpec, ...] = (
    IntentSpec(
        intent="store_scope",
        description="用户询问店铺经营范围、主营类目、卖什么商品。",
        examples=(
            "你家是卖什么的",
            "你们主要卖什么",
            "店里有什么商品",
            "你们主营什么产品",
            "这里可以买哪些东西",
            "有什么智能家居产品",
        ),
    ),
    IntentSpec(
        intent="solution_plan",
        description="用户希望按预算、场景或人群配置一套完整购买方案。",
        examples=(
            "帮我配一套家庭安防方案",
            "预算1500以内给爸妈配一套",
            "新房想做全屋智能",
            "给我一套完整购买方案",
            "卧室和客厅怎么搭一套",
            "家里老人用怎么配",
        ),
    ),
    IntentSpec(
        intent="recommendation",
        description="用户询问推荐、搭配、适合什么、买哪个更好。",
        examples=(
            "推荐一个智能门锁",
            "门锁和摄像头怎么搭配",
            "我应该买什么",
            "哪个更适合老人用",
            "有没有性价比高的摄像头",
            "这个还需要配什么",
        ),
    ),
    IntentSpec(
        intent="fact_query",
        description="用户查询具体商品事实，例如价格、库存、参数、规格、有货、品牌。",
        examples=(
            "这个多少钱",
            "有没有货",
            "智能门锁价格多少",
            "摄像头有什么参数",
            "小米摄像头库存还有吗",
            "门锁支持哪些规格",
        ),
    ),
    IntentSpec(
        intent="support",
        description="用户表达售后、故障、退货、投诉、差评或使用问题。",
        examples=(
            "东西坏了怎么办",
            "我要退货",
            "这个产品有故障",
            "我要投诉",
            "售后怎么处理",
            "用不了怎么修",
        ),
    ),
    IntentSpec(
        intent="chat",
        description="普通闲聊、问候、能力介绍，不需要商品检索。",
        examples=(
            "你好",
            "你是谁",
            "你能做什么",
            "在吗",
            "hello",
            "随便聊聊",
        ),
    ),
)


RULE_PATTERNS: dict[Intent, tuple[str, ...]] = {
    "store_scope": (
        r"卖(什么|啥)",
        r"(主营|经营).{0,4}(什么|啥)",
        r"有什么(商品|产品|东西)",
        r"可以买(什么|啥|哪些)",
    ),
    "solution_plan": (r"配.{0,4}套", r"完整.{0,4}方案", r"全屋", r"套装", r"预算\s*\d+"),
    "recommendation": (r"推荐", r"搭配", r"适合", r"(想买|准备买|我要买|想入手|打算买).*(门锁|摄像头|传感器|灯|插座|开关|音箱|窗帘|扫地|净化器|加湿器|空调|冰箱|洗衣机|厨房)", r"买(什么|哪个|哪款)", r"性价比"),
    "fact_query": (r"价格", r"多少钱", r"库存", r"有货", r"参数", r"规格", r"支持.*吗"),
    "support": (r"故障", r"坏了", r"退货", r"投诉", r"差评", r"售后", r"修"),
}


class LLMIntentDecision(BaseModel):
    intent: Intent = Field(description="用户意图")
    emotion: Emotion = Field(default="neutral", description="用户情绪")
    confidence: float = Field(ge=0, le=1, description="分类置信度")
    reason: str = Field(default="", description="简短分类理由")


def analyze_query(query: str) -> Dict[str, Any]:
    """Synchronous local routing for tests and deterministic fallback."""

    text = normalize_text(query)
    rule = rule_route(text)
    if rule and rule["confidence"] >= 0.88:
        return build_decision(
            intent=rule["intent"],
            emotion=detect_emotion(text),
            confidence=rule["confidence"],
            route_method="rule",
            reason=rule["reason"],
        )

    semantic = semantic_route(text)
    if semantic["confidence"] >= 0.58:
        return build_decision(
            intent=semantic["intent"],
            emotion=detect_emotion(text),
            confidence=semantic["confidence"],
            route_method="semantic",
            reason=semantic["reason"],
        )

    fallback_intent = semantic["intent"] if semantic["confidence"] >= 0.42 else "chat"
    return build_decision(
        intent=fallback_intent,
        emotion=detect_emotion(text),
        confidence=semantic["confidence"],
        route_method="local_fallback",
        reason=semantic["reason"] or "本地路由置信度不足，按安全默认处理。",
    )


async def analyze_query_async(query: str) -> Dict[str, Any]:
    """Route with local layers first, then optional LLM fallback."""

    local_decision = analyze_query(query)
    if local_decision["confidence"] >= 0.58:
        return local_decision

    llm_decision = await llm_route(query)
    if llm_decision:
        return build_decision(
            intent=llm_decision.intent,
            emotion=llm_decision.emotion,
            confidence=llm_decision.confidence,
            route_method="llm",
            reason=llm_decision.reason,
        )
    return local_decision


def rule_route(text: str) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    for intent, patterns in RULE_PATTERNS.items():
        hits = [pattern for pattern in patterns if re.search(pattern, text, re.IGNORECASE)]
        if not hits:
            continue
        confidence = min(0.93 + 0.02 * (len(hits) - 1), 0.98)
        candidate = {
            "intent": intent,
            "confidence": confidence,
            "reason": f"命中高置信规则：{hits[0]}",
        }
        if best is None or candidate["confidence"] > best["confidence"]:
            best = candidate
    return best


def semantic_route(text: str) -> Dict[str, Any]:
    if not text:
        return {"intent": "chat", "confidence": 0.0, "reason": "空输入"}

    query_vector = text_vector(text)
    best_intent: Intent = "chat"
    best_score = 0.0
    best_example = ""

    for spec in INTENT_SPECS:
        for example in spec.examples:
            score = cosine(query_vector, text_vector(normalize_text(example)))
            if score > best_score:
                best_score = score
                best_intent = spec.intent
                best_example = example

    confidence = min(round(best_score, 4), 0.86)
    return {
        "intent": best_intent,
        "confidence": confidence,
        "reason": f"语义最接近样例：{best_example}",
    }


async def llm_route(query: str) -> Optional[LLMIntentDecision]:
    if not llm_available():
        return None

    prompt = (
        "你是智能电商客服系统的 Supervisor。请只做意图分类，不要回答用户。\n"
        "可选 intent：chat, store_scope, fact_query, recommendation, solution_plan, support。\n"
        "分类标准：\n"
        "- chat: 问候、闲聊、问你是谁或能力介绍。\n"
        "- store_scope: 问店铺卖什么、主营什么、有什么商品。\n"
        "- fact_query: 价格、库存、参数、规格、有货等商品事实。\n"
        "- recommendation: 推荐、搭配、适合、买哪个。\n"
        "- solution_plan: 配一套、完整方案、按预算/场景/人群成套配置。\n"
        "- support: 故障、退货、投诉、售后、差评。\n"
        f"用户输入：{query}"
    )

    try:
        model = create_router_llm()
        decision = await model.with_structured_output(LLMIntentDecision).ainvoke(prompt)
        return decision
    except Exception:
        return None


def create_router_llm():
    if settings.AGENT_SERVICE == ServiceType.OLLAMA:
        from langchain_ollama import ChatOllama

        return ChatOllama(model=settings.OLLAMA_AGENT_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0)

    from langchain_deepseek import ChatDeepSeek

    return ChatDeepSeek(
        api_key=settings.DEEPSEEK_API_KEY,
        api_base=settings.DEEPSEEK_BASE_URL,
        model_name=settings.DEEPSEEK_MODEL,
        temperature=0,
        tags=["supervisor_intent_router"],
    )


def llm_available() -> bool:
    if settings.AGENT_SERVICE == ServiceType.OLLAMA:
        return is_port_open(settings.OLLAMA_BASE_URL)
    return bool(settings.DEEPSEEK_API_KEY and not settings.DEEPSEEK_API_KEY.startswith("your_"))


def build_decision(
    *,
    intent: Intent,
    emotion: Emotion,
    confidence: float,
    route_method: str,
    reason: str,
) -> Dict[str, Any]:
    recommendation_allowed = intent in {"fact_query", "recommendation", "solution_plan"} and emotion != "angry"
    route = "retrieval" if intent in {"fact_query", "recommendation", "solution_plan"} else "chat"
    return {
        "intent": intent,
        "emotion": emotion,
        "recommendation_allowed": recommendation_allowed,
        "sales_intensity": sales_intensity(intent, emotion),
        "route": route,
        "confidence": round(float(confidence), 4),
        "route_method": route_method,
        "reason": reason,
    }


def detect_emotion(text: str) -> Emotion:
    if any(word in text for word in ("生气", "垃圾", "差评", "投诉", "烦", "坏了")):
        return "angry"
    if any(word in text for word in ("喜欢", "不错", "想买", "准备买", "预算")):
        return "positive"
    if any(word in text for word in ("纠结", "不知道", "怎么选", "犹豫")):
        return "hesitant"
    return "neutral"


def sales_intensity(intent: str, emotion: str) -> str:
    if emotion == "angry" or intent == "support":
        return "none"
    if intent == "solution_plan":
        return "strong"
    if intent == "recommendation":
        return "medium"
    if intent in {"fact_query", "store_scope"}:
        return "soft"
    return "none"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def text_vector(text: str) -> Counter[str]:
    chars = [char for char in text if not char.isspace()]
    tokens: List[str] = []
    tokens.extend(chars)
    tokens.extend("".join(chars[index : index + 2]) for index in range(max(len(chars) - 1, 0)))
    tokens.extend(re.findall(r"[a-z0-9]+", text))
    return Counter(token for token in tokens if token)


def cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def is_port_open(url: str) -> bool:
    match = re.match(r"^https?://([^:/]+)(?::(\d+))?", url)
    host = match.group(1) if match else "localhost"
    port = int(match.group(2) or 80) if match else 80
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False
