"""Unit tests for the MoodMonitor judgement layer (V3.x mode system).

Covers the pure decision functions, the ``daily_modes`` store, and the
``MoodMonitor`` facade using injected signals/sources so no DB-vendor or LLM is
needed. Thresholds are pinned via an explicit :class:`Settings` object.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.database import Base
from app.infrastructure.models.daily_mode import MODE, DailyModeRow
from app.services import plan_service
from app.services.ai.mood_monitor import (
    DailyModeStore,
    MoodMonitor,
    TrendSignal,
    compute_trend_signal,
    decide_daily_baseline,
    has_today_tension,
    is_mood_low,
    should_drop_to_introspection,
)

DAY = __import__("datetime").date(2026, 8, 18)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def _settings(**kw) -> Settings:
    defaults = dict(
        mode_mood_low_threshold=0.40,
        mode_live_emotion_threshold=0.35,
        mode_trend_window_days=7,
        mode_followup_needs_pending_task=True,
        mode_enable_live_emotion_enhancement=False,
    )
    defaults.update(kw)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# Pure decision functions
# ---------------------------------------------------------------------------


def test_compute_trend_signal_empty_is_no_data():
    sig = compute_trend_signal([], window_days=7, mood_low_threshold=0.4)
    assert sig.has_data is False
    assert sig.samples == 0


def test_compute_trend_signal_averages_last_window():
    rows = [
        {"date": "2026-08-11", "avg_mood": 0.2, "card_count": 1},
        {"date": "2026-08-12", "avg_mood": 0.4, "card_count": 1},
        {"date": "2026-08-13", "avg_mood": 0.6, "card_count": 1},
    ]
    sig = compute_trend_signal(rows, window_days=7, mood_low_threshold=0.4)
    assert sig.has_data is True
    assert sig.composite_mood == pytest.approx(0.4, abs=1e-6)
    assert sig.samples == 3


def test_is_mood_low_only_when_data_backed():
    assert is_mood_low(TrendSignal(True, 0.3, 3), mood_low_threshold=0.4) is True
    assert is_mood_low(TrendSignal(True, 0.6, 3), mood_low_threshold=0.4) is False
    assert is_mood_low(TrendSignal(False), mood_low_threshold=0.4) is False


def test_decide_low_mood_wins_over_all():
    assert (
        decide_daily_baseline(
            yesterday_mode=None,
            trend=TrendSignal(True, 0.3, 3),
            tension=True,
            mood_low_threshold=0.4,
        )
        == MODE.INTROSPECTION
    )


def test_decide_followup_when_mood_ok_and_tension():
    assert (
        decide_daily_baseline(
            yesterday_mode=None,
            trend=TrendSignal(True, 0.6, 3),
            tension=True,
            mood_low_threshold=0.4,
        )
        == MODE.FOLLOWUP
    )


def test_decide_continuation_when_yesterday_introspection_still_low():
    assert (
        decide_daily_baseline(
            yesterday_mode=MODE.INTROSPECTION,
            trend=TrendSignal(True, 0.3, 3),
            tension=True,
            mood_low_threshold=0.4,
        )
        == MODE.INTROSPECTION
    )


def test_decide_leaves_introspection_when_recovered():
    assert (
        decide_daily_baseline(
            yesterday_mode=MODE.INTROSPECTION,
            trend=TrendSignal(True, 0.6, 3),
            tension=False,
            mood_low_threshold=0.4,
        )
        == MODE.DAILY
    )


def test_decide_defaults_to_daily_without_signals():
    assert (
        decide_daily_baseline(
            yesterday_mode=None,
            trend=TrendSignal(False),
            tension=False,
            mood_low_threshold=0.4,
        )
        == MODE.DAILY
    )


def test_should_drop_to_introspection_threshold():
    assert should_drop_to_introspection(0.2, live_threshold=0.35) is True
    assert should_drop_to_introspection(0.6, live_threshold=0.35) is False


def test_has_today_tension():
    assert has_today_tension(["task"]) is True
    assert has_today_tension([]) is False


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


def test_store_upsert_single_row_per_day(db):
    store = DailyModeStore()
    r1 = store.upsert(
        db, user_id="u1", day=DAY, baseline_mode="daily",
        auto_switched=False, switch_count=0, mood_signals_json="{}",
    )
    r2 = store.upsert(
        db, user_id="u1", day=DAY, baseline_mode="followup",
        auto_switched=True, switch_count=1, mood_signals_json="{}",
    )
    assert r1.id == r2.id  # same row (upsert)
    assert store.get(db, user_id="u1", day=DAY).baseline_mode == "followup"


# ---------------------------------------------------------------------------
# MoodMonitor facade (injected signals + sources)
# ---------------------------------------------------------------------------


def _monitor(settings_kw=None, trend_source=None, task_source=None, estimator=None):
    return MoodMonitor(
        settings=_settings(**(settings_kw or {})),
        mood_trend_source=trend_source,
        task_source=task_source,
        estimator=estimator,
    )


class _FakeEstimator:
    def score(self, text: str) -> float:
        return {"好累": -0.6, "开心": 0.7}.get(text, 0.0)


def test_resolve_baseline_low_mood_marks_introspection(db):
    mon = _monitor(
        trend_source=lambda db_, uid, days: [
            {"date": "2026-08-%02d" % d, "avg_mood": 0.25, "card_count": 1}
            for d in range(12, 19)
        ],
        task_source=lambda db_, user_id=...: [],
    )
    row = mon.resolve_or_create_baseline(db, user_id="u1", day=DAY)
    assert row.baseline_mode == MODE.INTROSPECTION


def test_resolve_baseline_followup_when_tension_and_mood_ok(db):
    # Stub sources: mood above low threshold + one today task.
    def trend(db_, uid, days):
        return [{"date": "2026-08-%02d" % d, "avg_mood": 0.6, "card_count": 1}
               for d in range(12, 19)]

    def tasks(db_, user_id="x"):
        return [{"title": "写报告", "status": "pending"}]

    # mood_trend_source signature: (db, user_id, int)
    mon = MoodMonitor(
        settings=_settings(),
        mood_trend_source=trend,
        task_source=lambda db_, **kw: tasks(db_),
    )
    row = mon.resolve_or_create_baseline(db, user_id="u1", day=DAY)
    assert row.baseline_mode == MODE.FOLLOWUP


def test_manual_override_does_not_consume_auto_budget(db):
    mon = _monitor()
    mon.resolve_or_create_baseline(
        db, user_id="u1", day=DAY,
        trend=TrendSignal(True, 0.6, 3), tension=True,
    )
    row = mon.record_manual_override(db, user_id="u1", day=DAY, mode=MODE.INTROSPECTION)
    assert row.baseline_mode == MODE.INTROSPECTION
    assert row.switch_count == 0
    assert row.auto_switched is False


def test_in_session_auto_switch_consumes_budget(db):
    mon = _monitor()
    mon.resolve_or_create_baseline(
        db, user_id="u1", day=DAY,
        trend=TrendSignal(True, 0.6, 3), tension=False,
    )
    row = mon.record_in_session_auto_switch(
        db, user_id="u1", day=DAY, to_mode=MODE.INTROSPECTION, mood_signals_json="{}"
    )
    assert row.auto_switched is True
    assert row.switch_count == 1
    # Budget consumed -> no further auto switch.
    assert mon.consumer_can_auto_switch(row, day=DAY) is False


def test_in_turn_mood_from_estimator():
    mon = _monitor(estimator=_FakeEstimator())
    assert mon.in_turn_mood("好累") <= 0.2  # 0.5 + (-0.6)*0.5 = 0.2
    assert mon.in_turn_mood("开心") > 0.8


def test_effective_mode_creates_then_reads(db):
    mon = _monitor(
        trend_source=lambda db_, uid, days: [],
        task_source=lambda db_, **kw: [],
    )
    m1 = mon.effective_mode(db, user_id="u1", day=DAY)
    assert m1 == MODE.DAILY  # no signals -> daily
    assert mon.effective_mode(db, user_id="u1", day=DAY) == MODE.DAILY


def test_real_plan_service_tension_db(db):
    """End-to-end within the DB: a due-today pending task -> followup tension."""
    mon = _monitor(
        trend_source=lambda db_, uid, days: [
            {"date": "2026-08-%02d" % d, "avg_mood": 0.6, "card_count": 1}
            for d in range(12, 19)
        ],
    )
    # Task uses real plan_service so B feeds the monitor through the default path.
    today = DAY.__class__.today()
    db.add(DailyModeRow(user_id="u1", date=today, baseline_mode="daily"))
    db.flush()
    plan_service.create_task(
        db, user_id="u1", plan_id=None, title="今日任务",
        note=None, due_date=today.isoformat(), source="manual",
        created_from_conversation_id=None,
    )
    tasks = plan_service.get_today_tasks(db, user_id="u1")
    assert has_today_tension(tasks) is True
    assert mon.followup_needs_pending is True
