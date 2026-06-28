"""Tests for the shared CrisisGuard component."""

from __future__ import annotations

from app.shared.crisis_guard import CRISIS_SAFE_RESPONSE, CrisisGuard


def test_detect_severe_signal() -> None:
    guard = CrisisGuard()
    assert guard.detect("我不想活了，想结束这一切") is True


def test_detect_low_emotion_score() -> None:
    guard = CrisisGuard()
    # Multiple negative keywords should push score below crisis threshold
    assert guard.detect("崩溃 绝望 痛苦 无助 恐惧 撑不住") is True


def test_detect_normal_text_returns_false() -> None:
    guard = CrisisGuard()
    assert guard.detect("今天天气不错，去公园散步了") is False
    assert guard.detect("工作有点累但还好") is False


def test_detect_empty_text_returns_false() -> None:
    guard = CrisisGuard()
    assert guard.detect("") is False
    assert guard.detect("   ") is False


def test_safe_response_contains_resources() -> None:
    guard = CrisisGuard()
    response = guard.safe_response
    assert "400-161-9995" in response
    assert "并不孤单" in response
    assert CRISIS_SAFE_RESPONSE == response
