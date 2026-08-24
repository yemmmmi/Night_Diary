"""MoodMonitor — the judgement layer of the V3.x user-mode system.

Determines the *current mode* (``daily`` / ``followup`` / ``introspection``)
for a scene-2 conversation, using three layered signals from spec
``docs/superpowers/specs/2026-08-18-v3x-mode-system-design.md`` sec.3:

* **A (20%)**  day/trend mood from ``card_service.get_mood_trends``
* **B (20%)**  plan tension from ``plan_service.get_today_tasks``
* **C (60%)**  in-turn emotion from ``EmotionEstimator.score``

The weights are *layered rule* semantics — this module implements them as
deterministic early-return rules (``decide_daily_baseline`` /
``should_drop_to_introspection``), not as a learnable weighted sum. The agent
never observes C or the thresholds directly: the *presentation* layer
(``ModePromptBuilder``, a later phase) consumes only the resulting mode.

Design splits:
- :class:`DailyModeStore` — thin read/upsert of ``daily_modes`` rows
  (single row per user per date, ``UniqueConstraint(user_id, date)``).
- pure decision functions — no DB/IO, fully unit-testable.
- :class:`MoodMonitor` — facade that fetches A/B signals, applies the rules,
  and persists outcomes without polluting the pure cores.

Mode codes are internal (``daily`` / ``followup`` / ``introspection``); the
user-visible names ``日常 / 跟进 / 内视`` are rendered by the presentation layer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.infrastructure.models.daily_mode import MODE, DailyModeRow

logger = logging.getLogger(__name__)

# Injected source signatures (defaults backed by the real services).
_MoodTrendSource = Callable[[Session, Any, int], list[dict[str, Any]]]
_TaskSource = Callable[..., list[Any]]


# ---------------------------------------------------------------------------
# DailyModeStore — thin persistence on the daily_modes table
# ---------------------------------------------------------------------------


class DailyModeStore:
    """Read / write one :class:`DailyModeRow` per user per date."""

    def get(
        self, db: Session, *, user_id: str, day: date
    ) -> DailyModeRow | None:
        return db.scalar(
            select(DailyModeRow).where(
                DailyModeRow.user_id == user_id, DailyModeRow.date == day
            )
        )

    def get_or_none_any(
        self, db: Session, *, user_id: str, day: date
    ) -> DailyModeRow | None:
        """Alias kept for readability at call sites."""
        return self.get(db, user_id=user_id, day=day)

    def upsert(
        self,
        db: Session,
        *,
        user_id: str,
        day: date,
        baseline_mode: str,
        auto_switched: bool,
        switch_count: int,
        mood_signals_json: str,
    ) -> DailyModeRow:
        row = self.get(db, user_id=user_id, day=day)
        if row is None:
            row = DailyModeRow(
                user_id=user_id,
                date=day,
                baseline_mode=baseline_mode,
                auto_switched=auto_switched,
                switch_count=switch_count,
                mood_signals_json=mood_signals_json,
            )
            db.add(row)
        else:
            row.baseline_mode = baseline_mode
            row.auto_switched = auto_switched
            row.switch_count = switch_count
            row.mood_signals_json = mood_signals_json
        db.flush()
        return row


# ---------------------------------------------------------------------------
# Pure decision functions (no DB, no IO)
# ---------------------------------------------------------------------------


@dataclass
class TrendSignal:
    """Aggregated criterion-A input."""

    has_data: bool = False
    composite_mood: float = 0.5
    samples: int = 0


def compute_trend_signal(
    mood_trends: list[dict[str, Any]],
    *,
    window_days: int,
    mood_low_threshold: float,
) -> TrendSignal:
    """Collapse daily mood trends into a single composite signal.

    Takes the last ``window_days`` buckets (ascending list from
    ``card_service.get_mood_trends``) and averages their ``avg_mood``.
    No bucketed rows => ``has_data=False`` so callers do not adjudicate
    purely on stale/empty history.
    """
    if not mood_trends:
        return TrendSignal(has_data=False, composite_mood=0.5, samples=0)
    recent = mood_trends[-window_days:]
    values = [float(r["avg_mood"]) for r in recent if r.get("avg_mood") is not None]
    if not values:
        return TrendSignal(has_data=False, composite_mood=0.5, samples=0)
    mean = sum(values) / len(values)
    return TrendSignal(
        has_data=True,
        composite_mood=mean,
        samples=len(values),
    )


def has_today_tension(today_tasks: list[Any]) -> bool:
    """Criterion-B: does the user have pending / due-today tasks?"""
    return bool(today_tasks)


def is_mood_low(trend: TrendSignal, *, mood_low_threshold: float) -> bool:
    """Criterion-A 'low' predicate: data-backed and below the threshold."""
    return trend.has_data and trend.composite_mood < mood_low_threshold


def decide_daily_baseline(
    *,
    yesterday_mode: str | None,
    trend: TrendSignal,
    tension: bool,
    mood_low_threshold: float,
    followup_needs_pending: bool = True,
) -> str:
    """Pick the day's baseline mode via layered early-return rules (B1).

    1. Continuation: yesterday was ``introspection`` and A is still weak
       (locked until the user recovers — do not re-push a fragile day).
    2. A clearly low -> ``introspection``.
    3. B has pending-today tension (and A is not low, guaranteed by step 2)
       -> ``followup``.
    4. Otherwise / no signal -> ``daily`` (never over-lean).
    """
    low = is_mood_low(trend, mood_low_threshold=mood_low_threshold)

    if yesterday_mode == MODE.INTROSPECTION and low:
        return MODE.INTROSPECTION
    if low:
        return MODE.INTROSPECTION
    if followup_needs_pending and tension:
        return MODE.FOLLOWUP
    return MODE.DAILY


def should_drop_to_introspection(
    turn_mood: float, *, live_threshold: float
) -> bool:
    """Criterion-C (B2): the current turn is poor enough to flip to a gentle mode.

    ``turn_mood`` is the 0..1 mood derived from ``EmotionEstimator.score``
    (``clamp(0.5 + score*0.5)``). Below ``live_threshold`` => introspect.
    """
    return turn_mood < live_threshold


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class MoodMonitor:
    """Compose signals and rules behind one entry point.

    Sources are injectable so unit tests can substitute stub mood/task/estimator
    hooks without a DB or LLM. Thresholds come from :class:`Settings` (a
    ``MODE_RULES``-style central bank) and are overridable for tests.
    """

    def __init__(
        self,
        *,
        store: DailyModeStore | None = None,
        estimator: Any = None,
        mood_trend_source: _MoodTrendSource | None = None,
        task_source: _TaskSource | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._store = store or DailyModeStore()
        self._settings = settings or get_settings()
        if estimator is None:
            from app.shared.emotion_estimator import get_emotion_estimator

            estimator = get_emotion_estimator()
        self._estimator = estimator
        self._mood_trend_source = mood_trend_source
        self._task_source = task_source

    # -- threshold helpers -----------------------------------------------------
    @property
    def mood_low_threshold(self) -> float:
        return self._settings.mode_mood_low_threshold

    @property
    def trend_window_days(self) -> int:
        return self._settings.mode_trend_window_days

    @property
    def live_threshold(self) -> float:
        return self._settings.mode_live_emotion_threshold

    @property
    def followup_needs_pending(self) -> bool:
        return self._settings.mode_followup_needs_pending_task

    # -- signal fetching ------------------------------------------------------
    def _mood_trends(self, db: Session, *, user_id: str) -> list[dict[str, Any]]:
        if self._mood_trend_source is not None:
            return self._mood_trend_source(db, user_id, self.trend_window_days)
        from app.services import card_service

        return card_service.get_mood_trends(
            db, user_id=user_id, days=self.trend_window_days
        )

    def _today_tasks(self, db: Session, *, user_id: str) -> list[Any]:
        if self._task_source is not None:
            return self._task_source(db, user_id=user_id)
        from app.services import plan_service

        return plan_service.get_today_tasks(db, user_id=user_id)

    def gather_signals(
        self, db: Session, *, user_id: str
    ) -> tuple[TrendSignal, bool]:
        """Return ``(trend_signal, has_tension)`` without mutating anything."""
        trend_rows = self._mood_trends(db, user_id=user_id)
        trend = compute_trend_signal(
            trend_rows,
            window_days=self.trend_window_days,
            mood_low_threshold=self.mood_low_threshold,
        )
        tension = (
            has_today_tension(self._today_tasks(db, user_id=user_id))
            if self.followup_needs_pending
            else False
        )
        return trend, tension

    # -- orchestration -------------------------------------------------------
    def resolve_or_create_baseline(
        self,
        db: Session,
        *,
        user_id: str,
        day: date,
        trend: TrendSignal | None = None,
        tension: bool | None = None,
    ) -> DailyModeRow:
        """Ensure a row exists for ``day`` and return its baseline.

        Computes the baseline from signals when no row is present *or* the sign
        escorts a manual override — the row's stored mode is otherwise authoritative.
        Injected ``trend``/``tension`` let tests drive the decision directly.
        """
        existing = self._store.get(db, user_id=user_id, day=day)
        if existing is not None:
            return existing

        if trend is None or tension is None:
            fetched_trend, fetched_tension = self.gather_signals(
                db, user_id=user_id
            )
            trend = trend if trend is not None else fetched_trend
            tension = tension if tension is not None else fetched_tension

        yesterday = self._store.get(
            db, user_id=user_id, day=day - timedelta(days=1)
        )
        baseline = decide_daily_baseline(
            yesterday_mode=yesterday.baseline_mode if yesterday else None,
            trend=trend,
            tension=tension,
            mood_low_threshold=self.mood_low_threshold,
            followup_needs_pending=self.followup_needs_pending,
        )
        return self._store.upsert(
            db,
            user_id=user_id,
            day=day,
            baseline_mode=baseline,
            auto_switched=False,
            switch_count=0,
            mood_signals_json=(
                f'{{"mood":{trend.composite_mood:.3f},'
                f'"samples":{trend.samples}}}'
            ),
        )

    def effective_mode(
        self, db: Session, *, user_id: str, day: date
    ) -> str:
        """Current authoritative mode for the day (manual/earlier override first)."""
        row = self._store.get(db, user_id=user_id, day=day)
        if row is not None:
            return row.baseline_mode
        # Fall back to a fresh baseline (creates the row).
        return self.resolve_or_create_baseline(
            db, user_id=user_id, day=day
        ).baseline_mode

    def in_turn_mood(self, content: str) -> float:
        """Derive 0..1 in-turn mood from the estimator (criterion C)."""
        score = float(self._estimator.score(content))
        return max(0.0, min(1.0, 0.5 + score * 0.5))

    def consumer_can_auto_switch(
        self, row: DailyModeRow | None, *, day: date
    ) -> bool:
        """Whether an auto-switch is still allowed today (max 1 auto switch).

        Spec: at most 2 automatic changes/day — the daily baseline counts as the
        first; only one further *in-session* auto switch (to introspection) is
        permitted, guarded by ``auto_switched``.
        """
        return row is None or not row.auto_switched

    def record_in_session_auto_switch(
        self,
        db: Session,
        *,
        user_id: str,
        day: date,
        to_mode: str,
        mood_signals_json: str,
    ) -> DailyModeRow:
        """Persist an in-session automatic switch (increments counters, sets
        ``auto_switched`` so the day's budget is consumed and intro_lock holds)."""
        row = self._store.get(db, user_id=user_id, day=day)
        prev_count = row.switch_count if row else 0
        return self._store.upsert(
            db,
            user_id=user_id,
            day=day,
            baseline_mode=to_mode,
            auto_switched=True,
            switch_count=prev_count + 1,
            mood_signals_json=mood_signals_json,
        )

    def record_manual_override(
        self, db: Session, *, user_id: str, day: date, mode: str
    ) -> DailyModeRow:
        """User-driven switch — always allowed, never consumes the auto budget."""
        row = self._store.get(db, user_id=user_id, day=day)
        prev_count = row.switch_count if row else 0
        return self._store.upsert(
            db,
            user_id=user_id,
            day=day,
            baseline_mode=mode,
            auto_switched=(row.auto_switched if row else False),
            switch_count=prev_count,
            mood_signals_json=(
                row.mood_signals_json if row else "{}"
            ),
        )
