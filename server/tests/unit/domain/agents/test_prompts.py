"""Unit tests for the replier-style helpers in ``app.domain.agents.prompts``.

Covers the three pieces that unblock the "回信者风格链路" fix:

* ``normalize_style_key`` — maps any input (new keys, legacy keys, garbage) onto
  the canonical warm/pragmatic/calm vocabulary, defaulting to ``warm``.
"""

from __future__ import annotations

import pytest

from app.domain.agents.prompts import (
    DEFAULT_PERSONALITY_KEY,
    EMPATHY_STYLE_INSTRUCTIONS,
    PERSONALITY_NO_PRESSURE_BOTTOM_LINE,
    PERSONALITY_PRESETS,
    STYLE_KEY_ALIASES,
    build_personality_directive,
    is_personality_key,
    normalize_personality_key,
    normalize_style_key,
    personality_label,
    personality_preset_options,
)

# ── normalize_style_key ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        # 新 key 原样返回 (大小写不敏感)
        ("warm", "warm"),
        ("pragmatic", "pragmatic"),
        ("calm", "calm"),
        ("WARM", "warm"),
        ("Pragmatic", "pragmatic"),
        # 旧 key 经别名映射到新 key
        ("empathetic", "warm"),
        ("practical", "pragmatic"),
        ("philosophical", "calm"),
        ("humorous", "warm"),
        # 空值 / 未知值回落到默认 warm
        (None, "warm"),
        ("", "warm"),
        ("   ", "warm"),
        ("unknown-style", "warm"),
    ],
)
def test_normalize_style_key_maps_inputs(raw: str | None, expected: str) -> None:
    assert normalize_style_key(raw) == expected


def test_normalize_style_key_result_is_always_a_known_key() -> None:
    """归一化结果必须是 EMPATHY_STYLE_INSTRUCTIONS 里真实存在的 key。"""
    for legacy in STYLE_KEY_ALIASES:
        assert normalize_style_key(legacy) in EMPATHY_STYLE_INSTRUCTIONS
    assert normalize_style_key(None) in EMPATHY_STYLE_INSTRUCTIONS


# ── Personality presets (E1) ──────────────────────────────────────────


def test_presets_align_with_style_instructions() -> None:
    """每个人格 preset 都必须有对应的语气文案 (单一事实来源)。"""
    for key in PERSONALITY_PRESETS:
        assert key in EMPATHY_STYLE_INSTRUCTIONS
        preset = PERSONALITY_PRESETS[key]
        assert preset["label"]
        assert preset["min_chars"] < preset["max_chars"]


def test_normalize_personality_key_maps_inputs() -> None:
    assert normalize_personality_key("pragmatic") == "pragmatic"
    assert normalize_personality_key("practical") == "pragmatic"  # legacy alias
    assert normalize_personality_key("calm") == "calm"
    assert normalize_personality_key(None) == DEFAULT_PERSONALITY_KEY
    assert normalize_personality_key("nonsense") == DEFAULT_PERSONALITY_KEY


def test_is_personality_key_accepts_canonical_and_legacy() -> None:
    for key in PERSONALITY_PRESETS:
        assert is_personality_key(key)
    assert is_personality_key("practical")  # legacy alias still accepted
    assert not is_personality_key("nonsense")
    assert not is_personality_key(None)
    assert not is_personality_key("")


def test_personality_label_is_human_readable() -> None:
    assert personality_label("warm") == "温和陪伴"
    assert personality_label("pragmatic") == "理性教练"
    assert personality_label("calm") == "简洁记事"


def test_build_personality_directive_has_tone_length_and_bottom_line() -> None:
    out = build_personality_directive("calm")
    assert "【回信人格·简洁记事】" in out
    assert EMPATHY_STYLE_INSTRUCTIONS["calm"] in out
    assert "40-160" in out
    assert PERSONALITY_NO_PRESSURE_BOTTOM_LINE in out


def test_build_personality_directive_falls_back_on_unknown() -> None:
    out = build_personality_directive("nonsense")
    assert f"【回信人格·{PERSONALITY_PRESETS[DEFAULT_PERSONALITY_KEY]['label']}】" in out


def test_personality_preset_options_serialisable() -> None:
    options = personality_preset_options()
    assert {o["key"] for o in options} == set(PERSONALITY_PRESETS)
    for option in options:
        assert set(option) == {"key", "label", "min_chars", "max_chars"}
