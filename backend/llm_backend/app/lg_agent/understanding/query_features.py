"""Deterministic ecommerce query feature extraction.

Extracts structured purchase-intent signals, ranking objectives, budget,
product categories, and support/negative intent from user queries.

This is NOT an Agent. It is a perception layer that lives between Memory
and Supervisor so the existing routing logic has reliable structured input.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from app.core.logger import get_logger

logger = get_logger(service="query_understanding")

# ── manual alias fallback ─────────────────────────────────────────────────
# Primary aliases come from product data. This table handles common
# abbreviations and synonyms that product data alone cannot infer.

MANUAL_ALIASES: Dict[str, str] = {
    # Smart locks
    "门锁": "智能门锁",
    "锁": "智能门锁",
    "指纹锁": "智能门锁",
    "猫眼": "智能门锁",
    "电子锁": "智能门锁",
    # Cameras
    "摄像头": "智能摄像头",
    "摄像机": "智能摄像头",
    "监控": "智能摄像头",
    "视频监控": "智能摄像头",
    # Cleaning
    "扫地机": "智能清洁",
    "扫地机器人": "智能清洁",
    "扫拖机器人": "智能清洁",
    "拖地机": "智能清洁",
    "扫地": "智能清洁",
    # Lighting
    "灯": "智能灯具",
    "灯具": "智能灯具",
    "主灯": "智能灯具",
    "灯泡": "智能灯具",
    "吸顶灯": "智能灯具",
    # Switches / sockets
    "开关": "智能开关",
    "插座": "智能插座",
    "插头": "智能插座",
    # Speakers
    "音箱": "智能音箱",
    "音响": "智能音箱",
    # Sensors
    "传感器": "智能传感器",
    "感应器": "智能传感器",
    # Curtains
    "窗帘": "智能窗帘",
    "电动窗帘": "智能窗帘",
    # Air / health
    "净化器": "空气净化器",
    "空净": "空气净化器",
    "加湿器": "智能加湿器",
    "空调": "智能空调",
    # Kitchen
    "电饭煲": "智能厨房",
    "破壁机": "智能厨房",
    "冰箱": "智能冰箱",
    "洗衣机": "智能洗衣机",
    # Gateway
    "网关": "智能网关",
    "晾衣架": "智能晾衣架",
    "门铃": "智能门铃",
    # Generic smart-home signals (weak — use with care)
    "智能家居": "",
    "智能设备": "",
    "全屋": "",
}

# ── ranking objective signals ─────────────────────────────────────────────

RANKING_SIGNALS: Dict[str, List[str]] = {
    "lowest_price": ["最便宜", "低价", "便宜点", "便宜", "入门款", "实惠", "平价", "最实惠"],
    "best_value": ["性价比", "划算", "值得买", "不踩坑", "好用不贵", "质优价廉"],
    "premium": ["高端", "顶配", "豪华", "旗舰", "最好", "最高端", "顶级", "贵的"],
    "popular": ["热门", "销量", "大家都买", "畅销", "卖得好"],
}

# ── purchase intent signals ───────────────────────────────────────────────

PURCHASE_SIGNAL_WORDS = [
    "买", "推荐", "选", "挑", "配", "方案",
    "有没有", "有货吗", "库存", "适合", "多少钱",
    "想入手", "准备买", "我要", "需要", "帮我",
    "来一个", "来一台", "搞一个", "入一个",
    "什么牌子", "哪个好", "哪款好", "怎么样",
    "质量", "保修", "参数", "规格",
]

# ── support / negative intent signals ─────────────────────────────────────

SUPPORT_SIGNAL_WORDS = [
    "坏了", "不能用", "退货", "投诉", "差评",
    "生气", "出问题", "售后", "故障", "修",
    "退款", "换货", "质量差", "不好用", "坑",
    "用不了", "连不上", "掉线", "卡顿",
]

# ── price need signals ────────────────────────────────────────────────────

PRICE_NEED_WORDS = ["多少钱", "价格", "价位", "贵不贵", "报价", "什么价"]

# ── stock need signals ────────────────────────────────────────────────────

STOCK_NEED_WORDS = ["有货", "库存", "现货", "缺货", "断货", "有没有"]

# ── budget extraction ─────────────────────────────────────────────────────

BUDGET_PATTERNS = [
    r"预算\s*(\d+(?:\.\d+)?)",
    r"(\d+(?:\.\d+)?)\s*元?\s*(?:以内|以下|之内|左右)",
    r"不超过\s*(\d+(?:\.\d+)?)",
    r"低于\s*(\d+(?:\.\d+)?)",
    r"(\d+(?:\.\d+)?)\s*预算",
    # Chinese numerals: 一千以内, 一千五左右
    r"(一千|两千|三千|五千|一万)\s*(?:以内|左右|以下|预算)?",
]

CN_NUM_MAP = {
    "一千": 1000, "一千五": 1500, "一千以内": 1000, "一千左右": 1000,
    "两千": 2000, "两千五": 2500,
    "三千": 3000, "三千五": 3500,
    "五千": 5000,
    "一万": 10000, "一万五": 15000,
    "一千元": 1000, "一千元以内": 1000,
}


# ── primary public API ────────────────────────────────────────────────────


def extract_query_features(
    query: str,
    products: List[Any] | None = None,
    shopping_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Extract structured ecommerce perception fields from *query*.

    Parameters
    ----------
    query:
        The effective query (already processed by Memory Layer).
    products:
        Optional list of ProductDocument objects for generating category aliases.
    shopping_state:
        Optional shopping state from Memory Layer (may carry prior categories).

    Returns
    -------
    A compact dict safe for trace metadata and Supervisor routing.
    """
    if not query or not query.strip():
        return _empty_features()

    text = query.strip()

    # ── category extraction (from product data + manual fallback) ─────
    alias_map = _build_alias_map(products)
    product_categories = _extract_categories(text, alias_map)

    # ── ranking objective ─────────────────────────────────────────────
    ranking_objective = _extract_ranking_objective(text)

    # ── budget ────────────────────────────────────────────────────────
    budget_max = _extract_budget(text)
    # Also check shopping_state for budget.
    if budget_max is None and shopping_state:
        budget_max = _safe_float(shopping_state.get("budget_max"))

    # ── purchase intent ───────────────────────────────────────────────
    purchase_signals = _match_signals(text, PURCHASE_SIGNAL_WORDS)
    has_purchase_intent = bool(purchase_signals) or bool(product_categories)

    # ── support intent ────────────────────────────────────────────────
    support_signals = _match_signals(text, SUPPORT_SIGNAL_WORDS)
    support_intent = bool(support_signals)

    # ── price / stock needs ───────────────────────────────────────────
    need_price = any(w in text for w in PRICE_NEED_WORDS)
    need_stock = any(w in text for w in STOCK_NEED_WORDS)

    # ── emotion ───────────────────────────────────────────────────────
    emotion = _detect_emotion(text)

    # ── intent signals summary ────────────────────────────────────────
    intent_signals: List[str] = []
    if purchase_signals:
        intent_signals.extend(purchase_signals)
    if support_signals:
        intent_signals.append("support")
    if ranking_objective:
        intent_signals.append("ranking")
    if budget_max is not None:
        intent_signals.append("budget")
    if need_price:
        intent_signals.append("price")
    if need_stock:
        intent_signals.append("stock")

    # Merge categories from shopping_state (previous turns).
    all_categories = list(dict.fromkeys(product_categories))
    if shopping_state:
        prev_cats = shopping_state.get("product_categories") or []
        for cat in prev_cats:
            if cat and cat not in all_categories:
                all_categories.append(cat)

    # Merge ranking_objective from shopping_state.
    if not ranking_objective and shopping_state:
        ranking_objective = shopping_state.get("ranking_objective") or None

    return {
        "has_purchase_intent": has_purchase_intent,
        "intent_signals": intent_signals,
        "ranking_objective": ranking_objective,
        "budget_max": budget_max,
        "product_categories": all_categories,
        "need_price": need_price,
        "need_stock": need_stock,
        "support_intent": support_intent,
        "emotion": emotion,
    }


# ── category alias generation ─────────────────────────────────────────────


def _build_alias_map(products: List[Any] | None) -> Dict[str, str]:
    """Build alias→canonical-category mapping from product data + manual table.

    Primary: product data categories and product-name tokens.
    Fallback: MANUAL_ALIASES.
    """
    alias_map: Dict[str, str] = dict(MANUAL_ALIASES)

    if not products:
        return alias_map

    # Collect all unique categories and product names.
    categories: Set[str] = set()
    name_tokens: Set[str] = set()
    for p in products:
        cat = getattr(p, "category", "") or ""
        name = getattr(p, "product_name", "") or ""
        if cat:
            categories.add(cat)
        if name:
            # Split product names into 2-3 char meaningful tokens.
            for tok in re.findall(r"[一-鿿]{2,4}", name):
                name_tokens.add(tok)

    # Each category name is an alias for itself.
    for cat in categories:
        alias_map[cat] = cat

    # For each category, also add trimmed aliases (e.g. "智能门锁" → "门锁").
    for cat in categories:
        # Remove "智能" prefix to get common abbreviation.
        if cat.startswith("智能") and len(cat) > 2:
            short = cat[2:]
            if short not in alias_map:
                alias_map[short] = cat

    # Map common product-name tokens to their categories.
    for p in products:
        cat = getattr(p, "category", "") or ""
        name = getattr(p, "product_name", "") or ""
        if not cat or not name:
            continue
        # Extract 2-4 char tokens from product name that might be aliases.
        for tok in re.findall(r"[一-鿿]{2,4}", name):
            # Only add if not already mapped and the token looks like a
            # category-level term (not a brand or model number).
            if tok not in alias_map and tok != cat and len(tok) >= 2:
                # Check that this token is distinctive enough.
                if tok not in {"华为", "小米", "美的", "海尔", "公牛", "欧普",
                                "绿米", "鹿客", "萤石", "石头", "科沃斯",
                                "德施曼", "凯迪仕", "易来", "智选", "云米"}:
                    alias_map[tok] = cat

    # Manual table always wins (already set first).
    return alias_map


def _extract_categories(text: str, alias_map: Dict[str, str]) -> List[str]:
    """Scan *text* for known aliases and return canonical category names.

    Longer aliases are matched first to avoid partial matches.
    """
    found: List[str] = []
    # Sort by length descending so "扫地机器人" matches before "扫地".
    aliases_sorted = sorted(alias_map.keys(), key=len, reverse=True)
    matched_positions: Set[int] = set()

    for alias in aliases_sorted:
        if not alias:
            continue
        # Find all occurrences of this alias in text.
        for match in re.finditer(re.escape(alias), text):
            start, end = match.span()
            # Skip if this position was already matched by a longer alias.
            if any(start <= p < end for p in matched_positions):
                continue
            canonical = alias_map[alias]
            if canonical and canonical not in found:
                found.append(canonical)
            # Mark positions as consumed to avoid "门锁" matching inside "智能门锁".
            for p in range(start, end):
                matched_positions.add(p)
            break  # One match per alias is enough.

    return found


# ── signal extraction helpers ─────────────────────────────────────────────


def _extract_ranking_objective(text: str) -> Optional[str]:
    """Return the strongest matching ranking objective, or None."""
    for objective, signals in RANKING_SIGNALS.items():
        if any(s in text for s in signals):
            return objective
    return None


def _extract_budget(text: str) -> Optional[float]:
    """Extract budget_max from text patterns and Chinese numerals."""
    # Try regex patterns first.
    for pattern in BUDGET_PATTERNS:
        m = re.search(pattern, text)
        if m:
            raw = m.group(1)
            if raw in CN_NUM_MAP:
                return float(CN_NUM_MAP[raw])
            try:
                return float(raw)
            except ValueError:
                continue

    # Try Chinese numeral patterns.
    cn_patterns = [
        (r"一千\s*五", 1500), (r"两千\s*五", 2500), (r"三千\s*五", 3500),
        (r"一千", 1000), (r"两千", 2000), (r"三千", 3000),
        (r"四千", 4000), (r"五千", 5000), (r"一万", 10000),
        (r"几百", 999), (r"几百块", 999),
    ]
    for pattern, amount in cn_patterns:
        if re.search(pattern, text):
            # Only return if there's a budget constraint context nearby.
            if re.search(r"(?:以内|左右|以下|预算|不超过|之内)", text):
                return float(amount)

    return None


def _match_signals(text: str, word_list: List[str]) -> List[str]:
    """Return subset of *word_list* that appear in *text*."""
    return [w for w in word_list if w in text]


def _detect_emotion(text: str) -> str:
    if any(w in text for w in ("生气", "垃圾", "差评", "投诉", "烦", "坏了", "坑", "退款")):
        return "angry"
    if any(w in text for w in ("喜欢", "不错", "想买", "准备买", "预算")):
        return "positive"
    if any(w in text for w in ("纠结", "不知道", "怎么选", "犹豫")):
        return "hesitant"
    return "neutral"


# ── helpers ───────────────────────────────────────────────────────────────


def _empty_features() -> Dict[str, Any]:
    return {
        "has_purchase_intent": False,
        "intent_signals": [],
        "ranking_objective": None,
        "budget_max": None,
        "product_categories": [],
        "need_price": False,
        "need_stock": False,
        "support_intent": False,
        "emotion": "neutral",
    }


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
