"""GraphRAG-backed explanation tool.

GraphRAG is attempted for every answer, but the tool is safe-by-default: if
GraphRAG data or dependencies are unavailable, it returns a deterministic
explanation over the already selected candidates.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.core.config import settings
from app.core.logger import get_logger
from app.lg_agent.llm_client import generate_text, llm_config_label
from app.lg_agent.memory.manager import memory_manager

logger = get_logger(service="graphrag_explanation_tool")


class GraphRAGExplanationTool:
    async def explain(
        self,
        query: str,
        retrieval_candidates: List[Dict[str, Any]],
        recommendations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        cache_payload = {
            "query": query,
            "retrieval_ids": [item.get("product_id") for item in retrieval_candidates[:8]],
            "recommendation_ids": [item.get("product_id") for item in recommendations[:8]],
        }
        cache_key = memory_manager.cache_key("graphrag_explanation", cache_payload)
        cached = await memory_manager.get_json(cache_key)
        if cached:
            return cached

        prompt = _build_graphrag_prompt(query, retrieval_candidates, recommendations)
        graphrag_text = await self._query_graphrag(prompt)
        if graphrag_text:
            result = {"source": "graphrag", "text": graphrag_text}
        else:
            # Try lightweight Qdrant evidence retrieval.
            evidence_text = await self._query_qdrant_evidence(query, retrieval_candidates, recommendations)
            if evidence_text:
                llm_text = await self._query_llm_with_evidence(query, retrieval_candidates, recommendations, evidence_text)
                if llm_text:
                    result = {"source": "lightweight_graphrag_qdrant", "text": llm_text, "model": llm_config_label()}
                else:
                    result = {
                        "source": "structured_relation_evidence",
                        "text": evidence_text,
                    }
            else:
                llm_text = await self._query_llm_explanation(query, retrieval_candidates, recommendations)
                if llm_text:
                    result = {"source": "llm", "text": llm_text, "model": llm_config_label()}
                else:
                    result = {
                        "source": "fallback",
                        "text": _deterministic_explanation(query, retrieval_candidates, recommendations),
                    }

        await memory_manager.set_json(cache_key, result, ttl=6 * 60 * 60)
        return result

    async def _query_graphrag(self, prompt: str) -> str:
        try:
            from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.customer_tools.node import GraphRAGAPI

            api = GraphRAGAPI(
                project_dir=settings.GRAPHRAG_PROJECT_DIR,
                data_dir_name=settings.GRAPHRAG_DATA_DIR,
                query_type=settings.GRAPHRAG_QUERY_TYPE,
                response_type=settings.GRAPHRAG_RESPONSE_TYPE,
                community_level=settings.GRAPHRAG_COMMUNITY_LEVEL,
                dynamic_community_selection=settings.GRAPHRAG_DYNAMIC_COMMUNITY,
            )
            result = await api.query_graphrag(prompt)
            return str(result.get("response") or "").strip()
        except Exception as exc:
            logger.info(f"GraphRAG explanation unavailable, fallback to deterministic explanation: {exc}")
            return ""

    async def _query_qdrant_evidence(
        self,
        query: str,
        retrieval_candidates: List[Dict[str, Any]],
        recommendations: List[Dict[str, Any]],
    ) -> str:
        """Retrieve relevant relation evidence from Qdrant.

        Returns a short evidence summary string, or empty string on failure.
        """
        try:
            from qdrant_client import QdrantClient

            client = QdrantClient(url=settings.QDRANT_URL)
            collection = "assistgen_explanation_evidence"
            collections = [c.name for c in client.get_collections().collections]
            if collection not in collections:
                return ""

            # Build search text from query + product context.
            product_names = " ".join(
                item.get("product_name", "")
                for item in (retrieval_candidates[:2] + recommendations[:2])
            )
            search_text = f"{query} {product_names}"

            # Embed search text.
            try:
                from fastembed import TextEmbedding
                embedder = TextEmbedding(model_name=settings.QDRANT_EMBEDDING_MODEL)
                vectors = list(embedder.embed([search_text]))
                query_vector = vectors[0] if vectors else None
            except Exception:
                query_vector = None

            if query_vector is None:
                return ""

            results = client.search(
                collection_name=collection,
                query_vector=query_vector.tolist(),
                limit=5,
            )

            # Build evidence summary from top results.
            lines: list[str] = []
            for hit in results:
                p = hit.payload or {}
                lines.append(
                    f"- {p.get('source_product_name','?')} + {p.get('target_product_name','?')}"
                    f"  relation={p.get('relation','?')}  scenario={p.get('scenario','')}"
                    f"  tags={','.join(p.get('reason_tags',[]))}"
                )

            return "\n".join(lines) if lines else ""

        except Exception:
            return ""

    async def _query_llm_with_evidence(
        self,
        query: str,
        retrieval_candidates: List[Dict[str, Any]],
        recommendations: List[Dict[str, Any]],
        evidence_text: str,
    ) -> str:
        """Generate natural Chinese explanation from Qdrant evidence."""
        try:
            text = await generate_text(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are the Explanation Agent in a Chinese ecommerce system.\n"
                            "You are given structured relation evidence from the product graph.\n"
                            "Use the evidence to explain why the recommended pairings make sense.\n"
                            "Do not invent new products, prices, or stock.\n"
                            "Do not say 'I queried the database', 'knowledge graph', 'relation chain',\n"
                            "or any backend system language.\n"
                            "Use buyer-facing language: what problem the pair solves,\n"
                            "why it fits the user's constraints, and what to confirm next.\n"
                            "Output 2-3 sentences in Chinese. Do not expose internal scores."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"User query: {query}\n"
                            f"Product evidence:\n{evidence_text}\n"
                            f"Main candidates: {', '.join(item.get('product_name','') for item in retrieval_candidates[:3])}\n"
                            f"Recommendations: {', '.join(item.get('product_name','') for item in recommendations[:3])}\n"
                            f"Please explain in natural Chinese why these products work together."
                        ),
                    },
                ],
                temperature=0.35,
                max_tokens=400,
                tags=["commerce_explanation_evidence"],
            )
            return text.strip()
        except Exception:
            return ""

    async def _query_llm_explanation(
        self,
        query: str,
        retrieval_candidates: List[Dict[str, Any]],
        recommendations: List[Dict[str, Any]],
    ) -> str:
        try:
            text = await generate_text(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are the Explanation Agent in a Chinese ecommerce customer service system.\n"
                            "Only explain using the given product facts and recommendation relations; "
                            "do not invent new products, prices, or stock.\n"
                            "Do not rewrite the recommendation list or recommend products not given.\n"
                            "Each recommended product carries relation (type), scenario, and tags (evidence). "
                            "Use these evidence tags to explain why the pairing makes sense, "
                            "rather than generic phrases like 'they complement each other'.\n"
                            "If the user asks for low price / cheapest / affordable, "
                            "prioritise explaining low-price candidates, not add-on recommendations.\n"
                            "Output 2-3 sentences in Chinese: why the main pick and pairings are reasonable, "
                            "and what additional info the user can provide next."
                        ),
                    },
                    {
                        "role": "user",
                        "content": _build_graphrag_prompt(query, retrieval_candidates, recommendations),
                    },
                ],
                temperature=0.35,
                max_tokens=500,
                tags=["commerce_explanation_agent"],
            )
            return text.strip()
        except Exception as exc:
            logger.info(f"LLM explanation unavailable, fallback to deterministic explanation: {exc}")
            return ""


def _build_graphrag_prompt(
    query: str,
    retrieval_candidates: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
) -> str:
    candidate_lines = [
        f"- {item.get('product_name')} / {item.get('category')} / price={item.get('price')} / stock={item.get('stock')}"
        for item in retrieval_candidates[:6]
    ]
    recommendation_lines = []
    for item in recommendations[:6]:
        tags = item.get("reason_tags") or []
        scenario = item.get("scenario") or ""
        evidence = f"relation={item.get('relation')}"
        if scenario:
            evidence += f", scenario={scenario}"
        if tags:
            evidence += f", tags={','.join(tags)}"
        recommendation_lines.append(
            f"- {item.get('product_name')} / {evidence} / reason={item.get('reason')}"
        )
    return (
        "You are the ecommerce Explanation module. Only explain the given candidates. Do not add new products.\n"
        f"User query: {query}\n"
        "Fact candidates:\n"
        + "\n".join(candidate_lines)
        + "\nRecommendation candidates:\n"
        + "\n".join(recommendation_lines)
        + "\nUse the relation, scenario, and tags evidence to explain why these pairings make sense. "
        + "Do not recommend other products. Do not output scores. Reply in Chinese."
    )


def _deterministic_explanation(
    query: str,
    retrieval_candidates: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
) -> str:
    if _is_support_or_angry(query) and not recommendations:
        lines = ["我先按你的问题定位到相关商品信息；这个场景不主动追加销售推荐。"]
        if retrieval_candidates:
            top = retrieval_candidates[0]
            lines.append(
                f"当前最相关的是 {top.get('product_name')}。如果这是已购商品，建议优先核对订单、保修期和故障现象。"
            )
        lines.append("你可以继续告诉我购买时间、故障表现或订单信息，我再帮你整理处理路径。")
        return "\n".join(lines)

    lines = ["我先按你的需求查了商品事实，再基于搭配关系补充推荐。"]
    if retrieval_candidates:
        top = retrieval_candidates[0]
        lines.append(
            f"优先匹配到的是 {top.get('product_name')}，价格 {top.get('price')}，库存 {top.get('stock')}。"
        )
    if recommendations:
        parts: list[str] = []
        for item in recommendations[:3]:
            name = item.get("product_name", "")
            relation_cn = RELATION_LABELS.get(item.get("relation", ""), "搭配")
            tags = item.get("reason_tags") or []
            tag_str = f"({'，'.join(tags[:2])})" if tags else ""
            parts.append(f"{name}（{relation_cn}{tag_str}）")
        names = "、".join(parts)
        lines.append(f"搭配推荐优先考虑 {names}，原因是它们和当前需求在使用场景或图关系上互补。")
        lines.append("如果你想要一套完整方案，我可以继续按预算、房型和安装复杂度帮你组合。")
    return "\n".join(lines)


def _is_support_or_angry(query: str) -> bool:
    return any(word in query for word in ("坏了", "故障", "投诉", "生气", "退货", "差评"))


# Human-readable relation labels for explanation.
RELATION_LABELS: Dict[str, str] = {
    "COMPLEMENTS": "功能互补",
    "BOUGHT_WITH": "常一起购买",
    "CONSUMABLE": "后续耗材/配件",
    "UPGRADE": "升级选择",
    "SAME_SCENE": "同场景搭配",
    "BUNDLE": "套装组合",
    "SUBSTITUTE": "替代选择",
}
