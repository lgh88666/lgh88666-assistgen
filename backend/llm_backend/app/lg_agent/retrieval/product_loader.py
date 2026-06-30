"""Product data loading utilities for the Hybrid Retrieval pipeline."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import ROOT_DIR, settings


@dataclass
class ProductDocument:
    product_id: str
    product_name: str
    category: str
    price: float
    stock: int
    supplier: str
    quantity_per_unit: str
    payload: Dict[str, Any]

    @property
    def text(self) -> str:
        """Text indexed by BM25/Qdrant.

        The richer optional fields make vector retrieval behave like a real
        ecommerce catalog rather than a simple name-price table.
        """

        return " ".join(
            str(part)
            for part in (
                self.product_name,
                self.category,
                self.supplier,
                self.quantity_per_unit,
                self.payload.get("brand"),
                self.payload.get("description"),
                self.payload.get("features"),
                self.payload.get("use_cases"),
                self.payload.get("target_users"),
                self.payload.get("tags"),
                self.payload.get("compatibility"),
                f"价格{self.price}",
                f"库存{self.stock}",
            )
            if part not in ("", None)
        )


def product_data_path() -> Path:
    path = Path(settings.PRODUCT_DATA_PATH)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def product_relations_path() -> Path:
    return product_data_path().with_name("product_relations.csv")


def load_products(path: Path | None = None) -> List[ProductDocument]:
    csv_path = path or product_data_path()
    if not csv_path.exists():
        raise FileNotFoundError(f"Product CSV not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]

    products = []
    for row in rows:
        product_id = str(row.get("ProductID") or row.get("product_id") or "")
        product_name = str(row.get("ProductName") or row.get("product_name") or "")
        category = str(row.get("CategoryName") or row.get("category") or "")
        supplier = str(row.get("SupplierName") or row.get("supplier") or "")
        quantity = str(row.get("QuantityPerUnit") or row.get("quantity_per_unit") or "")
        price = _to_float(row.get("UnitPrice") or row.get("price"))
        stock = int(_to_float(row.get("UnitsInStock") or row.get("stock")))
        payload = {
            "product_id": product_id,
            "product_name": product_name,
            "category": category,
            "price": price,
            "stock": stock,
            "supplier": supplier,
            "quantity_per_unit": quantity,
            "brand": str(row.get("Brand") or row.get("brand") or supplier),
            "description": str(row.get("Description") or row.get("description") or ""),
            "features": str(row.get("Features") or row.get("features") or ""),
            "use_cases": str(row.get("UseCases") or row.get("use_cases") or ""),
            "target_users": str(row.get("TargetUsers") or row.get("target_users") or ""),
            "tags": str(row.get("Tags") or row.get("tags") or ""),
            "rating": _to_float(row.get("Rating") or row.get("rating")),
            "review_count": int(_to_float(row.get("ReviewCount") or row.get("review_count"))),
            "sales_volume": int(_to_float(row.get("SalesVolume") or row.get("sales_volume"))),
            "business_weight": _to_float(row.get("BusinessWeight") or row.get("business_weight")),
            "install_difficulty": str(row.get("InstallDifficulty") or row.get("install_difficulty") or ""),
            "after_sales_policy": str(row.get("AfterSalesPolicy") or row.get("after_sales_policy") or ""),
            "compatibility": str(row.get("Compatibility") or row.get("compatibility") or ""),
        }
        products.append(
            ProductDocument(
                product_id=product_id,
                product_name=product_name,
                category=category,
                price=price,
                stock=stock,
                supplier=supplier,
                quantity_per_unit=quantity,
                payload=payload,
            )
        )
    return products


def load_product_relations(path: Path | None = None) -> List[Dict[str, Any]]:
    csv_path = path or product_relations_path()
    if not csv_path.exists():
        return []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]

    relations = []
    for row in rows:
        reason_tags_raw = str(row.get("ReasonTags") or row.get("reason_tags") or "")
        relations.append(
            {
                "source_product_id": str(row.get("SourceProductID") or row.get("source_product_id") or ""),
                "target_product_id": str(row.get("TargetProductID") or row.get("target_product_id") or ""),
                "relation": str(row.get("Relation") or row.get("relation") or "COMPLEMENTS"),
                "weight": _to_float(row.get("Weight") or row.get("weight")),
                "reason": str(row.get("Reason") or row.get("reason") or ""),
                "scenario": str(row.get("Scenario") or row.get("scenario") or ""),
                "reason_tags": [t.strip() for t in reason_tags_raw.split(",") if t.strip()],
                "business_weight": _to_float(row.get("BusinessWeight") or row.get("business_weight")),
            }
        )
    return relations


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
