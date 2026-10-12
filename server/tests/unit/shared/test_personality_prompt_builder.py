"""Unit tests for PersonalityPromptBuilder (E1 回信人格 preset middleware).

Validates the middleware injects the 【回信人格】 directive keyed off
``ctx.extra["personality"]``, is orthogonal to the mode, obeys the global
no-pressure bottom line, and degrades to the default preset on missing/unknown
input.
"""

from __future__ import annotations

from app.domain.agents.prompts import PERSONALITY_NO_PRESSURE_BOTTOM_LINE
from app.shared.middleware import MiddlewareContext, PersonalityPromptBuilder


def _ctx(personality: str | None = None) -> MiddlewareContext:
    extra = {} if personality is None else {"personality": personality}
    return MiddlewareContext(
        scenario="conversation", user_id="u1", content="你好", extra=extra
    )


def test_injects_chosen_preset_block() -> None:
    out = PersonalityPromptBuilder().on_system_prompt("BASE", _ctx("pragmatic"))
    assert "BASE" in out
    assert "【回信人格·理性教练】" in out


def test_missing_key_falls_back_to_default() -> None:
    out = PersonalityPromptBuilder().on_system_prompt("BASE", _ctx())
    assert "【回信人格·温和陪伴】" in out


def test_unknown_key_falls_back_to_default() -> None:
    out = PersonalityPromptBuilder().on_system_prompt("BASE", _ctx("nonsense"))
    assert "【回信人格·温和陪伴】" in out


def test_bottom_line_always_present() -> None:
    for key in ("warm", "pragmatic", "calm", "", "nonsense"):
        out = PersonalityPromptBuilder().on_system_prompt("BASE", _ctx(key))
        assert PERSONALITY_NO_PRESSURE_BOTTOM_LINE in out


def test_non_string_personality_is_ignored() -> None:
    ctx = MiddlewareContext(
        scenario="conversation", user_id="u1", content="你好", extra={"personality": 42}
    )
    out = PersonalityPromptBuilder().on_system_prompt("BASE", ctx)
    assert "【回信人格·温和陪伴】" in out