"""Tag CRUD scoped per-user via ``user_id`` (multi-user)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.infrastructure.models.tag import TagRow
from app.shared.errors import TagConflictError, TagNotFoundError


def list_tags(db: Session, *, user_id: str, sort_by_usage: bool = True) -> list[TagRow]:
    order = TagRow.usage_count.desc() if sort_by_usage else TagRow.created_at.desc()
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
