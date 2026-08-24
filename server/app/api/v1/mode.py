"""User-mode API routes (V3.x mode system).

Exposes:

* ``GET /api/v1/mode`` — current mode for the user today (used by the
  frontend to initialise the mode badge).
* ``POST /api/v1/mode`` — user-driven manual override (immediate, and never
  consumes the day's automatic-switch budget; see MoodMonitor).

Mode codes are internal (``daily`` / ``followup`` / ``introspection``);
``display_name`` maps to the user-visible names 日常 / 跟进 / 内视.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, DbDep
from app.infrastructure.models.daily_mode import MODE
from app.services.ai.mood_monitor import MoodMonitor

router = APIRouter(prefix="/mode", tags=["mode"])

#: Internal code -> user-visible name (also mirrored by the frontend's own map).
MODE_DISPLAY_NAMES: dict[str, str] = {
    MODE.DAILY: "日常",
    MODE.FOLLOWUP: "跟进",
    MODE.INTROSPECTION: "内视",
}


class ModeOverrideRequest(BaseModel):
    mode: str


@router.get("")
def get_current_mode(db: DbDep, user: CurrentUserDep) -> dict[str, Any]:
    """Return the user's current mode for today."""
    monitor = MoodMonitor()
    mode = monitor.effective_mode(db, user_id=str(user.id), day=date.today())
    return {
        "mode": mode,
        "display_name": MODE_DISPLAY_NAMES.get(mode, MODE_DISPLAY_NAMES[MODE.DAILY]),
    }


@router.post("")
def override_mode(
    db: DbDep, user: CurrentUserDep, body: ModeOverrideRequest
) -> dict[str, Any]:
    """Manually set today's mode (user-driven override)."""
    target = body.mode
    if target not in MODE_DISPLAY_NAMES:
        raise HTTPException(status_code=400, detail=f"invalid mode: {target}")
    monitor = MoodMonitor()
    monitor.record_manual_override(
        db, user_id=str(user.id), day=date.today(), mode=target
    )
    db.commit()
    return {
        "mode": target,
        "display_name": MODE_DISPLAY_NAMES[target],
    }
