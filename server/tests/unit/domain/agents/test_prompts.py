"""Unit tests for the replier-style helpers in ``app.domain.agents.prompts``.

Covers the three pieces that unblock the "回信者风格链路" fix:

* ``normalize_style_key`` — maps any input (new keys, legacy keys, garbage) onto
  the canonical warm/pragmatic/calm vocabulary, defaulting to ``warm``.
"""

from __future__ import annotations

import pytest

from app.domain.agents.prompts import (
    EMPATHY_STYLE_INSTRUCTIONS,
    STYLE_KEY_ALIASES,
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
