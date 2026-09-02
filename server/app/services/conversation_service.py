"""Conversation (chat) CRUD service."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.models.conversation import ChatMessageRow, ConversationRow
from app.shared.errors import ConversationNotFoundError


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


# ── Conversations ────────────────────────────────────────────────────


def create_conversation(
    db: Session, *, user_id: str, replier_id: str = "preset-warm"
) -> ConversationRow:
    row = ConversationRow(
        id=_new_id(),
        user_id=user_id,
        title="新会话",
        active_replier_id=replier_id,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_conversations(db: Session, *, user_id: str, limit: int = 50) -> list[ConversationRow]:
    return (
        db.query(ConversationRow)
        .filter(ConversationRow.user_id == user_id)
        .order_by(ConversationRow.updated_at.desc())
        .limit(limit)
        .all()
    )


def get_conversation(db: Session, *, user_id: str, conversation_id: str) -> ConversationRow | None:
    return (
        db.query(ConversationRow)
        .filter(
            ConversationRow.id == conversation_id,
            ConversationRow.user_id == user_id,
        )
        .first()
    )


def update_conversation_title(
    db: Session, *, user_id: str, conversation_id: str, title: str
) -> ConversationRow | None:
    row = get_conversation(db, user_id=user_id, conversation_id=conversation_id)
    if row is None:
        return None
    row.title = title
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def touch_conversation(db: Session, *, user_id: str, conversation_id: str) -> None:
    row = get_conversation(db, user_id=user_id, conversation_id=conversation_id)
    if row is not None:
        row.updated_at = _now()
        db.commit()


def delete_conversation(db: Session, *, user_id: str, conversation_id: str) -> bool:
    row = get_conversation(db, user_id=user_id, conversation_id=conversation_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


# ── Messages ─────────────────────────────────────────────────────────
#
# ChatMessageRow has no ``user_id`` column — ownership is established through
# the parent ConversationRow. Every message operation therefore verifies the
# conversation belongs to the requesting user first.


def list_messages(db: Session, *, user_id: str, conversation_id: str) -> list[ChatMessageRow]:
    if get_conversation(db, user_id=user_id, conversation_id=conversation_id) is None:
        return []
    return (
        db.query(ChatMessageRow)
        .filter(ChatMessageRow.conversation_id == conversation_id)
        .order_by(ChatMessageRow.created_at.asc())
        .all()
    )


def add_message(
    db: Session,
    *,
    user_id: str,
    conversation_id: str,
    role: str,
    content: str,
    retrieved_diary_ids: list[int] | None = None,
    retrieved_memory_ids: list[str] | None = None,
    attached_card_ids: list[str] | None = None,
    attached_plan_ids: list[str] | None = None,
    skill_result: dict[str, Any] | None = None,
    token_info: dict[str, Any] | None = None,
) -> ChatMessageRow:
    if get_conversation(db, user_id=user_id, conversation_id=conversation_id) is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)
    row = ChatMessageRow(
        id=_new_id(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        retrieved_diary_ids=json.dumps(retrieved_diary_ids) if retrieved_diary_ids else None,
        retrieved_memory_ids=json.dumps(retrieved_memory_ids) if retrieved_memory_ids else None,
        attached_card_ids=json.dumps(attached_card_ids) if attached_card_ids else None,
        attached_plan_ids=json.dumps(attached_plan_ids) if attached_plan_ids else None,
        skill_result=json.dumps(skill_result, ensure_ascii=False) if skill_result else None,
        token_info=json.dumps(token_info) if token_info else None,
        created_at=_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_user_message_and_reply(
    db: Session,
    *,
    user_id: str,
    conversation_id: str,
    content: str,
    reply_content: str,
    retrieved_diary_ids: list[int] | None = None,
    retrieved_memory_ids: list[str] | None = None,
    attached_card_ids: list[str] | None = None,
    attached_plan_ids: list[str] | None = None,
    skill_result: dict[str, Any] | None = None,
    token_info: dict[str, Any] | None = None,
) -> tuple[ChatMessageRow, ChatMessageRow]:
    user_msg = add_message(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        role="user",
        content=content,
        attached_card_ids=attached_card_ids,
        attached_plan_ids=attached_plan_ids,
    )
    reply_msg = add_message(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        role="assistant",
        content=reply_content,
        retrieved_diary_ids=retrieved_diary_ids,
        retrieved_memory_ids=retrieved_memory_ids,
        skill_result=skill_result,
        token_info=token_info,
    )
    touch_conversation(db, user_id=user_id, conversation_id=conversation_id)

    # Auto-title from first user message
    conv = get_conversation(db, user_id=user_id, conversation_id=conversation_id)
    if conv and conv.title == "新会话":
        title = content[:20].replace("\n", " ")
        update_conversation_title(db, user_id=user_id, conversation_id=conversation_id, title=title)

    return user_msg, reply_msg
