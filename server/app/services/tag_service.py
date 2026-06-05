"""Tag CRUD for the single-user desktop app."""

from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.infrastructure.models.tag import TagRow
from app.shared.errors import TagConflictError, TagNotFoundError


def list_tags(db: Session, *, sort_by_usage: bool = True) -> list[TagRow]:
    order = desc(TagRow.usage_count) if sort_by_usage else desc(TagRow.created_at)
    return db.query(TagRow).order_by(order).all()


def get_tag(db: Session, tag_id: int) -> TagRow:
    tag = db.query(TagRow).filter(TagRow.id == tag_id).first()
    if tag is None:
        raise TagNotFoundError(tag_id=tag_id)
    return tag


def create_tag(db: Session, *, name: str, color: str = "#6B7280") -> TagRow:
    existing = db.query(TagRow).filter(TagRow.name == name).first()
    if existing is not None:
        raise TagConflictError()

    tag = TagRow(name=name, color=color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def delete_tag(db: Session, tag_id: int) -> None:
    tag = db.query(TagRow).filter(TagRow.id == tag_id).first()
    if tag is None:
        raise TagNotFoundError(tag_id=tag_id)
    db.delete(tag)
    db.commit()
