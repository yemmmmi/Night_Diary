"""Embedding utilities for episodic memory vectorization (V3 P4).

Provides ``Embedder`` base class + :class:`BgeEmbedder` (production,
``bge-small-zh-v1.5``) + :class:`StubEmbedder` (deterministic, for unit tests).

Design notes
------------
* ``sentence-transformers`` is an *optional* ``[eval]`` extra (see
  ``pyproject.toml``); the heavy import lives inside :meth:`BgeEmbedder.embed`
  so importing this module never pulls ``torch`` or triggers a model download
  (mirrors :meth:`app.domain.rag.reranker.Reranker._default_load` and
  :func:`app.shared.embeddings.build_embedding_function`).
* :class:`BgeEmbedder` lazy-loads the model on the first ``embed`` call and
  returns L2-normalized vectors (``normalize_embeddings=True``), so cosine
  similarity reduces to a plain dot product downstream.
* :class:`StubEmbedder` derives a 32-dim vector from a SHA-256 digest. It is
  deterministic across processes (Python's built-in ``hash()`` is randomized
  for strings via ``PYTHONHASHSEED`` and must NOT be used here) and needs no
  model download — making it ideal for fast, hermetic unit tests.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


class Embedder:
    """Base class / protocol for text embedders.

    Subclasses must implement :meth:`embed`, mapping a text string to a
    list of floats (the vector). Producers of vectors (e.g. episodic memory)
    depend on this interface rather than any concrete implementation, so a
    :class:`StubEmbedder` can be injected in unit tests.
    """

    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class BgeEmbedder(Embedder):
    """SentenceTransformer-based embedder using ``bge-small-zh-v1.5``.

    Lazy-loads the model on the first :meth:`embed` call (not in ``__init__``)
    to keep import time cheap and avoid touching the network until needed.
    Returns L2-normalized vectors (suitable for cosine similarity via dot
    product).

    Requires the ``sentence-transformers`` extra (``pip install -e ".[eval]"``);
    callers that may run without it should guard construction or inject a
    :class:`StubEmbedder` instead.
    """

    DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or self.DEFAULT_MODEL
        self._model: Any | None = None

    def embed(self, text: str) -> list[float]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        vec = self._model.encode([text], normalize_embeddings=True)
        result: list[float] = vec[0].tolist()
        return result


class StubEmbedder(Embedder):
    """Deterministic stub embedder for unit tests (no model download).

    Derives a 32-dim vector from the SHA-256 digest of the text. Each of the
    first 32 bytes of the digest is scaled to ``[0, 1]``. The mapping is
    stable across processes (unlike Python's ``hash()``) and needs no model
    download — it is not semantically meaningful, only stable.
    """

    DIMENSION = 32

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [byte / 255.0 for byte in digest[: self.DIMENSION]]
