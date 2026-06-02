"""Keyword-based emotion estimation shared across the AI pipeline.

This is the single source of truth for the lightweight, LLM-free emotion
heuristic. In V1 the same keyword scoring was copy-pasted into both
``empathy_agent`` and ``crisis_detector`` (坏味 3: duplicated implementation);
here it lives once and is injected where needed.

The estimator is a configurable *instance* (no module-level mutable state). The
default lexicon and weights reproduce V1's behaviour so existing crisis-detection
thresholds stay valid. Callers that want different sensitivity pass their own
lexicon/weights through the constructor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Default lexicon — the union of the V1 empathy_agent / crisis_detector word
# lists, de-duplicated. "崩溃"/"绝望" are treated as severe (not merely negative)
# so they are never double-counted across the two tiers.
_DEFAULT_SEVERE_NEGATIVE: tuple[str, ...] = (
    "想死",
    "不想活",
    "自杀",
    "结束生命",
    "活着没意思",
    "我不想活了",
    "绝望",
    "崩溃",
    "撑不下去",
    "没有希望",
    "生不如死",
    "伤害自己",
    "自残",
    "割腕",
    "跳楼",
)

_DEFAULT_NEGATIVE: tuple[str, ...] = (
    "难过",
    "痛苦",
    "焦虑",
    "抑郁",
    "孤独",
    "害怕",
    "愤怒",
    "失望",
    "无助",
    "悲伤",
    "压抑",
    "烦躁",
    "失眠",
    "哭",
    "受不了",
    "太累了",
)

_DEFAULT_POSITIVE: tuple[str, ...] = (
    "开心",
    "快乐",
    "幸福",
    "感恩",
    "满足",
    "期待",
    "兴奋",
    "温暖",
    "感动",
    "自豪",
    "放松",
    "愉快",
)


@dataclass(frozen=True, slots=True)
class EmotionEstimate:
    """Result of a keyword-based emotion estimation pass."""

    score: float
    """Polarity in ``[-1.0, 1.0]``; negative is distress, positive is wellbeing."""

    label: str
    """One of ``crisis`` / ``negative`` / ``neutral`` / ``positive``."""

    matched_severe: tuple[str, ...] = field(default_factory=tuple)
    matched_negative: tuple[str, ...] = field(default_factory=tuple)
    matched_positive: tuple[str, ...] = field(default_factory=tuple)


class EmotionEstimator:
    """Estimate emotional polarity from text using a keyword lexicon.

    The heuristic is deliberately cheap: it runs before any LLM call so the
    pipeline can short-circuit to a crisis-safe path without spending tokens.
    It is *not* a replacement for the LLM sentiment analysis in
    :class:`~app.domain.skills.sentiment_skill.SentimentSkill`; it is the fast
    pre-screen that feeds routing and crisis detection.
    """

    def __init__(
        self,
        *,
        severe_keywords: tuple[str, ...] = _DEFAULT_SEVERE_NEGATIVE,
        negative_keywords: tuple[str, ...] = _DEFAULT_NEGATIVE,
        positive_keywords: tuple[str, ...] = _DEFAULT_POSITIVE,
        severe_weight: float = -0.4,
        negative_weight: float = -0.15,
        positive_weight: float = 0.15,
        crisis_threshold: float = -0.7,
        negative_threshold: float = -0.2,
        positive_threshold: float = 0.2,
    ) -> None:
        self._severe = severe_keywords
        self._negative = negative_keywords
        self._positive = positive_keywords
        self._severe_weight = severe_weight
        self._negative_weight = negative_weight
        self._positive_weight = positive_weight
        self._crisis_threshold = crisis_threshold
        self._negative_threshold = negative_threshold
        self._positive_threshold = positive_threshold

    @property
    def crisis_threshold(self) -> float:
        return self._crisis_threshold

    def estimate(self, text: str) -> EmotionEstimate:
        """Return the full estimate (score + label + matched keywords)."""
        if not text:
            return EmotionEstimate(score=0.0, label="neutral")

        matched_severe = tuple(w for w in self._severe if w in text)
        matched_negative = tuple(w for w in self._negative if w in text)
        matched_positive = tuple(w for w in self._positive if w in text)

        raw = (
            len(matched_severe) * self._severe_weight
            + len(matched_negative) * self._negative_weight
            + len(matched_positive) * self._positive_weight
        )
        score = max(-1.0, min(1.0, raw))

        return EmotionEstimate(
            score=score,
            label=self.label_for(score),
            matched_severe=matched_severe,
            matched_negative=matched_negative,
            matched_positive=matched_positive,
        )

    def score(self, text: str) -> float:
        """Return only the polarity score in ``[-1.0, 1.0]``."""
        return self.estimate(text).score

    def label_for(self, score: float) -> str:
        """Map a polarity score to a discrete emotion label."""
        if score <= self._crisis_threshold:
            return "crisis"
        if score <= self._negative_threshold:
            return "negative"
        if score >= self._positive_threshold:
            return "positive"
        return "neutral"

    def has_severe_signal(self, text: str) -> bool:
        """Whether the text contains any severe (crisis-level) keyword."""
        return any(word in text for word in self._severe)

    def count_negative_signals(self, text: str) -> int:
        """Count distinct general-negative keywords present in the text."""
        return sum(1 for word in self._negative if word in text)
