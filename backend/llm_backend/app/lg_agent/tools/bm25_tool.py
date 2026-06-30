"""BM25 sparse retrieval for product facts."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from app.core.config import settings
from app.lg_agent.retrieval.product_loader import ProductDocument, load_products


class BM25ProductRetriever:
    """Sparse retriever backed by an in-process BM25 index."""

    def __init__(self):
        self.products: List[ProductDocument] = []
        self._bm25 = None
        self._tokenized_corpus: list[list[str]] = []
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        self.products = load_products()
        self._tokenized_corpus = [self._tokenize(p.text) for p in self.products]
        try:
            from rank_bm25 import BM25Okapi

            self._bm25 = BM25Okapi(self._tokenized_corpus)
        except Exception:
            self._bm25 = None
        self._loaded = True

    def search(self, query: str, top_k: int | None = None) -> List[Dict[str, Any]]:
        self.load()
        limit = top_k or settings.RETRIEVAL_SPARSE_TOP_K
        tokens = self._tokenize(query)
        if not self.products:
            return []

        if self._bm25 is not None:
            scores = self._bm25.get_scores(tokens)
        else:
            scores = [self._simple_score(tokens, doc_tokens) for doc_tokens in self._tokenized_corpus]

        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:limit]
        max_score = max((score for _, score in ranked), default=0.0) or 1.0
        results = []
        for idx, score in ranked:
            if score <= 0:
                continue
            product = self.products[idx]
            payload = dict(product.payload)
            payload["bm25_score"] = float(score) / float(max_score)
            payload["source"] = "bm25"
            results.append(payload)
        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text = text.lower()
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        words = re.findall(r"[a-zA-Z0-9]+", text)
        chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        return chinese_chars + chinese_terms + words

    @staticmethod
    def _simple_score(query_tokens: list[str], doc_tokens: list[str]) -> float:
        doc_set = set(doc_tokens)
        return float(sum(1 for token in query_tokens if token in doc_set))

