"""Conversation API routes."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import DbDep
from app.api.mappers import conversation_to_response, message_to_response
from app.api.schemas import (
    ConversationResponse,
    MessageResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services import conversation_service
from app.shared.errors import ConversationNotFoundError

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationResponse])
def list_conversations(db: DbDep) -> list[ConversationResponse]:
    rows = conversation_service.list_conversations(db)
    return [conversation_to_response(r) for r in rows]


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(db: DbDep) -> ConversationResponse:
    row = conversation_service.create_conversation(db)
    return conversation_to_response(row)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_conversation(conversation_id: str, db: DbDep) -> Response:
    if not conversation_service.delete_conversation(db, conversation_id):
        raise ConversationNotFoundError(conversation_id=conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def get_messages(conversation_id: str, db: DbDep) -> list[MessageResponse]:
    conv = conversation_service.get_conversation(db, conversation_id)
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)
    rows = conversation_service.list_messages(db, conversation_id)
    return [message_to_response(r) for r in rows]


@router.post("/{conversation_id}/messages", response_model=SendMessageResponse, status_code=status.HTTP_201_CREATED)
def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    db: DbDep,
) -> SendMessageResponse:
    conv = conversation_service.get_conversation(db, conversation_id)
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)

    # For now: echo + simple reply. AI-powered reply will replace this in a follow-up PR.
    reply_text = f"收到你的消息。这段对话的功能还在完善中，请期待后续更新。"

    user_msg, reply_msg = conversation_service.add_user_message_and_reply(
        db,
        conversation_id=conversation_id,
        content=body.content,
        reply_content=reply_text,
    )
    return SendMessageResponse(
        message=message_to_response(user_msg),
        reply=message_to_response(reply_msg),
    )


@router.post("/{conversation_id}/generate-card", response_model=dict)
def generate_card_summary(conversation_id: str, db: DbDep) -> dict:
    conv = conversation_service.get_conversation(db, conversation_id)
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)
    return {
        "emotion": "平静",
        "event_summary": "卡片生成功能将在后续版本中接入 AI",
        "tags": ["对话"],
    }
