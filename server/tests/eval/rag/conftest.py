"""Fixtures for the offline RAG retrieval eval.

Loads the fixed corpus/queries, builds a BM25 index (always available) and a
temporary Chroma vector collection (only when ``chromadb`` + the embedding model
are usable). Model-dependent fixtures degrade to ``None`` so the eval still
reports the BM25 baseline on any machine; dependent branches are *skipped*
rather than recorded as degraded numbers.

This module is intentionally outside CI: ``make eval-rag`` runs it manually.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.config import get_settings
from app.domain.rag.bm25 import BM25Index
from app.domain.rag.chunker import ChunkSplitter
from app.domain.rag.collections import DiaryCollectionManager
from app.domain.rag.reranker import Reranker
from app.domain.rag.types import BM25Doc, RetrievalResult

DATA_DIR = Path(__file__).parent

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def eval_diaries() -> list[dict[str, str]]:
    return json.loads((DATA_DIR / "diaries.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def eval_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def chunk_splitter() -> ChunkSplitter:
    """One splitter shared by BM25 and the vector collection for identical chunks."""
    return ChunkSplitter()


@pytest.fixture(scope="session")
def bm25_index(
    eval_diaries: list[dict[str, str]],
    chunk_splitter: ChunkSplitter,
) -> BM25Index:
    """BM25 index over the same chunks the vector collection sees."""
    index = BM25Index()
    for diary in eval_diaries:
        chunks = chunk_splitter.split_chunks(
            diary["content"],
            diary_id=diary["diary_id"],
            date=diary.get("date", ""),
            tags=diary.get("tags", ""),
        )
        for chunk in chunks:
            index.add_document(
                BM25Doc(
                    doc_id=chunk.doc_id,
                    content=chunk.content,
                    diary_id=chunk.diary_id,
                    chunk_index=chunk.chunk_index,
                    chunk_total=chunk.chunk_total,
                    date=chunk.date,
                    tags=chunk.tags,
                )
            )
    return index


@pytest.fixture(scope="session")
def vector_collection(
    eval_diaries: list[dict[str, str]],
    chunk_splitter: ChunkSplitter,
) -> Iterator[DiaryCollectionManager | None]:
    """Yield a temp-Chroma-backed collection manager, or ``None`` if unavailable.

    Builds the Chinese embedding function via DI (Settings -> factory) and indexes
    all diaries. Any failure (missing chromadb/sentence-transformers, broken
    onnxruntime, no network for the model) degrades to ``None`` so the eval can
    still run the BM25 branch. The temp dir is always cleaned up.
    """
    settings = get_settings()
    tmp_dir = tempfile.mkdtemp(prefix="nd_eval_chroma_")
    manager: DiaryCollectionManager | None = None

    try:
        import chromadb

        from app.shared.embeddings import build_embedding_function

        client = chromadb.PersistentClient(path=tmp_dir)
        embedding_function = build_embedding_function(settings)
        manager = DiaryCollectionManager(
            settings=settings,
            chroma_client=client,
            embedding_function=embedding_function,
            chunk_splitter=chunk_splitter,
        )
        for diary in eval_diaries:
            manager.upsert_diary(
                diary["diary_id"],
                diary["content"],
                date=diary.get("date", ""),
                tags=diary.get("tags", ""),
            )
        logger.info("Vector branch ready: indexed %d diaries", len(eval_diaries))
    except Exception as exc:
        # Eval must degrade (skip dependent branches), never crash the suite.
        logger.warning("Vector branch unavailable (skipping vector/hybrid): %s", exc)
        manager = None

    try:
        yield manager
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def reranker() -> Reranker | None:
    """Return a usable :class:`Reranker`, or ``None`` if the model cannot load.

    We probe with a single pair: a successful rerank populates ``rerank_score``;
    a degraded ``fallback`` leaves it ``None``. We skip the rerank branch in the
    latter case rather than recording fallback (= RRF order) numbers as a rerank
    baseline.
    """
    candidate = Reranker(top_k=5)
    probe = candidate.rerank(
        "测试查询",
        [RetrievalResult(doc_id="probe", content="这是一段用于探测的文本", diary_id="probe")],
    )
    if probe and probe[0].rerank_score is not None:
        return candidate
    logger.warning("Reranker model unavailable; rerank branch will be skipped")
    return None
