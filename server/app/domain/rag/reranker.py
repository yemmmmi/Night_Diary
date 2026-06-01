"""Cross-encoder reranker with lazy loading and graceful degradation."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from typing import Any

from app.domain.rag.types import RetrievalResult

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-reranker-base"
DEFAULT_TOP_K = 5

ModelLoader = Callable[[], Any]


class Reranker:
    """Rerank fused retrieval candidates with a CrossEncoder model.

    Unlike V1, configuration is **instance-level**: no ``os.environ`` writes
    (``HF_HUB_OFFLINE`` etc.) leak into the process. The model is lazy-loaded on
    first ``rerank`` call. Any load/predict failure degrades to
    :meth:`fallback`, returning the original fused order without raising.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        top_k: int = DEFAULT_TOP_K,
        local_files_only: bool = False,
        model_loader: ModelLoader | None = None,
    ) -> None:
        self.model_name = model_name
        self.top_k = top_k
        self.local_files_only = local_files_only
        self._model_loader = model_loader
        self._model: Any | None = None
        self._load_failed = False

    def _load_model(self) -> Any | None:
        if self._model is not None:
            return self._model
        if self._load_failed:
            return None

        try:
            if self._model_loader is not None:
                self._model = self._model_loader()
            else:
                self._model = self._default_load()
            logger.info("Reranker model loaded: %s", self.model_name)
        except Exception as exc:
            self._load_failed = True
            logger.warning("Reranker model load failed (%s); degrading: %s", self.model_name, exc)
            return None

        return self._model

    def _default_load(self) -> Any:
        from sentence_transformers import CrossEncoder

        kwargs: dict[str, Any] = {}
        if self.local_files_only:
            kwargs["automodel_args"] = {"local_files_only": True}
            kwargs["tokenizer_args"] = {"local_files_only": True}
        return CrossEncoder(self.model_name, **kwargs)

    def rerank(self, query: str, candidates: list[RetrievalResult]) -> list[RetrievalResult]:
        """Return the top-k candidates reordered by cross-encoder relevance.

        Falls back to the original fused order (truncated to ``top_k``) when the
        model is unavailable or scoring raises.
        """
        if not candidates:
            return []

        model = self._load_model()
        if model is None:
            return self.fallback(candidates)

        try:
            pairs = [(query, candidate.content) for candidate in candidates]
            scores = model.predict(pairs)
            scored = [
                dataclasses.replace(
                    candidate,
                    rerank_score=float(score),
                    score=float(score),
                )
                for candidate, score in zip(candidates, scores, strict=False)
            ]
            scored.sort(key=lambda result: result.rerank_score or 0.0, reverse=True)
            return scored[: self.top_k]
        except Exception as exc:
            logger.warning("Reranker predict failed; degrading: %s", exc)
            return self.fallback(candidates)

    def fallback(self, candidates: list[RetrievalResult]) -> list[RetrievalResult]:
        """Return original fused candidates truncated to ``top_k``, no rerank score."""
        return candidates[: self.top_k]
