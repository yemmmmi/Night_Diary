"""Embedding-function factory for vector retrieval.

The heavy ``chromadb`` / ``sentence-transformers`` imports live inside the
function body so importing this module never pulls ``torch`` or triggers a model
download (mirrors :meth:`app.domain.rag.reranker.Reranker._default_load`).

Callers build the embedding function from :class:`~app.config.Settings` and
inject it into :class:`~app.domain.rag.collections.DiaryCollectionManager` or
:class:`~app.domain.knowledge.store.DomainKnowledgeStore` via DI. Domain code
must never import the model directly or read the model name with ``os.getenv``.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings


def build_embedding_function(settings: Settings | None = None) -> Any:
    """Return a Chroma-compatible embedding function for ``embedding_model_name``.

    The default is a Chinese-first model (``BAAI/bge-small-zh-v1.5``); the diary
    corpus is Chinese, so an English model would degrade vector search to noise.
    The return value satisfies Chroma's ``EmbeddingFunction`` protocol and is
    used for both indexing and query embedding within a single process.
    """
    resolved = settings or get_settings()
    # chromadb lazily exposes this class via __getattr__, so it is importable at
    # runtime but invisible to mypy's static analysis.
    from chromadb.utils.embedding_functions import (  # type: ignore[attr-defined]
        SentenceTransformerEmbeddingFunction,
    )

    return SentenceTransformerEmbeddingFunction(model_name=resolved.embedding_model_name)
