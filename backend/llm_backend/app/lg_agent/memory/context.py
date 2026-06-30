"""Context-aware working memory layer.

Placed before Supervisor in the main pipeline. Uses deterministic extraction
from the frontend-provided `messages` to carry shopping context into short
follow-up turns, fixing failures like:

    User: 我想买智能门锁和摄像头
    User: 我主要在意性价比

Without this layer the backend may treat the second turn as a standalone query
and drift to unrelated products.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ── follow-up signal detection ──────────────────────────────────────────

# Each entry: (regex, ranking_objective | None, preference_label)
FOLLOWUP_SIGNALS: List[tuple] = [
    (r"性价比|划算|值得买|哪个更好|哪个更值|更值[得的]买", "best_value", "性价比优先"),
    (r"便宜|低价|实惠|入门款|预算低|便宜点|最便宜|便宜[的的]|省点钱", "lowest_price", "低价优先"),
    (r"高质量|高端|贵的|旗舰|顶配|最好[的的]|品质好|质量好", "highest_rating", "高品质优先"),
    (r"销量|热门|流行|大家都在买|卖得好|多人买", "highest_sales", "销量优先"),
    (r"爸妈|老人|父母|长辈|给父母|送长辈|家里老人|老人家", None, "老人使用"),
    (r"新房|装修|全屋|新家|刚装修|毛坯", None, "新房装修"),
    (r"小孩|宝宝|婴儿|儿童|母婴|孩子|幼儿", None, "母婴/儿童"),
    (r"宠物|猫|狗|主子|毛孩子|猫咪|狗狗", None, "宠物友好"),
]

BRAND_PATTERN = (
    r"小米|华为|华为智选|鹿客|萤石|美的|海尔|Aqara|绿米|"
    r"公牛|欧普|石头|科沃斯|Yeelight|德施曼|凯迪仕|360|"
    r"追觅|云鲸|米家|小爱"
)

BUDGET_PATTERNS: List[tuple] = [
    (r"预算\s*(\d+(?:\.\d+)?)", "budget"),
    (r"(\d+(?:\.\d+)?)\s*元?\s*(?:以内|以下|之内|左右)", "max"),
    (r"不超过\s*(\d+(?:\.\d+)?)", "max"),
    (r"高于\s*(\d+(?:\.\d+)?)", "min"),
    (r"(\d+(?:\.\d+)?)\s*元?\s*(?:以上|起)", "min"),
]

# Queries longer than this (chars, after stripping) are unlikely to be
# short follow-ups unless they start with explicit follow-up markers.
MAX_FOLLOWUP_LENGTH = 28

# Minimum prior messages (user+assistant) to attempt context extraction.
MIN_PRIOR_USER_MESSAGES = 1

# Maximum recent messages to use for shopping topic extraction.
# Longer histories are truncated to the most recent window to keep
# memory lightweight and avoid drift from old context.
RECENT_WINDOW_SIZE = 6


async def build_memory_context(
    current_query: str,
    messages: Optional[List[Dict[str, str]]] = None,
    *,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build shopping context from conversation history + session memory.

    Args:
        current_query: The latest user query.
        messages: Full conversation history from the frontend, ordered
            chronologically.  The last user message should match
            *current_query*.
        session_id: Persistent session id for cross-turn memory.

    Returns:
        A dict with:
        - ``raw_query``: the original user query unchanged.
        - ``effective_query``: context-enriched query for downstream agents.
        - ``memory_used``: whether prior context was merged in.
        - ``shopping_state``: structured requirements dict (may be empty).
        - ``last_recommended_ids``: product ids from previous turn.
    """
    # ── load persisted session memory (V3) ─────────────────────────
    session_mem = None
    if session_id:
        try:
            from app.lg_agent.memory.store import get_session_store
            store = await get_session_store()
            session_mem = await store.load(session_id)
        except Exception:
            session_mem = None

    clean = (current_query or "").strip()
    result: Dict[str, Any] = {
        "raw_query": clean,
        "effective_query": clean,
        "memory_used": False,
        "shopping_state": dict(session_mem.shopping_state) if session_mem else {},
        "recent_window_size": RECENT_WINDOW_SIZE,
        "recent_message_count": 0,
        "hint_text": "",
        "session_id": session_id,
        "last_recommended_ids": list(session_mem.last_recommended_ids) if session_mem else [],
    }

    if not clean:
        # Even with empty query, carry forward the persisted state.
        if session_mem and session_mem.shopping_state:
            _enrich_effective_query_from_state(result, session_mem.shopping_state)
            result["memory_used"] = True
            result["hint_text"] = _build_hint_text(session_mem.shopping_state)
        return result

    msgs = messages or []
    total_msg_count = len(msgs)

    # Truncate to recent window to avoid drift from stale context.
    if len(msgs) > RECENT_WINDOW_SIZE:
        msgs = msgs[-RECENT_WINDOW_SIZE:]

    result["recent_window_size"] = RECENT_WINDOW_SIZE
    result["recent_message_count"] = min(total_msg_count, RECENT_WINDOW_SIZE)

    # ── V3: LLM structured compression when exceeding window ─────────
    needs_compression = total_msg_count > RECENT_WINDOW_SIZE
    result["needs_compression"] = needs_compression
    if needs_compression:
        # Fire-and-forget: compress in background, save to session.
        _schedule_llm_compression(clean, messages, session_id, session_mem)

    prior_user_count = sum(1 for m in msgs if m.get("role") == "user")
    # The last user message IS current_query, so we need at least 2 user
    # messages total to have prior shopping context.
    if prior_user_count < MIN_PRIOR_USER_MESSAGES + 1:
        # Still try to inherit session-persisted state for standalone queries.
        if session_mem and session_mem.shopping_state:
            _enrich_effective_query_from_state(result, session_mem.shopping_state)
            result["memory_used"] = True
            result["hint_text"] = _build_hint_text(session_mem.shopping_state)
        return result

    # Detect whether *clean* reads like a short follow-up.
    followup = _detect_followup(clean)
    if followup is None:
        # No follow-up detected, but session state may still apply.
        if session_mem and session_mem.shopping_state:
            _enrich_effective_query_from_state(result, session_mem.shopping_state)
            result["memory_used"] = True
            result["hint_text"] = _build_hint_text(session_mem.shopping_state)
        return result

    # Extract the prior shopping topic from history (excludes current_query).
    prior = _extract_shopping_topic(msgs)
    if not prior.get("product_categories") and not prior.get("scenario"):
        # No prior shopping topic to carry forward — pass through.
        return result

    shopping_state = _merge_shopping_state(prior, followup)
    effective_query = _build_effective_query(prior, clean)

    result["effective_query"] = effective_query
    result["memory_used"] = True
    result["shopping_state"] = shopping_state
    result["hint_text"] = _build_hint_text(shopping_state)
    return result


# ── follow-up detection ─────────────────────────────────────────────────


def _schedule_llm_compression(
    current_query: str,
    messages: Optional[List[Dict[str, str]]],
    session_id: Optional[str],
    session_mem: Any,
) -> None:
    """Fire-and-forget LLM compression of long conversation history."""
    if not messages or not session_id:
        return
    try:
        import asyncio
        from app.lg_agent.llm_client import generate_text, _parse_json

        async def _compress() -> None:
            existing_summary = (
                session_mem.summary if session_mem else None
            )
            msg_text = "\n".join(
                f"[{m.get('role','user')}]: {m.get('content','')[:200]}"
                for m in messages[-20:]
            )
            prev = f"\nPrevious summary: {existing_summary}\n" if existing_summary else ""

            try:
                response = await generate_text(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You are a context summarizer for a Chinese ecommerce shopping assistant.\n"
                                "Output ONLY valid JSON. No markdown, no prose.\n"
                                "Schema: {\"active_task\": string, \"stable_preferences\": string[], "
                                "\"hard_constraints\": string[], \"negative_feedback\": string[], "
                                "\"latest_intent\": string}.\n"
                                "Extract the ongoing shopping task, stable preferences, "
                                "hard budget/category constraints, negative feedback, "
                                "and latest user intent.\n"
                                "Keep it short. Each array at most 3 items."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Recent conversation:\n{msg_text}\n{prev}"
                                f"Latest query: {current_query}\n"
                                f"Output JSON only."
                            ),
                        },
                    ],
                    temperature=0.2,
                    max_tokens=300,
                    tags=["memory_compression"],
                )
                summary_data = _parse_json(response)
            except Exception:
                summary_data = None

            if summary_data:
                from app.lg_agent.memory.store import SessionMemory, get_session_store
                store = await get_session_store()
                mem = await store.load(session_id)
                if mem is None:
                    mem = SessionMemory(session_id)
                mem.summary = summary_data
                await store.save(mem)

        asyncio.ensure_future(_compress())
    except Exception:
        pass


def _detect_followup(query: str) -> Optional[Dict[str, Any]]:
    """Return extracted follow-up signals, or *None* if this is standalone."""

    # Fast path: short query with follow-up keywords.
    if len(query) > MAX_FOLLOWUP_LENGTH and not _has_followup_marker(query):
        return None

    signals: Dict[str, Any] = {}

    for pattern, ranking_obj, label in FOLLOWUP_SIGNALS:
        if re.search(pattern, query):
            if ranking_obj:
                signals["ranking_objective"] = ranking_obj
            if label:
                signals.setdefault("preferences", []).append(label)

    brand = re.search(BRAND_PATTERN, query)
    if brand:
        signals["brand_preference"] = brand.group()

    for pat, kind in BUDGET_PATTERNS:
        m = re.search(pat, query)
        if m:
            amount = float(m.group(1))
            if kind == "max":
                signals["budget_max"] = amount
            elif kind == "min":
                signals["budget_min"] = amount
            else:
                # bare "预算 NNN" — treat as max
                signals["budget_max"] = amount
            break

    # Map preference labels → target_user / scenario
    prefs = signals.get("preferences", [])
    if "老人使用" in prefs:
        signals["target_user"] = "老人"
    if "新房装修" in prefs:
        signals["scenario"] = "新房装修"
    if "母婴/儿童" in prefs:
        signals["target_user"] = "母婴/儿童"
    if "宠物友好" in prefs:
        signals["scenario"] = "宠物家庭"

    # Normalise preferences.
    if "preferences" in signals:
        signals["preferences"] = list(dict.fromkeys(signals["preferences"]))

    if not signals:
        return None
    return {k: v for k, v in signals.items() if v not in (None, [], "")}


def _has_followup_marker(query: str) -> bool:
    """Allow a longer query to still be treated as follow-up."""
    markers = [
        r"^(那|那么|还|还是|或者|就|就是|另外|再|再加|还有|有没有)",
        r"(不要|去掉|换[一一个]|替[一一个]|改成?[一一个]?)",
    ]
    return any(re.search(m, query) for m in markers)


# ── shopping topic extraction ───────────────────────────────────────────


def _extract_shopping_topic(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Pull the recent shopping topic from prior messages.

    User messages are weighted higher than assistant messages because
    assistant replies often repeat product names from recommendations
    that should not be mistaken for user intent.
    """
    user_texts: List[str] = []
    assistant_texts: List[str] = []

    for msg in messages:
        role = (msg.get("role") or "").lower()
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            user_texts.append(content)
        elif role == "assistant":
            assistant_texts.append(content)

    # Remove the last user message — it's the current query.
    if user_texts:
        user_texts.pop()

    topic: Dict[str, Any] = {
        "product_categories": [],
        "scenario": None,
        "budget_min": None,
        "budget_max": None,
        "brand_preference": None,
        "target_user": None,
    }

    # Extract from user messages first (higher weight).
    for text in user_texts:
        _merge_into(
            topic,
            _parse_categories(text),
            _parse_budget(text),
            _parse_brand(text),
            _parse_scenario(text),
            _parse_target_user(text),
        )

    # Fill remaining gaps from assistant messages (lowest weight).
    # Only fill structural data (categories, budget); do NOT extract
    # scenario / target_user / brand from assistant replies — they often
    # contain product names from past recommendations that can mislead.
    for text in assistant_texts:
        _merge_into_gaps(
            topic,
            _parse_categories(text),
            _parse_budget(text),
        )

    return topic


# ── parsers ─────────────────────────────────────────────────────────────

_CATEGORY_MAP: Dict[str, str] = {
    "智能门锁": r"门锁|猫眼|指纹锁|密码锁|智能锁",
    "智能摄像头": r"摄像头|摄像机|监控|看家|云台",
    "智能传感器": r"传感器|人体感应|门磁|烟雾|水浸",
    "智能音箱": r"音箱|音响|小爱|天猫精灵|HomePod|小度",
    "智能灯具": r"灯\b|灯具|吸顶灯|灯带|灯泡|筒灯|射灯",
    "智能插座": r"插座|插排|排插|墙插",
    "智能开关": r"开关|面板",
    "智能清洁": r"扫地|拖地|扫地机|扫拖|洗地机|吸尘器",
    "空气净化器": r"净化器|空气净化|除甲醛|除PM|新风",
    "智能加湿器": r"加湿器|加湿",
    "智能厨房": r"厨房|电饭煲|破壁机|烤箱|微波炉|电磁炉|空气炸锅",
    "智能冰箱": r"冰箱|冰柜|冷藏",
    "智能空调": r"空调|冷暖|变频",
    "智能洗衣机": r"洗衣机|烘干机|洗烘",
    "智能窗帘": r"窗帘|电动窗帘|卷帘|百叶",
    "智能晾衣架": r"晾衣架|晾衣杆|晾晒",
    "智能网关": r"网关|中枢|Hub|Zigbee|多模",
}


def _parse_categories(text: str) -> Dict[str, Any]:
    cats: List[str] = []
    for category, pattern in _CATEGORY_MAP.items():
        if re.search(pattern, text):
            cats.append(category)
    return {"product_categories": list(dict.fromkeys(cats))}


def _parse_budget(text: str) -> Dict[str, Any]:
    for pat, kind in BUDGET_PATTERNS:
        m = re.search(pat, text)
        if m:
            amount = float(m.group(1))
            if kind in ("min",):
                return {"budget_min": amount, "budget_max": None}
            return {"budget_max": amount, "budget_min": None}
    return {"budget_max": None, "budget_min": None}


def _parse_brand(text: str) -> Dict[str, Any]:
    m = re.search(BRAND_PATTERN, text)
    return {"brand_preference": m.group() if m else None}


def _parse_scenario(text: str) -> Dict[str, Any]:
    if any(w in text for w in ("安防", "安全", "看家", "门口", "入户", "防盗")):
        return {"scenario": "家庭安防"}
    if any(w in text for w in ("新房", "装修", "全屋", "新家", "毛坯")):
        return {"scenario": "新房装修"}
    if any(w in text for w in ("老人", "爸妈", "父母", "长辈", "养老")):
        return {"scenario": "老人看护"}
    if any(w in text for w in ("清洁", "扫地", "拖地", "懒人")):
        return {"scenario": "清洁护理"}
    if any(w in text for w in ("空气", "净化", "加湿", "母婴", "过敏", "甲醛")):
        return {"scenario": "空气健康"}
    if any(w in text for w in ("厨房", "做饭", "烹饪", "下厨")):
        return {"scenario": "智能厨房"}
    if any(w in text for w in ("宠物", "猫", "狗")):
        return {"scenario": "宠物家庭"}
    return {"scenario": None}


def _parse_target_user(text: str) -> Dict[str, Any]:
    if any(w in text for w in ("老人", "爸妈", "父母", "长辈", "养老")):
        return {"target_user": "老人"}
    if any(w in text for w in ("小孩", "宝宝", "婴儿", "儿童", "母婴", "幼儿")):
        return {"target_user": "母婴/儿童"}
    if any(w in text for w in ("租客", "租房", "出租屋")):
        return {"target_user": "租客"}
    return {"target_user": None}


# ── merge helpers ───────────────────────────────────────────────────────


def _merge_into(topic: Dict[str, Any], *sources: Dict[str, Any]) -> None:
    """Merge from parsed sources; overwrite None/empty slots."""
    for src in sources:
        for key, value in src.items():
            if key == "product_categories":
                for cat in value or []:
                    if cat not in topic[key]:
                        topic[key].append(cat)
            elif value is not None and value != [] and value != "":
                topic[key] = value


def _merge_into_gaps(topic: Dict[str, Any], *sources: Dict[str, Any]) -> None:
    """Fill only empty slots (used for lower-weight assistant messages)."""
    for src in sources:
        for key, value in src.items():
            if key == "product_categories":
                if not topic[key]:
                    topic[key] = list(dict.fromkeys(value or []))
            elif value is not None and value != [] and value != "":
                if topic.get(key) in (None, [], ""):
                    topic[key] = value


def _merge_shopping_state(
    prior: Dict[str, Any],
    followup: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the final shopping_state by overlaying follow-up on prior."""
    state: Dict[str, Any] = {}

    # Copy prior topic fields.
    for key in (
        "product_categories",
        "scenario",
        "target_user",
        "budget_min",
        "budget_max",
        "brand_preference",
    ):
        if prior.get(key) not in (None, [], ""):
            state[key] = prior[key]

    # Overlay follow-up signals (they take priority).
    for key in (
        "ranking_objective",
        "brand_preference",
        "budget_min",
        "budget_max",
        "target_user",
        "scenario",
    ):
        val = followup.get(key)
        if val not in (None, [], ""):
            state[key] = val

    # Compile preferences list.
    prefs: List[str] = list(followup.get("preferences", []))
    obj_labels = {
        "best_value": "性价比优先",
        "lowest_price": "低价优先",
        "highest_rating": "高品质优先",
        "highest_sales": "销量优先",
    }
    if "ranking_objective" in state and not any(
        p in prefs for p in obj_labels.values()
    ):
        label = obj_labels.get(state["ranking_objective"])
        if label:
            prefs.append(label)
    if prefs:
        state["preferences"] = list(dict.fromkeys(prefs))

    # Default ranking objective.
    state.setdefault("ranking_objective", "balanced")

    return state


def _build_effective_query(
    prior: Dict[str, Any],
    current_query: str,
) -> str:
    """Compose an effective query that combines prior topic + current follow-up."""
    parts: List[str] = []

    categories = prior.get("product_categories") or []
    if categories:
        parts.append(f"我想买{'、'.join(categories)}")

    if prior.get("scenario"):
        parts.append(f"场景：{prior['scenario']}")

    if prior.get("target_user"):
        parts.append(f"给{prior['target_user']}用")

    if prior.get("budget_max") is not None:
        parts.append(f"预算{int(prior['budget_max'])}元以内")

    # Current follow-up.
    parts.append(current_query)

    return "，".join(parts)


def _enrich_effective_query_from_state(
    result: Dict[str, Any],
    shopping_state: Dict[str, Any],
) -> None:
    """Build effective_query from persisted shopping_state when no follow-up detected."""
    parts: list[str] = []
    cat = shopping_state.get("active_category")
    if cat:
        parts.append(f"用户正在看{cat}")
    budget = shopping_state.get("budget_max")
    if budget:
        parts.append(f"预算约{budget}")
    ranking = shopping_state.get("ranking_objective")
    if ranking == "best_value":
        parts.append("关注性价比")
    elif ranking == "lowest_price":
        parts.append("关注低价")
    if parts:
        result["effective_query"] = f"{result['raw_query']}（{'，'.join(parts)}）"


def _build_hint_text(shopping_state: Dict[str, Any]) -> str:
    """Build a user-facing hint like '本轮理解：智能门锁 + 摄像头，性价比优先'.

    Returns an empty string when there is not enough structured state to
    form a meaningful hint.
    """
    if not shopping_state:
        return ""

    categories = shopping_state.get("product_categories") or []
    if not categories:
        return ""

    parts: List[str] = ["本轮理解："]

    # Product categories: 智能门锁 + 摄像头
    parts.append(" + ".join(categories[:3]))

    # Preference or ranking objective
    prefs = shopping_state.get("preferences") or []
    if prefs:
        parts.append("，" + prefs[0])
    else:
        obj_labels = {
            "best_value": "，性价比优先",
            "lowest_price": "，低价优先",
            "highest_rating": "，高品质优先",
            "highest_sales": "，销量优先",
        }
        obj = shopping_state.get("ranking_objective", "")
        label = obj_labels.get(obj)
        if label:
            parts.append(label)

    # Budget
    budget_max = shopping_state.get("budget_max")
    if budget_max is not None:
        parts.append(f"，预算{int(budget_max)}元以内")

    # Brand
    brand = shopping_state.get("brand_preference")
    if brand:
        parts.append(f"，偏好{brand}")

    return "".join(parts)
