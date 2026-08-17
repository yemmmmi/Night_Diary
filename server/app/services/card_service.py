"""Memory card CRUD with Card→EpisodicEntry bridge and Card→Diary expansion.

Cards are lightweight structured memory atoms. They flow into the
existing three-layer memory system:
  MemoryCard → card_to_episodic() → EpisodicEntry → episodic_memories
                                            → promote → UserProfile
  MemoryCard → expand_to_diary()   → DiaryEntry   → analysis_service
"""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.domain.memory.atom import UnifiedMemoryAtom
from app.domain.memory.types import EpisodicEntry
from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.models.memory_card import MemoryCardRow
from app.shared.errors import NotFoundError, ValidationError

if TYPE_CHECKING:
    from app.domain.memory.episodic import EpisodicMemory

logger = logging.getLogger(__name__)

RECENT_CARDS_DAYS = 30
RECENT_CARDS_LIMIT = 50

#: Card day boundary is Beijing time (UTC+8) — matches digest_service.
_BEIJING_OFFSET = timedelta(hours=8)


def _card_digest_day(row: MemoryCardRow) -> date:
    """The digest day for a card: its Beijing-time creation date."""
    created = row.created_at or datetime.now(UTC)
    return (created + _BEIJING_OFFSET).date()


def _refresh_day_digest(db: Session, row: MemoryCardRow, *, user_id: str) -> None:
    """V3 tree-hole: re-aggregate the day's digest card section (zero LLM).

    Never triggers an LLM call and never touches the digest's diary section —
    a quick 记一笔 must not make the user wait.
    """
    from app.services.digest_service import refresh_cards_section

    with contextlib.suppress(Exception):
        refresh_cards_section(db, user_id=user_id, day=_card_digest_day(row))
        db.commit()


# ── helpers ────────────────────────────────────────────────────────────


def _tags_to_json(tags: list[str]) -> str | None:
    return json.dumps(tags, ensure_ascii=False) if tags else None


def _json_to_tags(tags_json: str | None) -> list[str]:
    if not tags_json:
        return []
    try:
        parsed = json.loads(tags_json)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _emotions_to_json(emotions: list[str]) -> str | None:
    return json.dumps(emotions, ensure_ascii=False) if emotions else None


def _json_to_emotions(emotions_json: str | None, fallback: str) -> list[str]:
    if not emotions_json:
        return [fallback] if fallback else []
    try:
        parsed = json.loads(emotions_json)
        return parsed if isinstance(parsed, list) and parsed else ([fallback] if fallback else [])
    except (json.JSONDecodeError, TypeError):
        return [fallback] if fallback else []


def row_to_dict(row: MemoryCardRow) -> dict[str, Any]:
    return {
        "card_id": row.card_id,
        "emotion": row.emotion,
        "emotions": _json_to_emotions(row.emotions_json, row.emotion),
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
    user_id: str,
    emotion: str,
    emotions: list[str] | None = None,
    event_summary: str | None = None,
    mood_score: float = 0.5,
    tags: list[str] | None = None,
    importance: float = 0.5,
    card_type: str = "standard",
) -> MemoryCardRow:
    if not emotion.strip():
        raise ValidationError("情绪标签不能为空")

    cleaned_emotions = [e.strip() for e in (emotions or []) if e.strip()]
    primary = emotion.strip() or (cleaned_emotions[0] if cleaned_emotions else "")
    if not cleaned_emotions:
        cleaned_emotions = [primary]

    row = MemoryCardRow(
        card_id=uuid.uuid4().hex,
        user_id=user_id,
        emotion=primary,
        emotions_json=_emotions_to_json(cleaned_emotions),
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
    # V3 tree-hole: refresh the day's digest card section (zero LLM).
    _refresh_day_digest(db, row, user_id=user_id)
    return row


def get_card(db: Session, card_id: str, *, user_id: str) -> MemoryCardRow:
    row = (
        db.query(MemoryCardRow)
        .filter(MemoryCardRow.user_id == user_id)
        .filter(MemoryCardRow.card_id == card_id)
        .first()
    )
    if row is None:
        raise NotFoundError(resource="memory_card", resource_id=card_id)
    return row


def list_cards(
    db: Session,
    *,
    user_id: str,
    skip: int = 0,
    limit: int = 50,
    emotion: str | None = None,
    card_type: str | None = None,
    has_diary: bool | None = None,
) -> list[MemoryCardRow]:
    q = db.query(MemoryCardRow).filter(MemoryCardRow.user_id == user_id)

    if emotion:
        q = q.filter(MemoryCardRow.emotion == emotion)
    if card_type:
        q = q.filter(MemoryCardRow.card_type == card_type)
    if has_diary is True:
        q = q.filter(MemoryCardRow.diary_id.isnot(None))
    elif has_diary is False:
        q = q.filter(MemoryCardRow.diary_id.is_(None))

    return q.order_by(desc(MemoryCardRow.created_at)).offset(skip).limit(limit).all()


def update_card(
    db: Session,
    card_id: str,
    *,
    user_id: str,
    emotion: str | None = None,
    emotions: list[str] | None = None,
    event_summary: str | None = None,
    mood_score: float | None = None,
    tags: list[str] | None = None,
    importance: float | None = None,
) -> MemoryCardRow:
    row = get_card(db, card_id, user_id=user_id)

    if emotions is not None:
        cleaned = [e.strip() for e in emotions if e.strip()]
        if cleaned:
            row.emotions_json = _emotions_to_json(cleaned)
            row.emotion = cleaned[0]

    if emotion is not None:
        if not emotion.strip():
            raise ValidationError("情绪标签不能为空")
        row.emotion = emotion.strip()
        if emotions is None:
            row.emotions_json = _emotions_to_json([emotion.strip()])

    if event_summary is not None:
        row.event_summary = event_summary.strip() if event_summary else None

    if mood_score is not None:
        row.mood_score = max(0.0, min(1.0, mood_score))

    if tags is not None:
        row.tags_json = _tags_to_json(tags)

    if importance is not None:
        row.importance = max(0.0, min(1.0, importance))

    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    logger.info("Card updated: card_id=%s", card_id)
    # V3 tree-hole: re-aggregate the day's digest card section (zero LLM).
    _refresh_day_digest(db, row, user_id=user_id)
    return row


def delete_card(db: Session, card_id: str, *, user_id: str) -> None:
    row = get_card(db, card_id, user_id=user_id)
    day = _card_digest_day(row)
    db.delete(row)
    db.commit()
    logger.info("Card deleted: card_id=%s", card_id)
    # V3 tree-hole: re-aggregate the day's digest card section (zero LLM).
    from app.services.digest_service import refresh_cards_section

    with contextlib.suppress(Exception):
        refresh_cards_section(db, user_id=user_id, day=day)
        db.commit()


# ── Card → Episodic bridge ─────────────────────────────────────────────


def card_to_unified_atom(row: MemoryCardRow, user_id: str = "default") -> UnifiedMemoryAtom:
    """Convert a MemoryCardRow to a UnifiedMemoryAtom.

    Preserves all structured fields (tags, mood_score, emotions) that were
    previously lost in the card_to_episodic conversion.
    """
    import json
    from datetime import date as date_cls

    tags: list[str] = []
    if row.tags_json:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            tags = json.loads(row.tags_json)

    emotions: list[str] = []
    if row.emotions_json:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            emotions = json.loads(row.emotions_json)

    return UnifiedMemoryAtom(
        source="card",
        event_summary=row.event_summary or f"（{row.emotion}情绪记录）",
        emotion=row.emotion,
        emotions=emotions,
        mood_score=row.mood_score,
        tags=tags,
        importance=row.importance,
        event_date=row.created_at.date() if row.created_at else date_cls.today(),
        diary_id=row.diary_id,
        user_id=user_id,
    )


def card_to_episodic(row: MemoryCardRow) -> EpisodicEntry:
    """Convert a MemoryCardRow to an EpisodicEntry for the memory pipeline.

    Deprecated: prefer :func:`card_to_unified_atom` which preserves structured
    fields.  This function is kept for backward compatibility with existing
    call sites that construct EpisodicEntry directly.
    """
    event = row.event_summary or f"（{row.emotion}情绪记录）"
    return EpisodicEntry(
        event_summary=event,
        emotion=row.emotion,
        reply_insight="",
        source="card",
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

    Uses :func:`card_to_unified_atom` to preserve structured fields (tags,
    mood_score, emotions) in the episodic entry.
    Returns ``True`` if the entry was stored (importance > threshold).
    """
    if episodic is None:
        return False

    atom = card_to_unified_atom(row)
    entry = EpisodicEntry(
        event_summary=atom.event_summary[:120],
        emotion=atom.emotion,
        reply_insight=atom.reply_insight[:200],
        source=atom.source,
        timestamp=datetime.now(UTC).timestamp(),
        diary_ids=[str(atom.diary_id)] if atom.diary_id else [],
        importance=atom.importance,
        entry_id="",
        tags=atom.tags,
        mood_score=atom.mood_score,
        emotions=atom.emotions,
        event_date=atom.event_date.isoformat() if atom.event_date else None,
    )
    stored = episodic.store(entry)
    if stored:
        logger.debug(
            "Card→Episodic stored: card_id=%s event=%s importance=%.2f tags=%s",
            row.card_id,
            entry.event_summary,
            entry.importance,
            entry.tags,
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
    *,
    user_id: str,
) -> int:
    """Batch-sync recent un-pushed cards into episodic memory.

    Returns count of successfully stored entries.
    """
    if episodic is None:
        return 0

    recent = list_cards(db, skip=0, limit=RECENT_CARDS_LIMIT, user_id=user_id)
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
    user_id: str,
    entry_date: date | None = None,
    container: Any | None = None,
    auto_analyze: bool = True,
) -> tuple[DiaryEntryRow, Any | None]:
    """Expand a memory card into a full diary entry.

    Structured card fields (emotion, event, tags) stay on the linked card;
    diary content is pre-populated with the card's event_summary so the
    analysis pipeline can run immediately.

    When ``container`` is provided and ``auto_analyze`` is True, analysis is
    triggered automatically (best-effort — failures are logged, not raised).
    The card's ``diary_id`` is updated to link back to the new diary.

    Returns ``(diary_entry, analysis_row_or_none)``.
    """
    card = get_card(db, card_id, user_id=user_id)

    if card.diary_id is not None:
        raise ValidationError(f"卡片 {card_id} 已经展开为日记 #{card.diary_id}")

    # Pre-populate diary content from card's structured data
    initial_content = ""
    if card.event_summary and card.event_summary.strip():
        initial_content = card.event_summary.strip()
    else:
        # Generate minimal content from emotion so analysis has something to work with
        initial_content = f"今天记录了{card.emotion}的心情"

    diary_entry = DiaryEntryRow(
        user_id=user_id,
        content=initial_content,
        date=entry_date if entry_date is not None else datetime.now(UTC).date(),
    )
    db.add(diary_entry)
    db.commit()
    db.refresh(diary_entry)

    card.diary_id = diary_entry.id
    db.commit()
    db.refresh(card)

    logger.info(
        "Card→Diary expanded: card_id=%s → diary_id=%d content_len=%d",
        card_id,
        diary_entry.id,
        len(diary_entry.content or ""),
    )

    # Auto-trigger analysis (best-effort)
    analysis_row: Any | None = None
    if auto_analyze and container is not None and (diary_entry.content or "").strip():
        try:
            from app.services.analysis_service import trigger_analysis

            analysis_row, _mem_count = trigger_analysis(
                db,
                diary_entry.id,
                container,
                user_id=user_id,
            )
            logger.info(
                "Card→Diary auto-analysis: card_id=%s diary_id=%d analysis_id=%d",
                card_id,
                diary_entry.id,
                analysis_row.id,
            )
        except Exception as exc:
            logger.warning(
                "Card→Diary auto-analysis failed (non-blocking): card_id=%s diary_id=%d error=%s",
                card_id,
                diary_entry.id,
                exc,
            )

    return diary_entry, analysis_row


# ── stats ───────────────────────────────────────────────────────────────


def get_card_stats(db: Session, *, user_id: str) -> dict[str, Any]:
    """Get summary stats for the memory management dashboard."""
    total = db.query(MemoryCardRow).filter(MemoryCardRow.user_id == user_id).count()

    from sqlalchemy import func

    emotion_counts = (
        db.query(MemoryCardRow.emotion, func.count(MemoryCardRow.card_id))
        .filter(MemoryCardRow.user_id == user_id)
        .group_by(MemoryCardRow.emotion)
        .order_by(func.count(MemoryCardRow.card_id).desc())
        .limit(10)
        .all()
    )

    expanded = (
        db.query(MemoryCardRow)
        .filter(MemoryCardRow.user_id == user_id)
        .filter(MemoryCardRow.diary_id.isnot(None))
        .count()
    )
    not_expanded = total - expanded

    avg_mood = (
        db.query(func.avg(MemoryCardRow.mood_score))
        .filter(MemoryCardRow.user_id == user_id)
        .scalar()
        or 0.0
    )

    return {
        "total_cards": total,
        "expanded_to_diary": expanded,
        "not_expanded": not_expanded,
        "average_mood_score": round(float(avg_mood), 3),
        "top_emotions": [{"emotion": e, "count": c} for e, c in emotion_counts],
    }


def get_mood_trends(
    db: Session,
    *,
    user_id: str,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Get daily average mood scores for trend chart.

    Returns a list of {date, avg_mood, card_count} sorted by date ascending.
    """
    from sqlalchemy import func, text

    cutoff = datetime.now(UTC).date()
    start = cutoff - timedelta(days=days - 1)

    rows = (
        db.query(
            func.date(MemoryCardRow.created_at).label("day"),
            func.avg(MemoryCardRow.mood_score).label("avg_mood"),
            func.count(MemoryCardRow.card_id).label("card_count"),
        )
        .filter(MemoryCardRow.user_id == user_id)
        .filter(MemoryCardRow.created_at >= text(f"'{start.isoformat()}'"))
        .group_by(func.date(MemoryCardRow.created_at))
        .order_by(func.date(MemoryCardRow.created_at).asc())
        .all()
    )

    return [
        {
            "date": str(row.day),
            "avg_mood": round(float(row.avg_mood), 3),
            "card_count": row.card_count,
        }
        for row in rows
    ]
