"""CrisisGuard — shared crisis detection and safety response for both scenes.

Extracted from ``SupervisorAgent._detect_crisis`` so that scene 2 (multi-turn
conversation) can use the same safety net without depending on the supervisor.

Both the diary analysis pipeline (scene 1) and the conversation AI (scene 2)
call :meth:`detect` on user input. When it returns ``True``, the caller must
short-circuit normal generation and return :attr:`safe_response` verbatim.
"""

from __future__ import annotations

import logging

from app.domain.skills.crisis_detector import CRISIS_RESOURCES
from app.shared.emotion_estimator import EmotionEstimator, get_emotion_estimator

logger = logging.getLogger(__name__)

#: Pre-built response returned when crisis is detected.
#: Appended to the empathy reply in scene 1, returned directly in scene 2.
CRISIS_SAFE_RESPONSE = (
    "我能感受到你现在正承受着巨大的痛苦, 我在这里陪着你。\n"
    "你的感受是真实的, 但请不要独自承受这些。\n\n"
    + CRISIS_RESOURCES
)


class CrisisGuard:
    """Shared crisis detection wrapping :class:`EmotionEstimator`.

    The estimator is the single source of truth for the keyword heuristic and
    the crisis score threshold — no third copy of the lexicon exists.
    """

    def __init__(self, emotion_estimator: EmotionEstimator | None = None) -> None:
        self._emotion = emotion_estimator or get_emotion_estimator()

    @property
    def safe_response(self) -> str:
        """Return the safety resources text to send when crisis is detected."""
        return CRISIS_SAFE_RESPONSE

    def detect(self, text: str) -> bool:
        """Return ``True`` if *text* shows crisis-level signals.

        Two checks (either triggers):
        1. ``has_severe_signal`` — explicit self-harm / hopelessness keywords.
        2. ``score < crisis_threshold`` — overall emotion score below -0.7.
        """
        if not text or not text.strip():
            return False
        if self._emotion.has_severe_signal(text):
            logger.warning("CrisisGuard: severe signal detected")
            return True
        if self._emotion.score(text) < self._emotion.crisis_threshold:
            logger.warning("CrisisGuard: emotion score below crisis threshold")
            return True
        return False


_singleton: CrisisGuard | None = None


def get_crisis_guard() -> CrisisGuard:
    """Return a process-wide :class:`CrisisGuard` singleton."""
    global _singleton
    if _singleton is None:
        _singleton = CrisisGuard()
    return _singleton


__all__ = ["CRISIS_SAFE_RESPONSE", "CrisisGuard", "get_crisis_guard"]
