"""Unit tests for ModePromptBuilder (V3.x mode presentation layer).

Validates the middleware emits the mode tone + plan-state blocks, obeys the
global no-pressure bottom line, and degrades gracefully when no mode/plan subsystem
is available. Uses a stub :class:`DailyModeStore` (plus an unbound real
:class:`Session` placeholder so the ``isinstance(Session)`` guard passes) — no DB
vendor or LLM is required.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.infrastructure.models.daily_mode import MODE
from app.shared.middleware import MiddlewareContext, ModePromptBuilder


class _FakeStore:
    """Exposes the ``get`` contract ModePromptBuilder relies on."""

    def __init__(self, mode: str | None) -> None:
        self._mode = mode

    def get(self, db, *, user_id, day):
        class _Row:
            baseline_mode = self._mode

        return _Row() if self._mode else None


def _builder(store=None):
    return ModePromptBuilder(store=store or _FakeStore(MODE.DAILY))


def _ctx(user_id="u1", *, with_db=True):
    extra = {"db": Session()} if with_db else {}
    return MiddlewareContext(
        scenario="conversation", user_id=user_id, content="你好", extra=extra
    )


def test_daily_injects_plan_state_and_tone():
    out = _builder(_FakeStore(MODE.DAILY)).on_system_prompt("BASE", _ctx())
    assert "BASE" in out
    assert "【当前计划与状态】" in out
    assert "【模式语气·daily】" in out


def test_introspection_uses_tone_and_weakens_plan():
    out = _builder(_FakeStore(MODE.INTROSPECTION)).on_system_prompt("BASE", _ctx())
    assert "【模式语气·introspection】" in out
    # Introspection: do not surface today's todos.
    assert "今日待办" not in out
    assert "放下计划" in out or "暂缓" in out


def test_followup_uses_followup_tone():
    out = _builder(_FakeStore(MODE.FOLLOWUP)).on_system_prompt("BASE", _ctx())
    assert "【模式语气·followup】" in out


def test_no_mode_lookup_falls_back_to_daily_tone():
    # No store injected and no db in extra -> effective_mode degrades; the daily
    # tone must still be present and no exception escapes.
    b = ModePromptBuilder()  # real store, but no db context
    out = b.on_system_prompt("BASE", _ctx(with_db=False))
    assert "BASE" in out
    assert "【模式语气·daily】" in out


def test_global_bottom_line_always_present():
    for mode in (MODE.DAILY, MODE.FOLLOWUP, MODE.INTROSPECTION):
        out = _builder(_FakeStore(mode)).on_system_prompt("BASE", _ctx())
        assert "不要用『必须/赶紧/逾期警告』" in out
