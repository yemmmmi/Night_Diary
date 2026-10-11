"""Diary CRUD with Chroma vector sync, scoped per-user via ``user_id``."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.models.image_asset import ImageAssetRow
from app.infrastructure.models.memory_card import MemoryCardRow
from app.services.card_service import _json_to_emotions
from app.shared.errors import DiaryNotFoundError, ValidationError

if TYPE_CHECKING:
    from app.domain.rag.collections import DiaryCollectionManager
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

RECENT_HISTORY_DAYS = 7
RECENT_HISTORY_LIMIT = 10
MAX_SNIPPET = 200


def _schedule_digest_refresh(
    container: ServiceContainer | None,
    entry: DiaryEntryRow,
    *,
    user_id: str,
) -> None:
    """Async day-digest rebuild after a typed diary write (best-effort, never raises)."""
    if container is None or entry.date is None:
        return
    try:
        from app.services.digest_worker import schedule_day_digest_refresh

        schedule_day_digest_refresh(
            user_id,
            entry.date.isoformat(),
            entry.id,
        )
    except Exception as exc:
        logger.warning("Digest refresh scheduling failed: diary_id=%s %s", entry.id, exc)


def _format_emotion_for_chroma(
    db: Session,
    entry: DiaryEntryRow,
    *,
    user_id: str,
) -> str:
    card = (
        db.query(MemoryCardRow)
        .filter(MemoryCardRow.user_id == user_id)
        .filter(MemoryCardRow.diary_id == entry.id)
        .first()
    )
    if card is None:
        return ""
    emotions = _json_to_emotions(card.emotions_json, card.emotion)
    return "、".join(emotions) if emotions else card.emotion


def _sync_to_chroma(
    db: Session,
    collection_manager: DiaryCollectionManager | None,
    entry: DiaryEntryRow,
    *,
    user_id: str,
) -> None:
    if collection_manager is None:
        return
    date_str = entry.date.isoformat() if entry.date else ""
    emotion_str = _format_emotion_for_chroma(db, entry, user_id=user_id)
    try:
        collection_manager.update_diary(
            str(entry.id),
            entry.content or "",
            date=date_str,
            tags=emotion_str,
        )
    except Exception as exc:
        logger.warning("Chroma sync failed for diary_id=%s: %s", entry.id, exc)


def parse_image_asset_ids(raw: str | None) -> list[int]:
    """Parse a persisted ``image_assets_json`` value into a list of asset ids."""
    try:
        parsed = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, int)]


def _serialize_image_asset_ids(
    db: Session,
    image_asset_ids: list[int] | None,
    *,
    user_id: str,
) -> str | None:
    """Validate that every asset belongs to the user, then return a JSON id list."""
    if not image_asset_ids:
        return None
    unique_ids = list(dict.fromkeys(image_asset_ids))
    owned = (
        db.query(ImageAssetRow.id)
        .filter(ImageAssetRow.user_id == user_id)
        .filter(ImageAssetRow.id.in_(unique_ids))
        .all()
    )
    owned_ids = {row_id for (row_id,) in owned}
    missing = [asset_id for asset_id in unique_ids if asset_id not in owned_ids]
    if missing:
        raise ValidationError(f"图片附件不存在或无权限：{missing}")
    return json.dumps(unique_ids)


def image_attachment_note(
    db: Session,
    entry: DiaryEntryRow,
    *,
    user_id: str,
) -> str:
    """List a diary's attached image filenames for the agent, "" when none."""
    ids = parse_image_asset_ids(entry.image_assets_json)
    if not ids:
        return ""
    rows = (
        db.query(ImageAssetRow)
        .filter(ImageAssetRow.user_id == user_id)
        .filter(ImageAssetRow.id.in_(ids))
        .all()
    )
    by_id = {row.id: row.original_filename for row in rows}
    names = [by_id[asset_id] for asset_id in ids if asset_id in by_id]
    if not names:
        return ""
    return "附图片：" + "、".join(names)


def create_entry(
    db: Session,
    *,
    user_id: str,
    content: str,
    entry_date: date | None = None,
    weather: str | None = None,
    image_asset_ids: list[int] | None = None,
    collection_manager: DiaryCollectionManager | None = None,
    container: ServiceContainer | None = None,
) -> DiaryEntryRow:
    if not content or not content.strip():
        raise ValidationError("日记内容不能为空")

    entry = DiaryEntryRow(
        user_id=user_id,
        content=content.strip(),
        weather=weather,
        date=entry_date if entry_date is not None else datetime.now(UTC).date(),
        image_assets_json=_serialize_image_asset_ids(db, image_asset_ids, user_id=user_id),
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)
    _sync_to_chroma(db, collection_manager, entry, user_id=user_id)
    _schedule_digest_refresh(container, entry, user_id=user_id)
    return entry


def list_entries(
    db: Session,
    *,
    user_id: str,
    skip: int = 0,
    limit: int = 20,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[DiaryEntryRow]:
    query = db.query(DiaryEntryRow).filter(DiaryEntryRow.user_id == user_id)
    if date_from is not None:
        query = query.filter(DiaryEntryRow.date >= date_from)
    if date_to is not None:
        query = query.filter(DiaryEntryRow.date <= date_to)
    return (
        query.order_by(desc(DiaryEntryRow.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_entry(db: Session, diary_id: int, *, user_id: str) -> DiaryEntryRow:
    entry = (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.user_id == user_id)
        .filter(DiaryEntryRow.id == diary_id)
        .first()
    )
    if entry is None:
        raise DiaryNotFoundError(diary_id=diary_id)
    return entry


def get_entries_by_ids(
    db: Session,
    diary_ids: list[int],
    *,
    user_id: str,
) -> list[DiaryEntryRow]:
    if not diary_ids:
        return []
    rows = (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.user_id == user_id)
        .filter(DiaryEntryRow.id.in_(diary_ids))
        .all()
    )
    by_id = {row.id: row for row in rows}
    return [by_id[did] for did in diary_ids if did in by_id]


def get_recent_entries(
    db: Session,
    *,
    user_id: str,
    days: int = RECENT_HISTORY_DAYS,
    limit: int = RECENT_HISTORY_LIMIT,
) -> list[DiaryEntryRow]:
    """Shared helper for analysis context — eliminates duplicated 7-day logic."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.user_id == user_id)
        .filter(DiaryEntryRow.created_at >= cutoff)
        .order_by(desc(DiaryEntryRow.created_at))
        .limit(limit)
        .all()
    )


def update_entry(
    db: Session,
    diary_id: int,
    *,
    user_id: str,
    content: str | None = None,
    weather: str | None = None,
    image_asset_ids: list[int] | None = None,
    collection_manager: DiaryCollectionManager | None = None,
    container: ServiceContainer | None = None,
) -> DiaryEntryRow:
    entry = get_entry(db, diary_id, user_id=user_id)

    if content is not None:
        if not content.strip():
            raise ValidationError("日记内容不能为空")
        entry.content = content.strip()

    if weather is not None:
        entry.weather = weather

    if image_asset_ids is not None:
        entry.image_assets_json = _serialize_image_asset_ids(
            db, image_asset_ids, user_id=user_id
        )

    entry.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(entry)
    _sync_to_chroma(db, collection_manager, entry, user_id=user_id)
    _schedule_digest_refresh(container, entry, user_id=user_id)
    return entry


def delete_entry(
    db: Session,
    diary_id: int,
    *,
    user_id: str,
    collection_manager: DiaryCollectionManager | None = None,
    container: ServiceContainer | None = None,
) -> None:
    entry = get_entry(db, diary_id, user_id=user_id)
    day_iso = entry.date.isoformat() if entry.date is not None else None
    if collection_manager is not None:
        try:
            collection_manager.delete_diary(str(diary_id))
        except Exception as exc:
            logger.warning("Chroma delete failed for diary_id=%s: %s", diary_id, exc)
    db.delete(entry)
    db.commit()
    if container is not None and day_iso is not None:
        try:
            from app.services.digest_worker import schedule_day_digest_refresh

            schedule_day_digest_refresh(user_id, day_iso, diary_id)
        except Exception as exc:
            logger.warning(
                "Digest refresh scheduling failed after delete: diary_id=%s %s",
                diary_id,
                exc,
            )


def format_history_summary(
    entries: list[DiaryEntryRow],
    *,
    exclude_id: int | None = None,
    max_snippet: int = MAX_SNIPPET,
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
        lines.append(f"[{date_str}] {snippet}")

    return "\n".join(lines) if lines else "（暂无历史记录）"


def format_emotion_context(
    db: Session,
    entry: DiaryEntryRow,
    *,
    user_id: str,
) -> str:
    """Build mood context from linked memory card, or prompt AI to infer from text."""
    card = (
        db.query(MemoryCardRow)
        .filter(MemoryCardRow.user_id == user_id)
        .filter(MemoryCardRow.diary_id == entry.id)
        .first()
    )
    if card is None:
        return "（未标注，请从正文推断情绪）"
    emotions = _json_to_emotions(card.emotions_json, card.emotion)
    if emotions:
        return f"关联记忆卡片情绪：{'、'.join(emotions)}"
    if card.emotion:
        return f"关联记忆卡片情绪：{card.emotion}"
    return "（未标注，请从正文推断情绪）"


def format_diary_excerpt(entry: DiaryEntryRow, *, max_chars: int = 800) -> str:
    date_str = entry.date.isoformat() if entry.date else "未知"
    content = (entry.content or "").strip()
    if len(content) > max_chars:
        content = content[:max_chars] + "..."
    return f"[日记 #{entry.id} · {date_str}]\n{content}"
