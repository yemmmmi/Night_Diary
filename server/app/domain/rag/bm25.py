"""内存中的 Okapi BM25 索引，支持增量式文档维护。"""

from __future__ import annotations

import math
from collections import Counter

import jieba

from app.domain.rag.types import BM25Doc, SearchResult

_K1 = 1.5
_B = 0.75
_MIN_TOKEN_LEN = 2


def tokenize(text: str) -> list[str]:
    """通过 jieba 进行中文分词；丢弃单字符 token（V1：len > 1）。"""
    return [word for word in jieba.lcut(text) if len(word) >= _MIN_TOKEN_LEN]


class BM25Index:
    """进程内的 BM25 索引，``add_document`` / ``remove_document`` 均摊 O(1)。

    以增量方式维护文档频率（``df``）、平均文档长度（``avgdl``）以及
    每个文档的 token 列表，而非每次都重建整个语料库。
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

    def known_doc_ids(self) -> set[str]:
        """返回当前索引中所有 doc_id 的集合。"""
        return set(self._docs.keys())

    @property
    def avgdl(self) -> float:
        if self._doc_count == 0:
            return 0.0
        return self._total_dl / self._doc_count

    def clear(self) -> None:
        """移除所有已索引的文档。"""
        self._docs.clear()
        self._tokens.clear()
        self._df.clear()
        self._doc_count = 0
        self._total_dl = 0

    def build(self, documents: list[BM25Doc]) -> None:
        """根据文档列表重建索引（批量导入 / 迁移）。"""
        self.clear()
        for document in documents:
            self.add_document(document)

    def add_document(self, document: BM25Doc) -> None:
        """插入或替换一个文档，无需重建整个索引。"""
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
        """移除一个文档并更新语料库统计信息。"""
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
        """返回按 BM25 得分排序的 top-k chunk。"""
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
        """Okapi IDF（rank_bm25 / Lucene 变体）。"""
        if df <= 0 or corpus_size <= 0:
            return 0.0
        return math.log((corpus_size - df + 0.5) / (df + 0.5) + 1.0)
