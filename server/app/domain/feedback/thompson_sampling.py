"""Thompson Sampling for adaptive response style selection."""

from __future__ import annotations

import logging
import random
from typing import ClassVar

from app.domain.feedback.types import (
    DEFAULT_STYLE,
    STYLES,
    StylePreferenceRecord,
    StylePreferenceStore,
)

logger = logging.getLogger(__name__)


class ThompsonSampling:
    """Beta-bandit selector for empathetic/practical/philosophical/humorous styles."""

    STYLES: ClassVar[tuple[str, ...]] = STYLES
    DEFAULT_STYLE: ClassVar[str] = DEFAULT_STYLE

    def __init__(self, store: StylePreferenceStore | None = None) -> None:
        self._store = store

    def sample_style(self, user_id: str = "default") -> str:
        """Sample the highest Beta draw across all supported styles."""
        if self._store is None:
            return self.DEFAULT_STYLE

        try:
            preferences = self._store.ensure_preferences(user_id, list(self.STYLES))
            params = self._params_from_preferences(preferences)
            return self.sample_from_params(params)
        except Exception as exc:
            logger.warning(
                "Thompson Sampling failed for user_id=%s: %s. Falling back to %s",
                user_id,
                exc,
                self.DEFAULT_STYLE,
            )
            return self.DEFAULT_STYLE

    def update_reward(self, user_id: str, style: str, *, is_positive: bool) -> None:
        """Increment alpha on positive feedback and beta on negative feedback."""
        if self._store is None:
            return

        try:
            preferences = self._store.ensure_preferences(user_id, list(self.STYLES))
            current = next((pref for pref in preferences if pref.style == style), None)
            if current is None:
                logger.error("Missing style preference user_id=%s style=%s", user_id, style)
                return

            alpha = current.alpha + (1 if is_positive else 0)
            beta = current.beta + (0 if is_positive else 1)
            self._store.update_preference(user_id, style, alpha=alpha, beta=beta)
            logger.debug(
                "Updated Thompson reward user_id=%s style=%s positive=%s alpha=%s beta=%s",
                user_id,
                style,
                is_positive,
                alpha,
                beta,
            )
        except Exception as exc:
            logger.error(
                "Failed to update Thompson reward user_id=%s style=%s: %s",
                user_id,
                style,
                exc,
            )

    def get_style_params(self, user_id: str = "default") -> dict[str, dict[str, float]]:
        """Return alpha/beta parameters for every supported style."""
        if self._store is None:
            return {style: {"alpha": 1.0, "beta": 1.0} for style in self.STYLES}

        try:
            preferences = self._store.ensure_preferences(user_id, list(self.STYLES))
            return {pref.style: {"alpha": pref.alpha, "beta": pref.beta} for pref in preferences}
        except Exception as exc:
            logger.warning("Failed to load style params user_id=%s: %s", user_id, exc)
            return {style: {"alpha": 1.0, "beta": 1.0} for style in self.STYLES}

    @classmethod
    def sample_from_params(
        cls,
        params: dict[str, tuple[float, float]],
        *,
        rng: random.Random | None = None,
    ) -> str:
        """Sample a style from explicit Beta parameters (used in tests/stat checks)."""
        random_source = rng or random
        samples = {
            style: random_source.betavariate(alpha, beta) for style, (alpha, beta) in params.items()
        }
        return max(samples, key=lambda style: samples[style])

    @staticmethod
    def _params_from_preferences(
        preferences: list[StylePreferenceRecord],
    ) -> dict[str, tuple[float, float]]:
        params = {pref.style: (pref.alpha, pref.beta) for pref in preferences}
        for style in STYLES:
            params.setdefault(style, (1.0, 1.0))
        return params
