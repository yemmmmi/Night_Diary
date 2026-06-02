"""Unit tests for PromptTuner."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.feedback.prompt_tuner import (
    PromptTuner,
    ResponseLength,
    ResponseLengthContext,
    build_dynamic_prompt_for_agent,
    get_default_preference,
    infer_directness,
    infer_response_length,
)
from app.domain.feedback.thompson_sampling import ThompsonSampling
from app.domain.feedback.types import (
    DEFAULT_DIRECTNESS,
    DEFAULT_RESPONSE_LENGTH,
    DEFAULT_STYLE,
    STYLES,
)


def test_default_preference_values() -> None:
    pref = get_default_preference()
    assert pref.response_length == DEFAULT_RESPONSE_LENGTH
    assert pref.style == DEFAULT_STYLE
    assert pref.directness == DEFAULT_DIRECTNESS


def test_new_user_gets_default(memory_style_store) -> None:
    tuner = PromptTuner(store=memory_style_store)
    pref = tuner.get_user_preference("missing-user")
    assert pref == get_default_preference()


def test_prompt_tuner_uses_thompson_sampling(memory_style_store) -> None:
    memory_style_store.ensure_preferences("u1", list(STYLES))
    thompson = MagicMock(spec=ThompsonSampling)
    thompson.sample_style.return_value = "practical"
    tuner = PromptTuner(store=memory_style_store, thompson=thompson)

    pref = tuner.get_user_preference("u1")
    thompson.sample_style.assert_called_once_with("u1")
    assert pref.style == "practical"


def test_high_alpha_style_reflected_in_prompt(memory_style_store) -> None:
    memory_style_store.ensure_preferences("u1", list(STYLES))
    memory_style_store.update_preference("u1", "practical", alpha=50.0, beta=1.0)
    for style in STYLES:
        if style != "practical":
            memory_style_store.update_preference("u1", style, alpha=1.0, beta=50.0)

    tuner = PromptTuner(store=memory_style_store)
    practical_count = 0
    for _ in range(20):
        prompt = tuner.build_dynamic_prompt("u1", "empathy")
        if "务实" in prompt or "简洁有力" in prompt:
            practical_count += 1
    assert practical_count > 15


def test_infer_directness_practical_is_high(memory_style_store) -> None:
    memory_style_store.ensure_preferences("u1", list(STYLES))
    memory_style_store.update_preference("u1", "practical", alpha=10.0, beta=1.0)
    memory_style_store.update_preference("u1", "empathetic", alpha=1.0, beta=10.0)
    prefs = memory_style_store.get_preferences("u1")
    assert infer_directness(prefs) > 0.5


def test_infer_response_length_uses_context() -> None:
    assert (
        infer_response_length(
            context=ResponseLengthContext(diary_word_count=500),
        )
        == ResponseLength.LONG
    )
    assert (
        infer_response_length(
            context=ResponseLengthContext(diary_word_count=40),
        )
        == ResponseLength.SHORT
    )
    assert (
        infer_response_length(
            context=ResponseLengthContext(hour=23, emotion_intensity=0.9),
        )
        == ResponseLength.SHORT
    )


def test_build_dynamic_prompt_contains_sections(memory_style_store) -> None:
    tuner = PromptTuner(store=memory_style_store)
    prompt = tuner.build_dynamic_prompt("u1", "empathy")
    assert "用户偏好适配指令" in prompt
    assert "回应风格" in prompt
    assert "回应长度" in prompt
    assert "表达直接度" in prompt


def test_build_dynamic_prompt_for_agent_helper(memory_style_store) -> None:
    prompt = build_dynamic_prompt_for_agent(memory_style_store, "u1", "insight")
    assert "用户偏好适配指令" in prompt


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.2, "low"),
        (0.5, "medium"),
        (0.8, "high"),
    ],
)
def test_directness_to_level(value: float, expected: str) -> None:
    assert PromptTuner._directness_to_level(value) == expected
