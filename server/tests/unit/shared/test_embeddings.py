"""Unit tests for the embedding-function factory.

These run without the heavy ML stack: the ``chromadb`` import is stubbed so the
factory's lazy-import contract can be verified on any machine (CI included).
"""

from __future__ import annotations

import sys
import types

import pytest

from app.config import Settings


def _stub_chromadb(monkeypatch: pytest.MonkeyPatch, recorder: dict[str, object]) -> None:
    """Inject a fake ``chromadb.utils.embedding_functions`` into ``sys.modules``."""

    class FakeSentenceTransformerEmbeddingFunction:
        def __init__(self, model_name: str) -> None:
            recorder["model_name"] = model_name

    ef_module = types.ModuleType("chromadb.utils.embedding_functions")
    ef_module.SentenceTransformerEmbeddingFunction = FakeSentenceTransformerEmbeddingFunction  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "chromadb", types.ModuleType("chromadb"))
    monkeypatch.setitem(sys.modules, "chromadb.utils", types.ModuleType("chromadb.utils"))
    monkeypatch.setitem(sys.modules, "chromadb.utils.embedding_functions", ef_module)


def test_default_embedding_model_is_chinese() -> None:
    assert Settings().embedding_model_name == "BAAI/bge-small-zh-v1.5"


def test_build_embedding_function_passes_settings_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder: dict[str, object] = {}
    _stub_chromadb(monkeypatch, recorder)

    from app.shared.embeddings import build_embedding_function

    ef = build_embedding_function(Settings(embedding_model_name="BAAI/bge-base-zh-v1.5"))

    assert ef is not None
    assert recorder["model_name"] == "BAAI/bge-base-zh-v1.5"


def test_build_embedding_function_uses_default_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder: dict[str, object] = {}
    _stub_chromadb(monkeypatch, recorder)

    from app.shared.embeddings import build_embedding_function

    build_embedding_function()

    assert recorder["model_name"] == "BAAI/bge-small-zh-v1.5"


def test_module_import_defers_heavy_imports() -> None:
    """Importing the factory module must not eagerly import the ML stack.

    ``sentence_transformers`` is absent and ``chromadb``'s default embedding
    function is broken in some environments; a module-level import would crash
    on import. Reaching this assertion proves the imports are deferred to the
    call site.
    """
    import app.shared.embeddings as module

    assert hasattr(module, "build_embedding_function")
    assert "sentence_transformers" not in sys.modules
