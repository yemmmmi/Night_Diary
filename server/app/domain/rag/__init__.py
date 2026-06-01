"""RAG foundation: chunking, BM25 indexing, and diary Chroma collections."""

from app.domain.rag.bm25 import BM25Index, tokenize
from app.domain.rag.chunker import ChunkSplitter
from app.domain.rag.collections import COLLECTION_NAME, DiaryCollectionManager
from app.domain.rag.types import BM25Doc, Chunk, SearchResult

__all__ = [
    "COLLECTION_NAME",
    "BM25Doc",
    "BM25Index",
    "Chunk",
    "ChunkSplitter",
    "DiaryCollectionManager",
    "SearchResult",
    "tokenize",
]
