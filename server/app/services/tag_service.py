"""Tag CRUD scoped per-user via ``user_id`` (multi-user)."""

from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.infrastructure.models.tag import TagRow
from app.shared.errors import TagConflictError, TagNotFoundError

DEFAULT_MOOD_TAGS: tuple[tuple[str, str], ...] = (
    ("开心", "#10B981"),
    ("平静", "#3B82F6"),
    ("难过", "#6366F1"),
    ("委屈", "#8B5CF6"),
    ("沮丧", "#6B7280"),
    ("焦虑", "#F59E0B"),
    ("愤怒", "#EF4444"),
)


def list_tags(db: Session, *, user_id: str, sort_by_usage: bool = True) -> list[TagRow]:
    order = desc(TagRow.usage_count) if sort_by_usage else desc(TagRow.created_at)
    return db.query(TagRow).filter(TagRow.user_id == user_id).order_by(order).all()


def get_tag(db: Session, tag_id: int, *, user_id: str) -> TagRow:
    tag = db.query(TagRow).filter(TagRow.user_id == user_id).filter(TagRow.id == tag_id).first()
    if tag is None:
        raise TagNotFoundError(tag_id=tag_id)
    return tag


def create_tag(
    db: Session,
    *,
    user_id: str,
    name: str,
    color: str = "#6B7280",
) -> TagRow:
    existing = (
        db.query(TagRow).filter(TagRow.user_id == user_id).filter(TagRow.name == name).first()
    )
    if existing is not None:
        raise TagConflictError()

    tag = TagRow(user_id=user_id, name=name, color=color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def delete_tag(db: Session, tag_id: int, *, user_id: str) -> None:
    tag = db.query(TagRow).filter(TagRow.user_id == user_id).filter(TagRow.id == tag_id).first()
    if tag is None:
        raise TagNotFoundError(tag_id=tag_id)
    db.delete(tag)
    db.commit()


def seed_mood_tags(db: Session, *, user_id: str) -> list[TagRow]:
    """Idempotently add default mood labels (开心/难过/…). Skips names that already exist."""
    for name, color in DEFAULT_MOOD_TAGS:
        existing = (
            db.query(TagRow).filter(TagRow.user_id == user_id).filter(TagRow.name == name).first()
        )
        if existing is None:
            db.add(TagRow(user_id=user_id, name=name, color=color))
    db.commit()
    return list_tags(db, user_id=user_id)
