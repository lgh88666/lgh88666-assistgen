"""Index product CSV into Qdrant.

Run from backend/llm_backend:
    python scripts/index_products_to_qdrant.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import settings
from app.lg_agent.retrieval.embedding import embed_texts
from app.lg_agent.retrieval.product_loader import load_products, product_data_path


def main() -> None:
    csv_path = product_data_path()
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Product CSV not found: {csv_path}\n"
            "Please generate or place products.csv before indexing."
        )

    products = load_products(csv_path)
    if not products:
        raise RuntimeError(f"No products loaded from: {csv_path}")

    client = QdrantClient(url=settings.QDRANT_URL)
    client.recreate_collection(
        collection_name=settings.QDRANT_COLLECTION_PRODUCTS,
        vectors_config=VectorParams(size=settings.QDRANT_VECTOR_SIZE, distance=Distance.COSINE),
    )

    texts = [product.text for product in products]
    try:
        vectors = embed_texts(texts)
        label = f"{settings.EMBEDDING_PROVIDER}/{settings.EMBEDDING_MODEL}@{settings.EMBEDDING_DIMENSION}"
        print(f"Embedded {len(vectors)} product documents with {label}")
    except Exception as exc:
        print(f"[ERROR] Product embedding failed: {exc}")
        raise

    points = []
    for idx, (product, vector) in enumerate(zip(products, vectors), start=1):
        point_id = int(product.product_id) if str(product.product_id).isdigit() else idx
        payload = dict(product.payload)
        payload["document_text"] = product.text
        points.append(PointStruct(id=point_id, vector=vector, payload=payload))

    client.upsert(collection_name=settings.QDRANT_COLLECTION_PRODUCTS, points=points)
    print(f"Indexed {len(points)} products into Qdrant collection '{settings.QDRANT_COLLECTION_PRODUCTS}'.")


if __name__ == "__main__":
    main()

