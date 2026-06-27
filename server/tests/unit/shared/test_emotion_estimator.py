"""Unit tests for the shared EmotionEstimator."""

from __future__ import annotations

from app.shared.emotion_estimator import EmotionEstimator


def test_empty_text_is_neutral() -> None:
    est = EmotionEstimator()
    result = est.estimate("")
    assert result.score == 0.0
    assert result.label == "neutral"
    assert result.matched_severe == ()


def test_crisis_text_scores_below_threshold() -> None:
    est = EmotionEstimator()
    result = est.estimate("我不想活了，撑不下去了。")
    assert result.score < est.crisis_threshold
    assert result.label == "crisis"
    assert "撑不下去" in result.matched_severe


def test_positive_text_is_positive() -> None:
    est = EmotionEstimator()
    result = est.estimate("今天很开心，感觉很幸福也很感恩。")
    assert result.score > 0
    assert result.label == "positive"
    assert "开心" in result.matched_positive


def test_score_is_clamped_to_unit_range() -> None:
    est = EmotionEstimator()
    # Many severe keywords would exceed -1.0 without clamping.
    score = est.score("想死 不想活 自杀 绝望 崩溃 生不如死 跳楼 割腕")
    assert score == -1.0


def test_has_severe_signal_and_negative_count() -> None:
    est = EmotionEstimator()
    assert est.has_severe_signal("我想死") is True
    assert est.has_severe_signal("今天有点难过") is False
    assert est.count_negative_signals("我很焦虑，也很孤独，还失眠") == 3


def test_custom_lexicon_and_weights() -> None:
    est = EmotionEstimator(
        negative_keywords=("摆烂",),
        negative_weight=-0.5,
        positive_keywords=(),
        severe_keywords=(),
    )
    result = est.estimate("今天只想摆烂")
    assert result.score == -0.5
    assert result.matched_negative == ("摆烂",)
    assert est.has_severe_signal("我想死") is False


# ── Negation prefix detection (PR-1: fix/crisis-emotion-bug) ──


def test_negation_prefix_flips_positive() -> None:
    """'不开心' must score negative — not match '开心' as positive."""
    est = EmotionEstimator()
    result = est.estimate("不开心")
    assert result.score < 0
    assert result.label != "positive"
    assert "开心" not in result.matched_positive


def test_negation_prefix_variants() -> None:
    """Multiple negation prefixes all flip positive keywords."""
    est = EmotionEstimator()
    for text in ("不快乐", "没幸福", "不满足", "别期待"):
        result = est.estimate(text)
        assert result.score <= 0, f"Expected non-positive for '{text}', got {result.score}"


def test_pure_positive_unchanged() -> None:
    """Pure positive keywords without negation remain positive (regression guard)."""
    est = EmotionEstimator()
    for text in ("开心", "快乐", "幸福"):
        result = est.estimate(text)
        assert result.score > 0, f"Expected positive for '{text}', got {result.score}"
    # Multiple positive words should exceed positive_threshold
    result = est.estimate("开心快乐幸福")
    assert result.label == "positive"


def test_double_negation_restores_positive() -> None:
    """'不是不开心' is double negation → neutral or positive."""
    est = EmotionEstimator()
    result = est.estimate("不是不开心")
    # Double negation → even count → treated as positive
    assert "开心" in result.matched_positive


def test_crisis_negation_not_masked() -> None:
    """Crisis keywords like '不想活了' must still be detected as severe."""
    est = EmotionEstimator()
    result = est.estimate("不想活了")
    # "不想活" is a severe keyword — must be detected despite "不" prefix
    assert "不想活" in result.matched_severe
    assert result.score < 0
    # Multiple severe keywords should trigger crisis threshold
    result2 = est.estimate("不想活了，撑不下去了")
    assert result2.score <= est.crisis_threshold
    assert result2.label == "crisis"
