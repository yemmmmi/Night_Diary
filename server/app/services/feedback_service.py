"""Feedback submission with async Thompson Sampling update."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domain.feedback.thompson_sampling import ThompsonSampling
from app.domain.feedback.types import StylePreferenceStore
from app.infrastructure.models.feedback_record import FeedbackRow
from app.services.analysis_service import get_analysis_by_id
from app.shared.errors import ValidationError

logger = logging.getLogger(__name__)


def _schedule_thompson_update(
    thompson: ThompsonSampling,
    *,
    user_id: str,
    style: str,
    is_positive: bool,
) -> None:
    """Fire-and-forget reward update so the API response is not blocked."""

    def _run() -> None:
        try:
            thompson.update_reward(user_id, style, is_positive=is_positive)
        except Exception as exc:
            logger.warning("Thompson Sampling async update failed: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


def submit_feedback(
    db: Session,
    *,
    analysis_id: int,
    feedback_type: str,
    reason: str | None = None,
    response_style: str = "empathetic",
    thompson: ThompsonSampling | None = None,
) -> FeedbackRow:
    if feedback_type not in ("positive", "negative"):
        raise ValidationError("feedback_type 必须是 positive 或 negative")

    analysis = get_analysis_by_id(db, analysis_id)
    row = FeedbackRow(
        analysis_id=analysis.id,
        diary_id=analysis.diary_id,
        response_style=response_style,
        feedback_type=feedback_type,
        reason=reason,
        source="explicit",
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if thompson is not None:
        _schedule_thompson_update(
            thompson,
            user_id="default",
            style=response_style,
            is_positive=feedback_type == "positive",
        )

    return row


def build_thompson_sampler(store: StylePreferenceStore | None) -> ThompsonSampling:
    return ThompsonSampling(store=store)
