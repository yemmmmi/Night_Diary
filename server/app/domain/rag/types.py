"""RAG domain types for diary chunking and keyword retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    """A text segment derived from a diary entry, ready for vector/BM25 indexing."""

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
    """Document payload stored in a :class:`BM25Index`."""

    doc_id: str
    content: str
    diary_id: str
    chunk_index: int = 0
    chunk_total: int = 1
    date: str = ""
    tags: str = ""


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A single BM25 keyword retrieval hit."""

    doc_id: str
    content: str
    diary_id: str
    bm25_score: float
    chunk_index: int = 0
    chunk_total: int = 1
    date: str = ""
    tags: str = ""
