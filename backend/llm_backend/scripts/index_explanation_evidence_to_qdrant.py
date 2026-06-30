"""Index lightweight explanation evidence from product_relations.csv into Qdrant.

Creates (or re-creates) the ``assistgen_explanation_evidence`` collection
with short evidence documents that the Explanation layer can retrieve.

Each evidence document describes one product relation edge and carries
metadata needed for filtered retrieval: source/target product ids, relation
type, scenario, reason_tags, and category pair.

Usage::

    python scripts/index_explanation_evidence_to_qdrant.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# Allow running from scripts/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.lg_agent.retrieval.product_loader import load_product_relations, load_products


COLLECTION_NAME = "assistgen_explanation_evidence"
VECTOR_SIZE = settings.QDRANT_VECTOR_SIZE


def main() -> None:
    products = load_products()
    products_by_id: Dict[str, Any] = {p.product_id: p for p in products}

    relations = load_product_relations()
    if not relations:
        print("No product relations found. Run generate_demo_ecommerce_data.py first.")
        return

    print(f"Building evidence documents from {len(relations)} relations...")

    documents: List[str] = []
    payloads: List[Dict[str, Any]] = []
    ids: List[str] = []

    for i, rel in enumerate(relations):
        source_id = rel.get("source_product_id", "")
        target_id = rel.get("target_product_id", "")
        source = products_by_id.get(source_id)
        target = products_by_id.get(target_id)
        if not source or not target:
            continue

        relation_type = rel.get("relation", "COMPLEMENTS")
        scenario = rel.get("scenario", "")
        reason_tags = rel.get("reason_tags") or []
        reason_text = rel.get("reason", "")
        weight = rel.get("weight", 0.0)

        # Build a short natural-language evidence document for embedding.
        evidence_text = (
            f"关系类型：{relation_type}。"
            f"商品：{source.product_name}（{source.category}）→ {target.product_name}（{target.category}）。"
        )
        if scenario:
            evidence_text += f"使用场景：{scenario}。"
        if reason_tags:
            evidence_text += f"证据标签：{'，'.join(reason_tags)}。"
        if reason_text:
            evidence_text += f"推荐理由：{reason_text}。"

        documents.append(evidence_text)
        payloads.append({
            "evidence_id": f"evidence_{i}",
            "source_product_id": source_id,
            "target_product_id": target_id,
            "source_product_name": source.product_name,
            "target_product_name": target.product_name,
            "source_category": source.category,
            "target_category": target.category,
            "relation": relation_type,
            "scenario": scenario,
            "reason_tags": reason_tags,
            "weight": weight,
            "category_pair": f"{source.category} / {target.category}",
        })
        # Qdrant 1.18 requires unsigned integers or UUIDs for point ids.
        ids.append(i)

    if not documents:
        print("No valid evidence documents to index.")
        return

    # Try Qdrant.
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams
    except ImportError:
        print("qdrant-client not installed. Evidence not indexed.")
        return

    try:
        client = QdrantClient(url=settings.QDRANT_URL)
    except Exception:
        print(f"Qdrant unavailable at {settings.QDRANT_URL}. Evidence not indexed.")
        return

    # Re-create collection.
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in collections:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing collection: {COLLECTION_NAME}")

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    print(f"Created collection: {COLLECTION_NAME} (dim={VECTOR_SIZE})")

    # Embed documents using the configured provider (local or dashscope).
    try:
        from app.lg_agent.retrieval.embedding import embed_texts
        vectors = embed_texts(documents)
        label = f"{settings.EMBEDDING_PROVIDER}/{settings.EMBEDDING_MODEL}@{settings.EMBEDDING_DIMENSION}"
        print(f"Embedded {len(vectors)} documents with {label}")
    except Exception as exc:
        print(f"[WARN] embedding unavailable ({exc}), indexed zero vectors for structural verification")
        vectors = [[0.0] * VECTOR_SIZE for _ in documents]

    # Batch insert.
    batch_size = 100
    for start in range(0, len(documents), batch_size):
        batch_docs = documents[start:start + batch_size]
        batch_payloads = payloads[start:start + batch_size]
        batch_ids = ids[start:start + batch_size]
        batch_vectors = vectors[start:start + batch_size]

        points = [
            PointStruct(id=pid, vector=vec, payload=payload)
            for pid, vec, payload in zip(batch_ids, batch_vectors, batch_payloads)
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"  Indexed {start + len(batch_docs)}/{len(documents)}")

    print(f"Done. {len(documents)} evidence documents indexed to {COLLECTION_NAME}.")


if __name__ == "__main__":
    main()
