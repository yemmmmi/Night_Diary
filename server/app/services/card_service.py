"""Memory card CRUD with Card→EpisodicEntry bridge and Card→Diary expansion.

Cards are lightweight structured memory atoms. They flow into the
existing three-layer memory system:
  MemoryCard → card_to_episodic() → EpisodicEntry → episodic_memories
                                            → promote → UserProfile
  MemoryCard → expand_to_diary()   → DiaryEntry   → analysis_service
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.domain.memory.types import EpisodicEntry
from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.models.memory_card import MemoryCardRow
from app.shared.errors import NotFoundError, ValidationError

if TYPE_CHECKING:
    from app.domain.memory.episodic import EpisodicMemory

logger = logging.getLogger(__name__)

RECENT_CARDS_DAYS = 30
RECENT_CARDS_LIMIT = 50


# ── helpers ────────────────────────────────────────────────────────────


def _tags_to_json(tags: list[str]) -> str | None:
    return json.dumps(tags, ensure_ascii=False) if tags else None


def _json_to_tags(tags_json: str | None) -> list[str]:
    if not tags_json:
        return []
    try:
        return json.loads(tags_json)
    except (json.JSONDecodeError, TypeError):
        return []


def row_to_dict(row: MemoryCardRow) -> dict:
    return {
        "card_id": row.card_id,
        "emotion": row.emotion,
        "event_summary": row.event_summary,
        "mood_score": row.mood_score,
        "tags": _json_to_tags(row.tags_json),
        "importance": row.importance,
        "card_type": row.card_type,
        "diary_id": row.diary_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


# ── CRUD ────────────────────────────────────────────────────────────────


def create_card(
    db: Session,
    *,
    emotion: str,
    event_summary: str | None = None,
    mood_score: float = 0.5,
    tags: list[str] | None = None,
    importance: float = 0.5,
    card_type: str = "standard",
) -> MemoryCardRow:
    if not emotion.strip():
        raise ValidationError("情绪标签不能为空")

    row = MemoryCardRow(
        card_id=uuid.uuid4().hex,
        emotion=emotion.strip(),
        event_summary=event_summary.strip() if event_summary else None,
        mood_score=max(0.0, min(1.0, mood_score)),
        tags_json=_tags_to_json(tags or []),
        importance=max(0.0, min(1.0, importance)),
        card_type=card_type,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "Card created: card_id=%s emotion=%s type=%s",
        row.card_id,
        row.emotion,
        row.card_type,
    )
    return row


def get_card(db: Session, card_id: str) -> MemoryCardRow:
    row = db.query(MemoryCardRow).filter(MemoryCardRow.card_id == card_id).first()
    if row is None:
        raise NotFoundError(resource="memory_card", resource_id=card_id)
    return row


def list_cards(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
    emotion: str | None = None,
    card_type: str | None = None,
    has_diary: bool | None = None,
) -> list[MemoryCardRow]:
    q = db.query(MemoryCardRow)

    if emotion:
        q = q.filter(MemoryCardRow.emotion == emotion)
    if card_type:
        q = q.filter(MemoryCardRow.card_type == card_type)
    if has_diary is True:
        q = q.filter(MemoryCardRow.diary_id.isnot(None))
    elif has_diary is False:
        q = q.filter(MemoryCardRow.diary_id.is_(None))

    return (
        q.order_by(desc(MemoryCardRow.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_card(
    db: Session,
    card_id: str,
    *,
    emotion: str | None = None,
    event_summary: str | None = None,
    mood_score: float | None = None,
    tags: list[str] | None = None,
    importance: float | None = None,
) -> MemoryCardRow:
    row = get_card(db, card_id)

    if emotion is not None:
        if not emotion.strip():
            raise ValidationError("情绪标签不能为空")
        row.emotion = emotion.strip()

    if event_summary is not None:
        row.event_summary = event_summary.strip() if event_summary else None

    if mood_score is not None:
        row.mood_score = max(0.0, min(1.0, mood_score))

    if tags is not None:
        row.tags_json = _tags_to_json(tags)

    if importance is not None:
        row.importance = max(0.0, min(1.0, importance))

    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    logger.info("Card updated: card_id=%s", card_id)
    return row


def delete_card(db: Session, card_id: str) -> None:
    row = get_card(db, card_id)
    db.delete(row)
    db.commit()
    logger.info("Card deleted: card_id=%s", card_id)


# ── Card → Episodic bridge ─────────────────────────────────────────────


def card_to_episodic(row: MemoryCardRow) -> EpisodicEntry:
    """Convert a MemoryCardRow to an EpisodicEntry for the memory pipeline."""
    event = row.event_summary or f"（{row.emotion}情绪记录）"
    return EpisodicEntry(
        event=event,
        emotion=row.emotion,
        ai_suggestion="",
        user_feedback="none",
        timestamp=row.created_at.timestamp(),
        diary_ids=[str(row.diary_id)] if row.diary_id else [],
        importance=row.importance,
        entry_id="",
    )


def sync_card_to_episodic(
    row: MemoryCardRow,
    episodic: EpisodicMemory | None,
) -> bool:
    """Push a card into the episodic memory pipeline.

    Returns ``True`` if the entry was stored (importance > threshold).
    """
    if episodic is None:
        return False

    entry = card_to_episodic(row)
    stored = episodic.store(entry)
    if stored:
        logger.debug(
            "Card→Episodic stored: card_id=%s event=%s importance=%.2f",
            row.card_id,
            entry.event,
            entry.importance,
        )
    else:
        logger.debug(
            "Card→Episodic skipped (below threshold): card_id=%s importance=%.2f",
            row.card_id,
            entry.importance,
        )
    return stored


def sync_recent_cards_to_episodic(
    db: Session,
    episodic: EpisodicMemory | None,
) -> int:
    """Batch-sync recent un-pushed cards into episodic memory.

    Returns count of successfully stored entries.
    """
    if episodic is None:
        return 0

    recent = list_cards(db, skip=0, limit=RECENT_CARDS_LIMIT)
    stored = 0
    for row in recent:
        if sync_card_to_episodic(row, episodic):
            stored += 1
    return stored


# ── Card → Diary expansion ─────────────────────────────────────────────


def expand_to_diary(
    db: Session,
    card_id: str,
    *,
    entry_date: date | None = None,
) -> DiaryEntryRow:
    """Expand a memory card into a full diary entry.

    The card's emotion, event_summary and tags are used as seed content.
    The card's ``diary_id`` is updated to link back to the new diary.
    """
    card = get_card(db, card_id)

    if card.diary_id is not None:
        raise ValidationError(f"卡片 {card_id} 已经展开为日记 #{card.diary_id}")

    tags = _json_to_tags(card.tags_json)
    lines = [
        f"💭 心情：{card.emotion}",
    ]
    if card.event_summary:
        lines.append(f"📌 事件：{card.event_summary}")
    if tags:
        lines.append(f"🏷️ 标签：{'、'.join('#' + t for t in tags)}")
    lines.append("")
    lines.append("（从记忆卡片展开，继续写下更多细节……）")

    diary_entry = DiaryEntryRow(
        content="\n".join(lines),
        date=entry_date if entry_date is not None else datetime.utcnow().date(),
    )
    db.add(diary_entry)
    db.commit()
    db.refresh(diary_entry)

    card.diary_id = diary_entry.id
    db.commit()
    db.refresh(card)

    logger.info(
        "Card→Diary expanded: card_id=%s → diary_id=%d",
        card_id,
        diary_entry.id,
    )
    return diary_entry


# ── stats ───────────────────────────────────────────────────────────────


def get_card_stats(db: Session) -> dict:
    """Get summary stats for the memory management dashboard."""
    total = db.query(MemoryCardRow).count()

    from sqlalchemy import func

    emotion_counts = (
        db.query(MemoryCardRow.emotion, func.count(MemoryCardRow.card_id))
        .group_by(MemoryCardRow.emotion)
        .order_by(func.count(MemoryCardRow.card_id).desc())
        .limit(10)
        .all()
    )

    expanded = db.query(MemoryCardRow).filter(MemoryCardRow.diary_id.isnot(None)).count()
    not_expanded = total - expanded

    avg_mood = (
        db.query(func.avg(MemoryCardRow.mood_score)).scalar() or 0.0
    )

    return {
        "total_cards": total,
        "expanded_to_diary": expanded,
        "not_expanded": not_expanded,
        "average_mood_score": round(float(avg_mood), 3),
        "top_emotions": [
            {"emotion": e, "count": c} for e, c in emotion_counts
        ],
    }


def get_mood_trends(
    db: Session,
    *,
    days: int = 30,
) -> list[dict]:
    """Get daily average mood scores for trend chart.

    Returns a list of {date, avg_mood, card_count} sorted by date ascending.
    """
    from sqlalchemy import func, text

    cutoff = datetime.utcnow().date()
    start = cutoff - __import__("datetime").timedelta(days=days - 1)

    rows = (
        db.query(
            func.date(MemoryCardRow.created_at).label("day"),
            func.avg(MemoryCardRow.mood_score).label("avg_mood"),
            func.count(MemoryCardRow.card_id).label("card_count"),
        )
        .filter(MemoryCardRow.created_at >= text(f"'{start.isoformat()}'"))
        .group_by(func.date(MemoryCardRow.created_at))
        .order_by(func.date(MemoryCardRow.created_at).asc())
        .all()
    )

    return [
        {"date": str(row.day), "avg_mood": round(float(row.avg_mood), 3), "card_count": row.card_count}
        for row in rows
    ]
