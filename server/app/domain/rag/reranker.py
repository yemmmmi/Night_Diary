"""交叉编码器重排序器，支持延迟加载与优雅降级。"""

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
    """使用 CrossEncoder 模型对融合后的检索候选进行重排序。

    与 V1 不同，配置是**实例级**的：不会向进程中泄漏任何 ``os.environ`` 写入
    （``HF_HUB_OFFLINE`` 等）。模型在首次调用 ``rerank`` 时延迟加载。
    任何加载 / 预测失败都会降级到 :meth:`fallback`，按原始融合顺序返回，不抛异常。
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
        """返回由交叉编码器相关性重新排序后的 top-k 候选。

        当模型不可用或打分抛出异常时，降级为原始融合顺序（截断到 ``top_k``）。
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
        """返回截断到 ``top_k`` 的原始融合候选，不带 rerank 得分。"""
        return candidates[: self.top_k]
