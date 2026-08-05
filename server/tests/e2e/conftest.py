"""Fixtures for end-to-end API flow tests."""

from __future__ import annotations

import pytest

from tests.embedding_stub import patch_chroma_embedding_function


@pytest.fixture(autouse=True)
def _no_real_embedding_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """E2E tests never load the real embedding model (heavy ML deps absent)."""
    patch_chroma_embedding_function(monkeypatch)
