"""KG-style recommendation tool with deterministic fallbacks.

Neo4j is the preferred online source for relation evidence. When Neo4j is not
available, the tool uses the generated product_relations.csv as a local graph,
then falls back to category complement rules. This keeps the recommendation
agent visible and testable without Docker or database services.
"""

from __future__ import annotations

import socket
from typing import Any, Dict, List
from urllib.parse import urlparse

from app.core.config import settings
from app.core.logger import get_logger
from app.lg_agent.retrieval.product_loader import ProductDocument, load_product_relations, load_products

logger = get_logger(service="recommendation_tool")


class KGRecommendationTool:
    def __init__(self):
        self.products = load_products()
        self.products_by_id = {p.product_id: p for p in self.products}
        self.relations = load_product_relations()

    def recommend(
        self,
        query: str,
        retrieval_candidates: List[Dict[str, Any]],
        top_k: int | None = None,
        shopping_state: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        limit = top_k or settings.RECOMMENDATION_TOP_K
        budget = _extract_budget(query)
        # Prefer shopping_state budget over regex extraction.
        if shopping_state:
            if shopping_state.get("budget_max") is not None:
                budget = float(shopping_state["budget_max"])
            elif shopping_state.get("budget_min") is not None:
                budget = float(shopping_state["budget_min"])
        anchors = _select_anchors(retrieval_candidates)

        graph_items = self._recommend_from_neo4j(anchors)
        source = "neo4j"

        if not graph_items:
            graph_items = self._recommend_from_local_relations(anchors, query)
            source = "local_relation_graph"

        if not graph_items:
            graph_items = self._recommend_by_rules(anchors, query)
            source = "category_rules_fallback"

        ranked = self._score(graph_items, retrieval_candidates, budget=budget, shopping_state=shopping_state)
        ranked = _prioritize_requested_categories(ranked, query, anchors)

        # Apply ranking_objective from shopping_state (takes priority over
        # keyword-based low-price sorting in hybrid_pipeline).
        if shopping_state:
            objective = shopping_state.get("ranking_objective", "balanced")
            if objective == "lowest_price":
                ranked.sort(key=lambda x: _to_float(x.get("price")) or float("inf"))
            elif objective == "highest_rating":
                ranked.sort(key=lambda x: _to_float(x.get("final_score")) or 0, reverse=True)
            # "best_value" and "highest_sales" use the default weighted scoring.

        return {
            "source": source,
            "anchors": anchors,
            "items": ranked[:limit],
            "budget": budget,
            "estimated_bundle_total": estimate_bundle_total(anchors, ranked[:limit], budget),
            "summary": build_recommendation_summary(ranked[:limit]),
        }

    def _recommend_from_neo4j(self, anchors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not anchors or not _is_neo4j_port_open(settings.NEO4J_URL):
            return []

        try:
            from app.lg_agent.kg_sub_graph.kg_neo4j_conn import get_neo4j_graph

            graph = get_neo4j_graph()
            anchor_names = [item.get("product_name") for item in anchors if item.get("product_name")]
            if not anchor_names:
                return []

            query = """
            MATCH (anchor:Product)-[r:BOUGHT_WITH|COMPLEMENTS|UPGRADE|SCENE_MATCH]-(p:Product)
            WHERE anchor.ProductName IN $anchor_names
            RETURN
              p.ProductID AS product_id,
              p.ProductName AS product_name,
              p.CategoryName AS category,
              p.UnitPrice AS price,
              p.UnitsInStock AS stock,
              type(r) AS relation,
              coalesce(r.Weight, r.weight, r.score, r.confidence, 1.0) AS graph_score,
              anchor.ProductName AS anchor_product,
              coalesce(r.Reason, r.reason, '') AS reason,
              coalesce(r.Scenario, r.scenario, '') AS scenario
            ORDER BY graph_score DESC
            LIMIT 30
            """
            return [dict(row) for row in graph.query(query, params={"anchor_names": anchor_names})]
        except Exception as exc:
            logger.info(f"Neo4j recommendation unavailable, fallback to local graph: {exc}")
            return []

    def _recommend_from_local_relations(self, anchors: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        if not self.relations:
            return []

        anchor_ids = {str(item.get("product_id")) for item in anchors if item.get("product_id")}
        query_scenarios = _scenarios_from_query(query)
        results: List[Dict[str, Any]] = []

        for relation in self.relations:
            source_id = str(relation.get("source_product_id") or "")
            if anchor_ids and source_id not in anchor_ids:
                continue
            if query_scenarios and relation.get("scenario") not in query_scenarios and not anchor_ids:
                continue
            item = self._relation_to_item(relation, scenario_boost=query_scenarios)
            if item:
                results.append(item)

        if results:
            return results

        if not query_scenarios:
            return []

        for relation in self.relations:
            if relation.get("scenario") not in query_scenarios:
                continue
            item = self._relation_to_item(relation, scenario_boost=query_scenarios)
            if item:
                results.append(item)
        return results

    def _relation_to_item(self, relation: Dict[str, Any], scenario_boost: List[str]) -> Dict[str, Any] | None:
        target = self.products_by_id.get(str(relation.get("target_product_id")))
        source = self.products_by_id.get(str(relation.get("source_product_id")))
        if not target:
            return None
        boost = 0.08 if scenario_boost and relation.get("scenario") in scenario_boost else 0.0
        relation_type = relation.get("relation") or "COMPLEMENTS"
        return {
            **target.payload,
            "relation": relation_type,
            "graph_score": min(_to_float(relation.get("weight")) + boost, 1.0),
            "anchor_product": source.product_name if source else "",
            "reason": relation.get("reason") or _reason_for_relation(str(relation_type), target),
            "scenario": relation.get("scenario", ""),
        }

    def _recommend_by_rules(self, anchors: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        anchor_categories = {str(item.get("category", "")) for item in anchors if item.get("category")}
        target_categories = set()
        for category in anchor_categories:
            target_categories.update(COMPLEMENT_RULES.get(category, []))

        if not target_categories:
            target_categories.update(_categories_from_query(query))

        anchor_ids = {str(item.get("product_id")) for item in anchors if item.get("product_id")}
        results = []
        for product in self.products:
            if product.product_id in anchor_ids:
                continue
            if target_categories and product.category not in target_categories:
                continue
            relation = _rule_relation(anchor_categories, product.category)
            results.append(
                {
                    **product.payload,
                    "relation": relation,
                    "graph_score": DEFAULT_RELATION_SCORES.get(relation, 0.55),
                    "anchor_product": _anchor_name_for(product.category, anchors),
                    "reason": _reason_for_relation(relation, product),
                }
            )
        return results

    def _score(
        self,
        graph_items: List[Dict[str, Any]],
        retrieval_candidates: List[Dict[str, Any]],
        *,
        budget: float | None,
        shopping_state: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        retrieval_by_id = {str(item.get("product_id")): item for item in retrieval_candidates}
        grouped: Dict[str, Dict[str, Any]] = {}

        for item in graph_items:
            pid = str(item.get("product_id") or "")
            if not pid:
                continue
            current = grouped.setdefault(pid, dict(item))
            current["graph_score"] = max(_to_float(current.get("graph_score")), _to_float(item.get("graph_score")))
            if not current.get("reason") and item.get("reason"):
                current["reason"] = item["reason"]

        # Determine which relation type boost map to use.
        intent = (shopping_state or {}).get("ranking_objective", "balanced")
        is_solution = intent == "solution_plan" or (shopping_state or {}).get("scenario") == "新房装修"
        is_low_price = intent == "lowest_price"

        for pid, item in grouped.items():
            retrieval_score = _to_float(retrieval_by_id.get(pid, {}).get("retrieval_score"))
            graph_score = _normalize_score(_to_float(item.get("graph_score")))
            business_score = _business_score(item)
            budget_score = _budget_score(_to_float(item.get("price")), budget)
            relation_boost = _relation_boost(
                str(item.get("relation", "COMPLEMENTS")),
                budget=budget,
                is_solution=is_solution,
                is_low_price=is_low_price,
            )
            item["retrieval_score"] = retrieval_score
            item["graph_score"] = graph_score
            item["business_score"] = business_score
            item["budget_score"] = budget_score
            item["final_score"] = round(
                settings.RECOMMENDATION_RETRIEVAL_WEIGHT * retrieval_score
                + settings.RECOMMENDATION_GRAPH_WEIGHT * graph_score
                + settings.RECOMMENDATION_BUSINESS_WEIGHT * business_score
                + 0.08 * budget_score
                + 0.10 * relation_boost,
                4,
            )
            item.setdefault("reason", _reason_for_relation(str(item.get("relation", "COMPLEMENTS")), item))

        ranked = list(grouped.values())
        ranked.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        return ranked


COMPLEMENT_RULES = {
    "智能门锁": ["智能摄像头", "智能传感器"],
    "智能摄像头": ["智能门锁", "智能传感器"],
    "智能传感器": ["智能门锁", "智能摄像头", "智能插座"],
    "智能音箱": ["智能灯具", "智能插座", "智能窗帘"],
    "智能灯具": ["智能音箱", "智能开关", "智能插座"],
    "智能开关": ["智能灯具", "智能插座"],
    "智能插座": ["智能音箱", "智能灯具", "智能开关"],
    "智能清洁": ["空气净化器", "智能加湿器"],
    "智能空调": ["智能加湿器", "空气净化器"],
    "智能网关": ["智能门锁", "智能灯具", "智能开关", "智能窗帘"],
}

DEFAULT_RELATION_SCORES = {
    "BOUGHT_WITH": 0.85,
    "COMPLEMENTS": 0.75,
    "UPGRADE": 0.65,
    "SCENE_MATCH": 0.60,
}


def build_recommendation_summary(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "暂无可推荐的搭配商品。"
    return "\n".join(
        f"{item.get('product_name')}，关系：{item.get('relation')}，推荐分：{item.get('final_score')}，理由：{item.get('reason')}"
        for item in items
    )


def estimate_bundle_total(
    anchors: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
    budget: float | None,
) -> Dict[str, Any]:
    """Estimate a simple bundle using top anchor + affordable relation items."""

    selected: List[Dict[str, Any]] = []
    if anchors:
        selected.append(anchors[0])

    total = sum(_to_float(item.get("price")) for item in selected)
    for item in recommendations:
        price = _to_float(item.get("price"))
        if budget is not None and total + price > budget and selected:
            continue
        selected.append(item)
        total += price
        if len(selected) >= 3:
            break

    return {
        "total": round(total, 2),
        "within_budget": budget is None or total <= budget,
        "items": [
            {
                "product_id": item.get("product_id"),
                "product_name": item.get("product_name"),
                "price": item.get("price"),
            }
            for item in selected
        ],
    }


def _select_anchors(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = sorted(candidates, key=lambda x: x.get("retrieval_score", 0), reverse=True)
    anchors: List[Dict[str, Any]] = []
    seen_categories: set[str] = set()
    seen_ids: set[str] = set()

    for item in ranked:
        category = str(item.get("category") or "")
        pid = str(item.get("product_id") or "")
        if not category or category in seen_categories:
            continue
        anchors.append(item)
        seen_categories.add(category)
        if pid:
            seen_ids.add(pid)
        if len(anchors) >= 3:
            return anchors

    for item in ranked:
        pid = str(item.get("product_id") or "")
        if pid and pid in seen_ids:
            continue
        anchors.append(item)
        if pid:
            seen_ids.add(pid)
        if len(anchors) >= 3:
            break
    return anchors


def _categories_from_query(query: str) -> List[str]:
    explicit = []
    if "门锁" in query:
        explicit.append("智能门锁")
    if "摄像头" in query or "摄像机" in query:
        explicit.append("智能摄像头")
    if "传感器" in query:
        explicit.append("智能传感器")
    if "灯" in query:
        explicit.append("智能灯具")
    if "插座" in query:
        explicit.append("智能插座")
    if explicit:
        return list(dict.fromkeys(explicit))
    if any(word in query for word in ("安防", "安全", "看家", "门口")):
        return ["智能门锁", "智能摄像头", "智能传感器"]
    if any(word in query for word in ("新房", "装修", "全屋")):
        return ["智能网关", "智能门锁", "智能灯具", "智能开关", "智能插座", "智能窗帘"]
    if any(word in query for word in ("老人", "爸妈", "父母", "长辈")):
        return ["智能摄像头", "智能传感器", "智能音箱", "智能灯具"]
    return []


def _prioritize_requested_categories(
    ranked: List[Dict[str, Any]],
    query: str,
    anchors: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    requested = set(_categories_from_query(query))
    if not requested:
        return ranked

    anchor_ids = {str(item.get("product_id") or "") for item in anchors}
    direct = []
    indirect = []
    for item in ranked:
        category = str(item.get("category") or "")
        pid = str(item.get("product_id") or "")
        if pid in anchor_ids:
            continue
        if category in requested:
            boosted = dict(item)
            boosted["final_score"] = round(_to_float(boosted.get("final_score")) + 0.12, 4)
            direct.append(boosted)
        else:
            indirect.append(item)
    direct.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    indirect.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    return direct + indirect


def _rule_relation(anchor_categories: set[str], product_category: str) -> str:
    for category in anchor_categories:
        if product_category in COMPLEMENT_RULES.get(category, []):
            return "COMPLEMENTS"
    return "SCENE_MATCH"


def _anchor_name_for(product_category: str, anchors: List[Dict[str, Any]]) -> str:
    for anchor in anchors:
        category = str(anchor.get("category", ""))
        if product_category in COMPLEMENT_RULES.get(category, []):
            return str(anchor.get("product_name", ""))
    return str(anchors[0].get("product_name", "")) if anchors else ""


def _reason_for_relation(relation: str, product: ProductDocument | Dict[str, Any]) -> str:
    name = product.product_name if isinstance(product, ProductDocument) else product.get("product_name")
    if relation == "BOUGHT_WITH":
        return f"{name} 与用户关注商品存在共购关系，适合作为搭配推荐。"
    if relation == "UPGRADE":
        return f"{name} 是同类升级选择，适合预算更高或追求体验的用户。"
    if relation == "SCENE_MATCH":
        return f"{name} 符合同一使用场景，可补齐方案。"
    return f"{name} 与用户关注商品功能互补，适合组成套装。"


def _business_score(item: Dict[str, Any]) -> float:
    stock = _to_float(item.get("stock"))
    price = _to_float(item.get("price"))
    configured = _to_float(item.get("business_weight"))
    if configured > 0:
        return min(configured, 1.0)
    stock_score = min(stock / 100.0, 1.0)
    price_score = 1.0 if price <= 1000 else 0.8 if price <= 2500 else 0.6
    return round(0.7 * stock_score + 0.3 * price_score, 4)


def _budget_score(price: float, budget: float | None) -> float:
    if budget is None or budget <= 0:
        return 0.5
    if price <= budget * 0.35:
        return 1.0
    if price <= budget * 0.6:
        return 0.8
    if price <= budget:
        return 0.55
    return 0.05


def _normalize_score(value: float) -> float:
    if value > 1:
        return min(value / 100.0, 1.0)
    return max(value, 0.0)


# ── relation type boost ─────────────────────────────────────────────────

# Base boost for each relation type in "normal" (single-product add-on) mode.
RELATION_BOOST_DEFAULT: Dict[str, float] = {
    "COMPLEMENTS": 0.95,
    "BOUGHT_WITH": 0.90,
    "CONSUMABLE": 0.80,
    "SAME_SCENE": 0.60,
    "BUNDLE": 0.55,
    "UPGRADE": 0.45,
    "SUBSTITUTE": 0.40,
}

# Boost overrides for solution-plan intent (bundle > same-scene > complements).
RELATION_BOOST_SOLUTION: Dict[str, float] = {
    "BUNDLE": 0.95,
    "SAME_SCENE": 0.90,
    "COMPLEMENTS": 0.75,
    "BOUGHT_WITH": 0.65,
    "CONSUMABLE": 0.50,
    "UPGRADE": 0.35,
    "SUBSTITUTE": 0.30,
}

# Boost overrides for low-price intent (substitute > complements, down-rank upgrade).
RELATION_BOOST_LOW_PRICE: Dict[str, float] = {
    "SUBSTITUTE": 0.90,
    "COMPLEMENTS": 0.70,
    "BOUGHT_WITH": 0.65,
    "CONSUMABLE": 0.60,
    "SAME_SCENE": 0.50,
    "BUNDLE": 0.40,
    "UPGRADE": 0.20,
}


def _relation_boost(
    relation: str,
    *,
    budget: float | None,
    is_solution: bool,
    is_low_price: bool,
) -> float:
    """Return a 0-1 boost factor for the given relation type and intent."""
    if is_low_price:
        table = RELATION_BOOST_LOW_PRICE
    elif is_solution:
        table = RELATION_BOOST_SOLUTION
    else:
        table = RELATION_BOOST_DEFAULT

    boost = table.get(relation, 0.50)

    # Further penalise UPGRADE when budget is tight.
    if relation == "UPGRADE" and budget is not None and budget < 1500:
        boost -= 0.25

    return max(boost, 0.0)


def _extract_budget(query: str) -> float | None:
    patterns = [
        r"预算\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*元?\s*(?:以内|以下|之内)",
        r"不超过\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = __import__("re").search(pattern, query)
        if match:
            return float(match.group(1))
    return None


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_neo4j_port_open(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 7687
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def _scenarios_from_query(query: str) -> List[str]:
    scenarios = []
    if any(word in query for word in ("安防", "安全", "看家", "门口", "入户")):
        scenarios.append("家庭安防")
    if any(word in query for word in ("爸妈", "老人", "父母", "长辈")):
        scenarios.append("老人看护")
    if any(word in query for word in ("新房", "装修", "全屋", "客厅", "卧室")):
        scenarios.append("全屋智能")
    if any(word in query for word in ("清洁", "扫地", "拖地", "懒人")):
        scenarios.append("清洁护理")
    if any(word in query for word in ("空气", "净化", "加湿", "母婴", "过敏")):
        scenarios.append("空气健康")
    if any(word in query for word in ("厨房", "做饭", "烹饪")):
        scenarios.append("智能厨房")
    if any(word in query for word in ("节能", "省电", "插座", "用电")):
        scenarios.append("节能用电")
    return scenarios
