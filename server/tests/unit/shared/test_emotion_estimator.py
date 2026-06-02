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
