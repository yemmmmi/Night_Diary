"""Sync MoodMonitor's daily modes into the profile's short_term_state (P1-A).

The daily-mode system previously flowed one way: profile/emotion signals fed
``daily_modes``, but the multi-day trend never flowed back — agents saw
today's mode and nothing else. This module is the return path: at chat time
the recent ``daily_modes`` window is rolled into
``UserProfile.short_term_state`` (recent_modes + composite_mood), which then
renders into the frozen memory block and the insight agent's profile context.

The write is guarded: at most one profile write per user per day (the state's
``updated_date`` is the churn guard), best-effort, never raises.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.memory.types import ShortTermState
from app.services.ai.mood_monitor import (
    SHORT_TERM_WINDOW_DAYS,
    compute_short_term_state,
)

logger = logging.getLogger(__name__)


def refresh_short_term_state(
    db: Session,
    container: object,
    *,
    user_id: str,
    day: date | None = None,
) -> ShortTermState | None:
    """Roll recent daily_modes into the profile's short_term_state.

    Returns the (possibly cached) state, or ``None`` when there is nothing to
    sync (no mode rows yet, or no long-term store). Best-effort: failures are
    logged and swallowed — the mode system must never break the chat path.
    """
    long_term = getattr(container, "long_term_memory", None)
    if long_term is None:
        return None

    try:
        from app.infrastructure.models.daily_mode import DailyModeRow

        today = day if day is not None else date.today()
        window_start = today - timedelta(days=SHORT_TERM_WINDOW_DAYS - 1)
        rows = list(
            db.scalars(
                select(DailyModeRow)
                .where(
                    DailyModeRow.user_id == user_id,
                    DailyModeRow.date >= window_start,
                    DailyModeRow.date <= today,
                )
                .order_by(DailyModeRow.date.asc())
            )
        )
        if not rows:
            return None

        state = compute_short_term_state(rows, today=today)

        profile = long_term.get_profile(user_id)
        if profile.short_term_state == state:
            return state  # already synced today (daily churn guard)

        profile.short_term_state = state
        long_term.update_profile(user_id, profile, source="mood_sync")
        logger.info(
            "Short-term state synced for user_id=%s: modes=%s mood=%.2f samples=%d",
            user_id,
            state.recent_modes,
            state.composite_mood,
            state.samples,
        )
        return state
    except Exception as exc:
        logger.warning("Short-term state sync failed (best-effort): %s", exc)
        return None
