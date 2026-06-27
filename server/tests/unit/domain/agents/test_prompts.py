"""Unit tests for the replier-style helpers in ``app.domain.agents.prompts``.

Covers the three pieces that unblock the "回信者风格链路" fix:

* ``normalize_style_key`` — maps any input (new keys, legacy keys, garbage) onto
  the canonical warm/pragmatic/calm vocabulary, defaulting to ``warm``.
* ``build_style_fragment`` — turns the frontend ``replier_preset`` /
  ``replier_persona`` payload into the ``style_fragment`` text injected into the
  empathy/insight prompts (persona wins over preset; both empty → ``None``).
"""

from __future__ import annotations

import pytest

from app.domain.agents.prompts import (
    EMPATHY_STYLE_INSTRUCTIONS,
    STYLE_KEY_ALIASES,
    build_style_fragment,
    normalize_style_key,
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


# ── build_style_fragment ──────────────────────────────────────────────


def test_persona_takes_priority_over_preset() -> None:
    fragment = build_style_fragment("warm", "你是一个诗人，用短句回信")
    assert fragment is not None
    assert fragment.startswith("## 回信者人设（用户指定，优先级最高）")
    assert "你是一个诗人，用短句回信" in fragment
    # preset 文案不应混入 persona fragment
    assert "## 回信风格" not in fragment


def test_preset_only_maps_to_style_text() -> None:
    fragment = build_style_fragment("pragmatic", None)
    assert fragment is not None
    assert fragment.startswith("## 回信风格（用户指定，优先级最高）")
    # 内容是 normalize 后的 pragmatic 文案
    assert EMPATHY_STYLE_INSTRUCTIONS["pragmatic"] in fragment


def test_legacy_preset_key_is_normalized() -> None:
    """前端若传旧 key (如 practical), 应映射到 pragmatic 文案。"""
    fragment = build_style_fragment("practical", None)
    assert fragment is not None
    assert EMPATHY_STYLE_INSTRUCTIONS["pragmatic"] in fragment


def test_empty_persona_falls_back_to_preset() -> None:
    """persona 为空白时退回 preset。"""
    fragment = build_style_fragment("calm", "   ")
    assert fragment is not None
    assert fragment.startswith("## 回信风格（用户指定，优先级最高）")
    assert EMPATHY_STYLE_INSTRUCTIONS["calm"] in fragment


def test_both_empty_returns_none() -> None:
    """preset/persona 都缺省 → None, 由 agent 回落到 profile 偏好风格。"""
    assert build_style_fragment(None, None) is None
    assert build_style_fragment("", "") is None
    assert build_style_fragment(None, "") is None
