"""Cross-encoder reranker with lazy loading and graceful degradation."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from typing import Any

from app.domain.memory.types import EpisodicEntry
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
            raw_scores = model.predict(pairs)
            score_values = [float(s) for s in raw_scores]
            if len(score_values) != len(candidates):
                logger.warning(
                    "Reranker score count mismatch: candidates=%d scores=%d; "
                    "pairing min length only",
                    len(candidates),
                    len(score_values),
                )
            pair_count = min(len(candidates), len(score_values))
            scored = [
                dataclasses.replace(
                    candidates[i],
                    rerank_score=score_values[i],
                    score=score_values[i],
                )
                for i in range(pair_count)
            ]
            scored.sort(key=lambda result: result.rerank_score or 0.0, reverse=True)
            return scored[: self.top_k]
        except Exception as exc:
            logger.warning("Reranker predict failed; degrading: %s", exc)
            return self.fallback(candidates)

    def fallback(self, candidates: list[RetrievalResult]) -> list[RetrievalResult]:
        """Return original fused candidates truncated to ``top_k``, no rerank score."""
        return candidates[: self.top_k]

    def rerank_episodic(
        self, query: str, entries: list[EpisodicEntry]
    ) -> list[EpisodicEntry]:
        """Rerank episodic entries by query relevance using the cross-encoder.

        Mirrors :meth:`rerank` but accepts ``EpisodicEntry`` instead of
        ``RetrievalResult``. Uses ``event_summary`` + ``tags`` as the
        cross-encoder content (short summaries need tag disambiguation).
        Returns entries sorted by relevance (most relevant first), without
        ``top_k`` truncation — the caller (Stage 3 of ``retrieve_relevant``)
        already narrows the candidate pool.

        Falls back to the original order when the model is unavailable or
        scoring raises; never propagates exceptions.
        """
        if not entries:
            return []

        model = self._load_model()
        if model is None:
            return list(entries)

        pairs = [(query, self._entry_to_text(entry)) for entry in entries]
        try:
            raw_scores = model.predict(pairs)
            score_values = [float(s) for s in raw_scores]
        except Exception as exc:
            logger.warning("Reranker episodic predict failed; degrading: %s", exc)
            return list(entries)

        pair_count = min(len(entries), len(score_values))
        ranked = sorted(
            range(pair_count), key=lambda i: score_values[i], reverse=True
        )
        return [entries[i] for i in ranked]

    @staticmethod
    def _entry_to_text(entry: EpisodicEntry) -> str:
        """Convert an ``EpisodicEntry`` to text for cross-encoder input.

        Uses ``event_summary`` + ``tags`` (tags help disambiguate short
        summaries, e.g. "失眠" + ["睡眠", "健康"]).
        """
        text = entry.event_summary
        if entry.tags:
            text += " " + " ".join(entry.tags)
        return text
