"""Chroma embedding-function stub for tests that build the AI stack.

The heavy ML extras (``sentence-transformers``, ``torch``) are intentionally
absent from the core/CI dependency set (see the ``[eval]`` extra in
``pyproject.toml``), so unit tests must never load a real embedding model.
``app.shared.embeddings.build_embedding_function`` lazily imports
``SentenceTransformerEmbeddingFunction`` from ``chromadb`` at call time;
replacing that class attribute on the chromadb module short-circuits every
build site without touching application code.
"""

from __future__ import annotations

import pytest


class FakeEmbeddingFunction:
    """Chroma-compatible embedding function that needs no ML dependencies.

    Produces deterministic, content-derived 8-dimensional vectors so Chroma can
    index and query documents in tests without a real model.
    """

    name = "test-fake-embedding"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [
            [float((sum(ord(c) for c in text) + dim) % 100) / 100.0 for dim in range(8)]
            for text in input
        ]


def patch_chroma_embedding_function(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace chromadb's sentence-transformer embedding with the fake."""
    from chromadb.utils import embedding_functions as ef

    monkeypatch.setattr(
        ef,
        "SentenceTransformerEmbeddingFunction",
        FakeEmbeddingFunction,
        raising=False,
    )
