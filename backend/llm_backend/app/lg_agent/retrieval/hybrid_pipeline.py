"""Hybrid Product RAG pipeline owned by Retrieval Agent."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.core.config import settings
from app.lg_agent.retrieval.reranker_client import RerankerClient
from app.lg_agent.tools.bm25_tool import BM25ProductRetriever
from app.lg_agent.tools.qdrant_tool import QdrantProductRetriever


@dataclass
class RetrievalConstraints:
    categories: List[str] = field(default_factory=list)
    brand: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    prefer_low_price: bool = False
    stock_required: bool = False
    use_case: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


class HybridProductRetriever:
    """Complete Hybrid RAG pipeline for product fact retrieval.

    Current local path:
    query constraints -> Qdrant dense retrieval -> BM25 sparse retrieval ->
    metadata filter -> weighted fusion -> reranker/fallback ranking.
    """

    def __init__(
        self,
        dense_retriever: QdrantProductRetriever | None = None,
        sparse_retriever: BM25ProductRetriever | None = None,
        reranker: RerankerClient | None = None,
    ):
        self.dense_retriever = dense_retriever or QdrantProductRetriever()
        self.sparse_retriever = sparse_retriever or BM25ProductRetriever()
        self.reranker = reranker or RerankerClient()

    async def retrieve(
        self, query: str, top_k: int | None = None, *, ranking_objective: str | None = None
    ) -> Dict[str, Any]:
        constraints = parse_constraints(query)
        rewritten_query = rewrite_query(query, constraints)

        dense = _safe_call(lambda: self.dense_retriever.search(rewritten_query, settings.RETRIEVAL_DENSE_TOP_K))
        sparse = _safe_call(lambda: self.sparse_retriever.search(rewritten_query, settings.RETRIEVAL_SPARSE_TOP_K))

        merged = merge_candidates(dense, sparse)
        filtered = metadata_filter(merged, constraints)
        fused = score_fusion(filtered)
        pre_rerank_limit = max(settings.RETRIEVAL_RERANK_TOP_K * 3, settings.RETRIEVAL_RERANK_TOP_K)
        reranked = await self.reranker.rerank(
            rewritten_query,
            fused[:pre_rerank_limit],
            top_k or settings.RETRIEVAL_RERANK_TOP_K,
        )
        reranked = ensure_category_coverage(reranked, fused, constraints, top_k or settings.RETRIEVAL_RERANK_TOP_K)
        if ranking_objective == "lowest_price" or constraints.prefer_low_price:
            reranked = sort_by_low_price(reranked)
        elif ranking_objective == "best_value":
            reranked = sort_by_best_value(reranked)
        elif ranking_objective == "premium":
            reranked = sort_by_premium(reranked)
        elif ranking_objective == "popular":
            reranked = sort_by_popular(reranked)
        return {
            "query": query,
            "rewritten_query": rewritten_query,
            "constraints": constraints.raw,
            "candidates": reranked,
            "fact_summary": build_fact_summary(reranked),
        }


def parse_constraints(query: str) -> RetrievalConstraints:
    text = query.strip()
    constraints = RetrievalConstraints(raw={})

    categories = []
    for alias, normalized in CATEGORY_ALIASES.items():
        if alias in text:
            categories.append(normalized)
    constraints.categories = list(dict.fromkeys(categories))
    if constraints.categories:
        constraints.raw["categories"] = constraints.categories

    for brand in BRANDS:
        if brand.lower() in text.lower():
            constraints.brand = brand
            constraints.raw["brand"] = brand
            break

    price_max = _extract_price_max(text)
    if price_max is not None:
        constraints.price_max = price_max
        constraints.raw["price_max"] = price_max

    price_min = _extract_price_min(text)
    if price_min is not None:
        constraints.price_min = price_min
        constraints.raw["price_min"] = price_min

    if any(word in text for word in ("最便宜", "便宜", "低价", "实惠", "入门款", "预算友好")):
        constraints.prefer_low_price = True
        constraints.raw["prefer_low_price"] = True

    if any(word in text for word in ("有货", "库存", "现货")):
        constraints.stock_required = True
        constraints.raw["stock_required"] = True

    constraints.use_case = _extract_use_case(text)
    if constraints.use_case:
        constraints.raw["use_case"] = constraints.use_case
        if not constraints.categories:
            constraints.categories = _categories_for_use_case(constraints.use_case)
            constraints.raw["categories"] = constraints.categories

    return constraints


def rewrite_query(query: str, constraints: RetrievalConstraints) -> str:
    parts = [query]
    parts.extend(constraints.categories)
    if constraints.brand:
        parts.append(constraints.brand)
    if constraints.use_case:
        parts.append(constraints.use_case)
    if constraints.price_max:
        parts.append(f"{int(constraints.price_max)}元以内")
    if constraints.stock_required:
        parts.append("有库存")
    return " ".join(dict.fromkeys(part for part in parts if part))


def merge_candidates(dense: List[Dict[str, Any]], sparse: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for item in dense + sparse:
        pid = str(item.get("product_id") or item.get("ProductID") or "")
        if not pid:
            continue
        current = merged.setdefault(pid, {"product_id": pid})
        current.update({k: v for k, v in item.items() if v not in ("", None)})
        current["product_id"] = pid
        current["dense_score"] = max(_to_float(current.get("dense_score")), _to_float(item.get("dense_score")))
        current["bm25_score"] = max(_to_float(current.get("bm25_score")), _to_float(item.get("bm25_score")))
        current["document_text"] = candidate_text(current)
    return list(merged.values())


def metadata_filter(candidates: List[Dict[str, Any]], constraints: RetrievalConstraints) -> List[Dict[str, Any]]:
    filtered = []
    for item in candidates:
        metadata_score = 1.0
        category = str(item.get("category", ""))
        supplier = str(item.get("supplier", ""))
        name = str(item.get("product_name", ""))
        brand = str(item.get("brand", ""))
        searchable = " ".join(
            str(item.get(key, ""))
            for key in ("description", "features", "use_cases", "target_users", "tags")
        )
        price = _to_float(item.get("price"))
        stock = _to_float(item.get("stock"))

        if constraints.categories and not any(c in category or c in name or c in searchable for c in constraints.categories):
            continue
        if constraints.brand and constraints.brand not in supplier and constraints.brand not in name and constraints.brand not in brand:
            metadata_score -= 0.2
        if constraints.price_max is not None and price > constraints.price_max:
            continue
        if constraints.price_min is not None and price < constraints.price_min:
            continue
        if constraints.stock_required and stock <= 0:
            continue
        if constraints.use_case and constraints.use_case in searchable:
            metadata_score += 0.1
        if stock <= 0:
            metadata_score -= 0.3

        item["metadata_score"] = round(max(min(metadata_score, 1.0), 0.0), 4)
        filtered.append(item)
    return filtered


def score_fusion(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for item in candidates:
        dense_score = _to_float(item.get("dense_score"))
        bm25_score = _to_float(item.get("bm25_score"))
        metadata_score = _to_float(item.get("metadata_score"))
        business_score = _normalize_score(_to_float(item.get("business_weight")))
        item["fusion_score"] = round(
            0.40 * dense_score + 0.30 * bm25_score + 0.20 * metadata_score + 0.10 * business_score,
            4,
        )
        item["document_text"] = candidate_text(item)
    candidates.sort(key=lambda x: x.get("fusion_score", 0), reverse=True)
    return candidates


def ensure_category_coverage(
    reranked: List[Dict[str, Any]],
    fused: List[Dict[str, Any]],
    constraints: RetrievalConstraints,
    top_k: int,
) -> List[Dict[str, Any]]:
    """Keep multi-category queries from collapsing into one dominant category."""

    if len(constraints.categories) <= 1 or not reranked:
        return reranked[:top_k]

    selected: List[Dict[str, Any]] = []
    selected_ids: set[str] = set()

    for category in constraints.categories:
        item = _best_for_category(reranked, category) or _best_for_category(fused, category)
        if not item:
            continue
        pid = str(item.get("product_id") or "")
        if pid and pid not in selected_ids:
            selected.append(item)
            selected_ids.add(pid)

    for item in reranked:
        pid = str(item.get("product_id") or "")
        if pid and pid in selected_ids:
            continue
        selected.append(item)
        if pid:
            selected_ids.add(pid)
        if len(selected) >= top_k:
            break

    return selected[:top_k]


def sort_by_low_price(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: (
            _to_float(item.get("price")) <= 0,
            _to_float(item.get("price")),
            -_to_float(item.get("retrieval_score")),
        ),
    )


def sort_by_best_value(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank by value: prefer reasonable price with high quality signals.

    Uses a simple quality/price heuristic: higher rating + review_count
    relative to price gets priority.
    """
    return sorted(
        candidates,
        key=lambda item: (
            # Penalise items with no price or zero price.
            _to_float(item.get("price")) <= 0,
            # Value score: (rating * review_weight + retrieval) / price_ratio
            -(_value_score(item)),
        ),
    )


def sort_by_premium(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank by premium signals: higher price + high rating first."""
    return sorted(
        candidates,
        key=lambda item: (
            -_to_float(item.get("rating", 0)),
            -_to_float(item.get("price")),
            -_to_float(item.get("retrieval_score")),
        ),
    )


def sort_by_popular(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank by popularity: sales volume + review count."""
    return sorted(
        candidates,
        key=lambda item: (
            -_to_float(item.get("sales_volume", 0)),
            -_to_float(item.get("review_count", 0)),
            -_to_float(item.get("retrieval_score")),
        ),
    )


def _value_score(item: Dict[str, Any]) -> float:
    """Compute a simple quality/price ratio for best_value ranking."""
    rating = _to_float(item.get("rating", 3.0))
    review_count = min(_to_float(item.get("review_count", 0)), 5000)
    sales = min(_to_float(item.get("sales_volume", 0)), 10000)
    retrieval = _to_float(item.get("retrieval_score", 0))
    price = _to_float(item.get("price", 1))
    if price <= 0:
        price = 1.0

    # Quality signal from rating + social proof.
    quality = rating * 0.6 + (review_count / 5000) * 0.2 + (sales / 10000) * 0.1 + retrieval * 0.1
    # Value = quality relative to log(price) so cheap-but-good beats expensive-but-good.
    return quality / (1.0 + (price / 1000.0))


def _best_for_category(items: List[Dict[str, Any]], category: str) -> Dict[str, Any] | None:
    matches = [
        item
        for item in items
        if category in str(item.get("category", "")) or category in str(item.get("product_name", ""))
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda item: (
            _to_float(item.get("retrieval_score")),
            _to_float(item.get("fusion_score")),
            _to_float(item.get("bm25_score")),
        ),
    )


def build_fact_summary(candidates: List[Dict[str, Any]]) -> str:
    if not candidates:
        return "没有找到符合条件的商品。"
    lines = []
    for item in candidates:
        lines.append(
            f"{item.get('product_name')}，类别：{item.get('category')}，价格：¥{item.get('price')}，"
            f"库存：{item.get('stock')}，评分：{item.get('rating', '-')}，检索分：{item.get('retrieval_score')}"
        )
    return "\n".join(lines)


def candidate_text(candidate: Dict[str, Any]) -> str:
    return "，".join(
        str(part)
        for part in (
            candidate.get("product_name"),
            candidate.get("category"),
            candidate.get("supplier"),
            candidate.get("brand"),
            candidate.get("description"),
            candidate.get("features"),
            candidate.get("use_cases"),
            candidate.get("target_users"),
            candidate.get("tags"),
            f"价格{candidate.get('price')}",
            f"库存{candidate.get('stock')}",
        )
        if part not in ("", None)
    )


CATEGORY_ALIASES = {
    "智能门锁": "智能门锁",
    "门锁": "智能门锁",
    "猫眼": "智能门锁",
    "智能摄像头": "智能摄像头",
    "摄像头": "智能摄像头",
    "摄像机": "智能摄像头",
    "智能音箱": "智能音箱",
    "音箱": "智能音箱",
    "智能灯具": "智能灯具",
    "灯具": "智能灯具",
    "灯": "智能灯具",
    "智能插座": "智能插座",
    "插座": "智能插座",
    "智能开关": "智能开关",
    "开关": "智能开关",
    "智能传感器": "智能传感器",
    "传感器": "智能传感器",
    "扫地机器人": "智能清洁",
    "扫地机": "智能清洁",
    "智能清洁": "智能清洁",
    "空气净化器": "空气净化器",
    "净化器": "空气净化器",
    "加湿器": "智能加湿器",
    "智能加湿器": "智能加湿器",
    "智能厨房": "智能厨房",
    "电饭煲": "智能厨房",
    "破壁机": "智能厨房",
    "冰箱": "智能冰箱",
    "智能冰箱": "智能冰箱",
    "空调": "智能空调",
    "智能空调": "智能空调",
    "洗衣机": "智能洗衣机",
    "智能洗衣机": "智能洗衣机",
    "窗帘": "智能窗帘",
    "智能窗帘": "智能窗帘",
    "晾衣架": "智能晾衣架",
    "智能晾衣架": "智能晾衣架",
    "网关": "智能网关",
    "智能网关": "智能网关",
}

BRANDS = [
    "小米",
    "华为",
    "华为智选",
    "鹿客",
    "萤石",
    "美的",
    "海尔",
    "Aqara",
    "绿米",
    "公牛",
    "欧普",
    "石头",
    "科沃斯",
    "Yeelight",
    "德施曼",
    "凯迪仕",
    "360",
]


def _extract_use_case(text: str) -> Optional[str]:
    if any(word in text for word in ("安防", "安全", "看家", "门口", "入户")):
        return "家庭安防"
    if any(word in text for word in ("爸妈", "老人", "父母", "长辈")):
        return "老人看护"
    if any(word in text for word in ("新房", "装修", "全屋", "客厅", "卧室")):
        return "全屋智能"
    if any(word in text for word in ("清洁", "扫地", "拖地", "懒人")):
        return "清洁护理"
    if any(word in text for word in ("空气", "净化", "加湿", "母婴", "过敏")):
        return "空气健康"
    if any(word in text for word in ("厨房", "做饭", "烹饪")):
        return "智能厨房"
    if any(word in text for word in ("节能", "省电", "插座", "用电")):
        return "节能用电"
    return None


def _categories_for_use_case(use_case: str) -> List[str]:
    mapping = {
        "家庭安防": ["智能门锁", "智能摄像头", "智能传感器"],
        "老人看护": ["智能摄像头", "智能传感器", "智能音箱", "智能灯具"],
        "全屋智能": ["智能网关", "智能门锁", "智能灯具", "智能开关", "智能插座", "智能窗帘"],
        "清洁护理": ["智能清洁", "空气净化器", "智能加湿器"],
        "空气健康": ["空气净化器", "智能加湿器", "智能空调"],
        "智能厨房": ["智能厨房", "智能冰箱", "智能插座"],
        "节能用电": ["智能插座", "智能开关", "智能空调"],
    }
    return mapping.get(use_case, [])


def _extract_price_max(text: str) -> Optional[float]:
    patterns = [
        r"预算\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*元?\s*(?:以内|以下|之内)",
        r"不超过\s*(\d+(?:\.\d+)?)",
        r"低于\s*(\d+(?:\.\d+)?)",
    ]
    return _extract_price(text, patterns)


def _extract_price_min(text: str) -> Optional[float]:
    patterns = [r"(\d+(?:\.\d+)?)\s*元?\s*(?:以上|起)", r"高于\s*(\d+(?:\.\d+)?)"]
    return _extract_price(text, patterns)


def _extract_price(text: str, patterns: List[str]) -> Optional[float]:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None


def _normalize_score(value: float) -> float:
    if value > 1:
        return min(value / 100.0, 1.0)
    return max(value, 0.0)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_call(fn: Callable[[], List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    try:
        return fn()
    except Exception:
        return []
