"""Feedback submission with async Thompson Sampling update."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

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
    user_id: str,
    analysis_id: int,
    feedback_type: str,
    reason: str | None = None,
    response_style: str = "empathetic",
    thompson: ThompsonSampling | None = None,
) -> FeedbackRow:
    if feedback_type not in ("positive", "negative"):
        raise ValidationError("feedback_type 必须是 positive 或 negative")

    # Verify the analysis belongs to the current user via diary ownership.
    # AnalysisRow has no user_id column, so get_analysis_by_id uses a JOIN
    # on diary_entries to enforce isolation.
    analysis = get_analysis_by_id(db, analysis_id, user_id=user_id)
    row = FeedbackRow(
        analysis_id=analysis.id,
        diary_id=analysis.diary_id,
        response_style=response_style,
        feedback_type=feedback_type,
        reason=reason,
        source="explicit",
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if thompson is not None:
        _schedule_thompson_update(
            thompson,
            user_id=user_id,
            style=response_style,
            is_positive=feedback_type == "positive",
        )

    return row


def submit_conversation_feedback(
    db: Session,
    *,
    user_id: str,
    conversation_id: str,
    feedback_type: str,
    reason: str | None = None,
    response_style: str = "empathetic",
    thompson: ThompsonSampling | None = None,
) -> FeedbackRow:
    """Submit feedback for a conversation reply (scene 2).

    Unlike scene-1 feedback, there is no analysis_id or diary_id — only
    the conversation_id links the feedback to the AI response.
    """
    if feedback_type not in ("positive", "negative"):
        raise ValidationError("feedback_type 必须是 positive 或 negative")
    if not conversation_id or not conversation_id.strip():
        raise ValidationError("conversation_id 不能为空")

    # Verify the conversation belongs to the current user
    from app.infrastructure.models.conversation import ConversationRow

    conv = (
        db.query(ConversationRow)
        .filter(
            ConversationRow.id == conversation_id,
            ConversationRow.user_id == user_id,
        )
        .first()
    )
    if conv is None:
        raise ValidationError("对话不存在或无权访问")

    row = FeedbackRow(
        conversation_id=conversation_id,
        response_style=response_style,
        feedback_type=feedback_type,
        reason=reason,
        source="explicit",
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if thompson is not None:
        _schedule_thompson_update(
            thompson,
            user_id=user_id,
            style=response_style,
            is_positive=feedback_type == "positive",
        )

    return row


def build_thompson_sampler(store: StylePreferenceStore | None) -> ThompsonSampling:
    return ThompsonSampling(store=store)
