"""用于日记分块与关键词检索的 RAG 领域类型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    """从一条日记条目派生出的文本片段，可用于向量 / BM25 索引。"""

    content: str
    diary_id: str
    chunk_index: int
    chunk_total: int
    date: str = ""
    tags: str = ""
    doc_id: str = ""
    doc_type: str = "chunk"
    parent_id: str = ""


@dataclass(frozen=True, slots=True)
class BM25Doc:
    """存储在 :class:`BM25Index` 中的文档载荷。"""

    doc_id: str
    content: str
    diary_id: str
    chunk_index: int = 0
    chunk_total: int = 1
    date: str = ""
    tags: str = ""


@dataclass(frozen=True, slots=True)
class SearchResult:
    """单次 BM25 关键词检索命中。"""

    doc_id: str
    content: str
    diary_id: str
    bm25_score: float
    chunk_index: int = 0
    chunk_total: int = 1
    date: str = ""
    tags: str = ""


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """由 :class:`HybridRetriever` 产出的融合 / 重排序后的检索命中。

    ``score`` 携带最近一个阶段的得分（RRF 或 rerank）。各阶段得分会单独标注，
    以便调用方检查整个流水线。
    """

    doc_id: str
    content: str
    diary_id: str
    score: float = 0.0
    rrf_score: float | None = None
    rerank_score: float | None = None
    chunk_index: int = 0
    chunk_total: int = 1
    date: str = ""
    tags: str = ""
