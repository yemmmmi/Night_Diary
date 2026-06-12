"""Diary CRUD with Chroma vector sync (single-user, no ``user_id``)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.models.tag import TagRow
from app.shared.errors import DiaryNotFoundError, ValidationError

if TYPE_CHECKING:
    from app.domain.rag.collections import DiaryCollectionManager

logger = logging.getLogger(__name__)

RECENT_HISTORY_DAYS = 7
RECENT_HISTORY_LIMIT = 10


def _format_tags_for_chroma(tags: list[TagRow]) -> str:
    return ",".join(tag.name for tag in tags if tag.name)


def _sync_to_chroma(
    collection_manager: DiaryCollectionManager | None,
    entry: DiaryEntryRow,
) -> None:
    if collection_manager is None:
        return
    date_str = entry.date.isoformat() if entry.date else ""
    tags_str = _format_tags_for_chroma(entry.tags)
    try:
        collection_manager.update_diary(
            str(entry.id),
            entry.content or "",
            date=date_str,
            tags=tags_str,
        )
    except Exception as exc:
        logger.warning("Chroma sync failed for diary_id=%s: %s", entry.id, exc)


def create_entry(
    db: Session,
    *,
    content: str,
    entry_date: date | None = None,
    weather: str | None = None,
    tag_ids: list[int] | None = None,
    collection_manager: DiaryCollectionManager | None = None,
) -> DiaryEntryRow:
    if not content or not content.strip():
        raise ValidationError("日记内容不能为空")

    entry = DiaryEntryRow(
        content=content.strip(),
        weather=weather,
        date=entry_date if entry_date is not None else datetime.utcnow().date(),
    )
    if tag_ids:
        tags = db.query(TagRow).filter(TagRow.id.in_(tag_ids)).all()
        entry.tags = tags

    db.add(entry)
    db.commit()
    db.refresh(entry)
    _sync_to_chroma(collection_manager, entry)
    return entry


def list_entries(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 20,
) -> list[DiaryEntryRow]:
    return (
        db.query(DiaryEntryRow)
        .order_by(desc(DiaryEntryRow.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_entry(db: Session, diary_id: int) -> DiaryEntryRow:
    entry = db.query(DiaryEntryRow).filter(DiaryEntryRow.id == diary_id).first()
    if entry is None:
        raise DiaryNotFoundError(diary_id=diary_id)
    return entry


def get_recent_entries(
    db: Session,
    *,
    days: int = RECENT_HISTORY_DAYS,
    limit: int = RECENT_HISTORY_LIMIT,
) -> list[DiaryEntryRow]:
    """Shared helper for analysis context — eliminates duplicated 7-day logic."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    return (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.created_at >= cutoff)
        .order_by(desc(DiaryEntryRow.created_at))
        .limit(limit)
        .all()
    )


def update_entry(
    db: Session,
    diary_id: int,
    *,
    content: str | None = None,
    weather: str | None = None,
    tag_ids: list[int] | None = None,
    collection_manager: DiaryCollectionManager | None = None,
) -> DiaryEntryRow:
    entry = get_entry(db, diary_id)

    if content is not None:
        if not content.strip():
            raise ValidationError("日记内容不能为空")
        entry.content = content.strip()

    if weather is not None:
        entry.weather = weather

    if tag_ids is not None:
        tags = db.query(TagRow).filter(TagRow.id.in_(tag_ids)).all()
        entry.tags = tags

    entry.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(entry)
    _sync_to_chroma(collection_manager, entry)
    return entry


def delete_entry(
    db: Session,
    diary_id: int,
    *,
    collection_manager: DiaryCollectionManager | None = None,
) -> None:
    entry = get_entry(db, diary_id)
    if collection_manager is not None:
        try:
            collection_manager.delete_diary(str(diary_id))
        except Exception as exc:
            logger.warning("Chroma delete failed for diary_id=%s: %s", diary_id, exc)
    db.delete(entry)
    db.commit()


def format_history_summary(
    entries: list[DiaryEntryRow],
    *,
    exclude_id: int | None = None,
    max_snippet: int = 200,
) -> str:
    if not entries:
        return "（暂无历史记录）"

    lines: list[str] = []
    for entry in entries:
        if exclude_id is not None and entry.id == exclude_id:
            continue
        date_str = entry.date.isoformat() if entry.date else "未知"
        content = entry.content or ""
        snippet = content[:max_snippet] + "..." if len(content) > max_snippet else content
        tag_str = ""
        if entry.tags:
            tag_str = " [" + ", ".join(f"#{t.name}" for t in entry.tags) + "]"
        lines.append(f"[{date_str}]{tag_str} {snippet}")

    return "\n".join(lines) if lines else "（暂无历史记录）"


def format_tags_context(tags: list[TagRow]) -> str:
    if not tags:
        return "（未设置标签）"
    return "、".join(f"#{tag.name}" for tag in tags if tag.name)
