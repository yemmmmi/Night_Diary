"""In-memory Okapi BM25 index with incremental document maintenance."""

from __future__ import annotations

import math
from collections import Counter

import jieba

from app.domain.rag.types import BM25Doc, SearchResult

_K1 = 1.5
_B = 0.75
_MIN_TOKEN_LEN = 2


def tokenize(text: str) -> list[str]:
    """Chinese tokenization via jieba; drop single-character tokens (V1: len > 1)."""
    return [word for word in jieba.lcut(text) if len(word) >= _MIN_TOKEN_LEN]


class BM25Index:
    """Per-process BM25 index with O(1) amortized ``add_document`` / ``remove_document``.

    Maintains document frequency (``df``), average document length (``avgdl``), and
    per-document token lists incrementally instead of rebuilding the full corpus.
    """

    def __init__(self) -> None:
        self._docs: dict[str, BM25Doc] = {}
        self._tokens: dict[str, list[str]] = {}
        self._df: Counter[str] = Counter()
        self._doc_count = 0
        self._total_dl = 0

    @property
    def doc_count(self) -> int:
        return self._doc_count

    @property
    def avgdl(self) -> float:
        if self._doc_count == 0:
            return 0.0
        return self._total_dl / self._doc_count

    def clear(self) -> None:
        """Remove all indexed documents."""
        self._docs.clear()
        self._tokens.clear()
        self._df.clear()
        self._doc_count = 0
        self._total_dl = 0

    def build(self, documents: list[BM25Doc]) -> None:
        """Rebuild the index from a document list (bulk import / migration)."""
        self.clear()
        for document in documents:
            self.add_document(document)

    def add_document(self, document: BM25Doc) -> None:
        """Insert or replace a document without rebuilding the full index."""
        if document.doc_id in self._docs:
            self.remove_document(document.doc_id)

        tokens = tokenize(document.content)
        self._docs[document.doc_id] = document
        self._tokens[document.doc_id] = tokens
        self._doc_count += 1
        self._total_dl += len(tokens)

        for term in set(tokens):
            self._df[term] += 1

    def remove_document(self, doc_id: str) -> bool:
        """Remove a document and update corpus statistics."""
        if doc_id not in self._docs:
            return False

        tokens = self._tokens.pop(doc_id)
        self._docs.pop(doc_id)
        self._doc_count -= 1
        self._total_dl -= len(tokens)

        for term in set(tokens):
            self._df[term] -= 1
            if self._df[term] <= 0:
                del self._df[term]

        return True

    def search(self, query: str, *, top_k: int = 20) -> list[SearchResult]:
        """Return top-k chunks ranked by BM25 score."""
        if self._doc_count == 0:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scored: list[SearchResult] = []
        avgdl = self.avgdl

        for doc_id, document in self._docs.items():
            doc_tokens = self._tokens[doc_id]
            if not doc_tokens:
                continue

            term_freq = Counter(doc_tokens)
            doc_len = len(doc_tokens)
            score = 0.0

            for term in query_tokens:
                if term not in term_freq:
                    continue
                df = self._df.get(term, 0)
                idf = self._idf(df, self._doc_count)
                freq = term_freq[term]
                denom = freq + _K1 * (1.0 - _B + _B * doc_len / avgdl)
                score += idf * (freq * (_K1 + 1.0)) / denom

            if score > 0.0:
                scored.append(
                    SearchResult(
                        doc_id=doc_id,
                        content=document.content,
                        diary_id=document.diary_id,
                        bm25_score=score,
                        chunk_index=document.chunk_index,
                        chunk_total=document.chunk_total,
                        date=document.date,
                        tags=document.tags,
                    )
                )

        scored.sort(key=lambda hit: hit.bm25_score, reverse=True)
        return scored[:top_k]

    @staticmethod
    def _idf(df: int, corpus_size: int) -> float:
        """Okapi IDF (rank_bm25 / Lucene variant)."""
        if df <= 0 or corpus_size <= 0:
            return 0.0
        return math.log((corpus_size - df + 0.5) / (df + 0.5) + 1.0)
