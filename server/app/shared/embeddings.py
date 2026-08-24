"""Embedding-function factory for vector retrieval.

Two backends are supported:

* Cloud API (preferred when ``embedding_api_key`` is set): calls an
  OpenAI-compatible ``/embeddings`` endpoint (e.g. Qwen/DashScope
  ``text-embedding-v3``). Avoids heavy local ML deps and model downloads, which
  are often painful on constrained networks.
* Local sentence-transformers model (fallback when no API key is configured):
  ``BAAI/bge-small-zh-v1.5``. The heavy imports live inside the function body
  so importing this module never pulls ``torch`` or triggers a model download.

Callers build the embedding function from :class:`~app.config.Settings` and
inject it into :class:`~app.domain.rag.collections.DiaryCollectionManager` or
:class:`~app.domain.knowledge.store.DomainKnowledgeStore` via DI. Domain code
must never import the model directly or read the model name with ``os.getenv``.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class OpenAICompatibleEmbeddingFunction:
    """Chroma-compatible embedding function backed by an OpenAI-compatible API.

    Satisfies the ``EmbeddingFunction`` protocol used by the domain layer:
    ``__call__(input: list[str]) -> list[list[float]]``.

    Uses the ``openai`` SDK against ``settings.embedding_base_url`` with
    ``settings.embedding_model``. Batch embeds and flattens responses in input
    order.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._settings.embedding_api_key,
                base_url=self._settings.embedding_base_url,
            )
        return self._client

    def __call__(self, input: list[str]) -> list[list[float]]:
        if not input:
            return []
        client = self._get_client()
        resp = client.embeddings.create(
            model=self._settings.embedding_model,
            input=input,
        )
        # OpenAI-compatible responses return items in the same order as ``input``.
        return [item.embedding for item in resp.data]


def build_embedding_function(settings: Settings | None = None) -> Any:
    """Return a Chroma-compatible embedding function.

    Prefers the cloud API when ``embedding_api_key`` is configured (avoids local
    ML deps / model downloads); otherwise falls back to the local Chinese-first model
    (``BAAI/bge-small-zh-v1.5``). The return value satisfies Chroma's
    ``EmbeddingFunction`` protocol and is used for both indexing and query embedding
    within a single process.
    """
    resolved = settings or get_settings()
    if resolved.embedding_api_key:
        logger.info(
            "Using cloud embedding API: base_url=%s model=%s",
            resolved.embedding_base_url,
            resolved.embedding_model,
        )
        return OpenAICompatibleEmbeddingFunction(resolved)

    # Local fallback: chromadb lazily exposes this class via __getattr__, so it is
    # importable at runtime but invisible to mypy's static analysis.
    from chromadb.utils.embedding_functions import (  # type: ignore[attr-defined]
        SentenceTransformerEmbeddingFunction,
    )

    return SentenceTransformerEmbeddingFunction(model_name=resolved.embedding_model_name)
