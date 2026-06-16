"""Conversation (chat) CRUD service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.infrastructure.models.conversation import ChatMessageRow, ConversationRow


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.utcnow()


# ── Conversations ────────────────────────────────────────────────────

def create_conversation(db: Session, *, replier_id: str = "preset-warm") -> ConversationRow:
    row = ConversationRow(
        id=_new_id(),
        title="新会话",
        active_replier_id=replier_id,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_conversations(db: Session, *, limit: int = 50) -> list[ConversationRow]:
    return (
        db.query(ConversationRow)
        .order_by(ConversationRow.updated_at.desc())
        .limit(limit)
        .all()
    )


def get_conversation(db: Session, conversation_id: str) -> ConversationRow | None:
    return db.query(ConversationRow).filter(ConversationRow.id == conversation_id).first()


def update_conversation_title(db: Session, conversation_id: str, title: str) -> ConversationRow | None:
    row = get_conversation(db, conversation_id)
    if row is None:
        return None
    row.title = title
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def touch_conversation(db: Session, conversation_id: str) -> None:
    row = get_conversation(db, conversation_id)
    if row is not None:
        row.updated_at = _now()
        db.commit()


def delete_conversation(db: Session, conversation_id: str) -> bool:
    row = get_conversation(db, conversation_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


# ── Messages ─────────────────────────────────────────────────────────

def list_messages(db: Session, conversation_id: str) -> list[ChatMessageRow]:
    return (
        db.query(ChatMessageRow)
        .filter(ChatMessageRow.conversation_id == conversation_id)
        .order_by(ChatMessageRow.created_at.asc())
        .all()
    )


def add_message(
    db: Session,
    *,
    conversation_id: str,
    role: str,
    content: str,
    retrieved_diary_ids: list[int] | None = None,
    retrieved_memory_ids: list[str] | None = None,
) -> ChatMessageRow:
    row = ChatMessageRow(
        id=_new_id(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        retrieved_diary_ids=json.dumps(retrieved_diary_ids) if retrieved_diary_ids else None,
        retrieved_memory_ids=json.dumps(retrieved_memory_ids) if retrieved_memory_ids else None,
        created_at=_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_user_message_and_reply(
    db: Session,
    *,
    conversation_id: str,
    content: str,
    reply_content: str,
) -> tuple[ChatMessageRow, ChatMessageRow]:
    user_msg = add_message(db, conversation_id=conversation_id, role="user", content=content)
    reply_msg = add_message(db, conversation_id=conversation_id, role="assistant", content=reply_content)
    touch_conversation(db, conversation_id)

    # Auto-title from first user message
    conv = get_conversation(db, conversation_id)
    if conv and conv.title == "新会话":
        title = content[:20].replace("\n", " ")
        update_conversation_title(db, conversation_id, title)

    return user_msg, reply_msg
