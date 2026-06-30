"""Retrieval Agent powered by Hybrid Product RAG."""

from __future__ import annotations

from typing import Any, Dict

from app.core.logger import get_logger
from app.lg_agent.observability.trace import trace_event
from app.lg_agent.retrieval.hybrid_pipeline import HybridProductRetriever

logger = get_logger(service="retrieval_agent")


def create_retrieval_node(retriever: HybridProductRetriever | None = None):
    """Create Retrieval Agent node.

    Retrieval Agent owns the full product RAG pipeline:
    Query parsing -> Qdrant dense retrieval -> BM25 sparse retrieval ->
    metadata filtering -> score fusion -> reranker API -> context summary.
    """

    hybrid_retriever = retriever or HybridProductRetriever()

    async def retrieval(state: Dict[str, Any]) -> Dict[str, Any]:
        task = state.get("retriever_task") or state.get("task") or _last_user_message(state)
        shopping_state = state.get("shopping_state") or {}
        query_features = state.get("query_features") or {}
        ranking_objective = (
            shopping_state.get("ranking_objective")
            or query_features.get("ranking_objective")
        )
        logger.info(f"Retrieval Agent: hybrid retrieval for {task[:80]}")

        result = await hybrid_retriever.retrieve(
            task, ranking_objective=ranking_objective,
        )
        candidates = result["candidates"]
        records = [_to_record(candidate) for candidate in candidates]

        trace_event("Retrieval", {
            "query": result.get("rewritten_query", task),
            "method": _retrieval_method(result),
            "candidate_count": len(candidates),
            "top_products": candidates[:3],
        })

        return {
            "retriever_task": task,
            "retriever_results": [
                {
                    "task": task,
                    "statement": "HYBRID_PRODUCT_RAG",
                    "errors": [],
                    "records": records,
                }
            ],
            "retriever_answer": result["fact_summary"],
            "retrieval_context": result,
            "steps": ["retrieval"],
        }

    return retrieval


def _last_user_message(state: Dict[str, Any]) -> str:
    messages = state.get("messages", [])
    if not messages:
        return ""
    last = messages[-1]
    return getattr(last, "content", str(last))


def _retrieval_method(result: Dict[str, Any]) -> str:
    cands = result.get("candidates") or []
    if not cands:
        return "none"
    sources = {str(c.get("source", "")) for c in cands if c.get("source")}
    return "+".join(sorted(sources)) if sources else "unknown"


def _to_record(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ProductID": candidate.get("product_id"),
        "ProductName": candidate.get("product_name"),
        "CategoryName": candidate.get("category"),
        "UnitPrice": candidate.get("price"),
        "UnitsInStock": candidate.get("stock"),
        "SupplierName": candidate.get("supplier"),
        "DenseScore": candidate.get("dense_score", 0),
        "BM25Score": candidate.get("bm25_score", 0),
        "MetadataScore": candidate.get("metadata_score", 0),
        "FusionScore": candidate.get("fusion_score", 0),
        "RerankScore": candidate.get("rerank_score", 0),
        "RetrievalScore": candidate.get("retrieval_score", 0),
        "Strategy": "HYBRID_RAG",
    }

