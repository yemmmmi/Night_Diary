"""Conversation API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status

from app.api.deps import ContainerDep, DbDep
from app.api.mappers import conversation_to_response, message_to_response
from app.api.schemas import (
    ConversationResponse,
    MessageResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services import conversation_ai_service, conversation_service
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
    container: ContainerDep,
) -> SendMessageResponse:
    conv = conversation_service.get_conversation(db, conversation_id)
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)

    result = conversation_ai_service.generate_reply(
        db,
        container,
        conversation_id=conversation_id,
        content=body.content,
        diary_ids=body.diary_ids,
        auto_retrieve=body.auto_retrieve,
    )

    user_msg, reply_msg = conversation_service.add_user_message_and_reply(
        db,
        conversation_id=conversation_id,
        content=body.content,
        reply_content=result.reply_text,
        retrieved_diary_ids=result.retrieved_diary_ids,
        retrieved_memory_ids=result.retrieved_memory_ids,
    )
    return SendMessageResponse(
        message=message_to_response(user_msg),
        reply=message_to_response(reply_msg),
    )


@router.post("/{conversation_id}/generate-card", response_model=dict[str, Any])
def generate_card_summary(conversation_id: str, db: DbDep, container: ContainerDep) -> dict[str, Any]:
    conv = conversation_service.get_conversation(db, conversation_id)
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)
    return conversation_ai_service.generate_card_from_conversation(
        db, container, conversation_id=conversation_id,
    )
