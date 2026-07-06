"""Conversation API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
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
def list_conversations(db: DbDep, user: CurrentUserDep) -> list[ConversationResponse]:
    rows = conversation_service.list_conversations(db, user_id=str(user.id))
    return [conversation_to_response(r) for r in rows]


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(db: DbDep, user: CurrentUserDep) -> ConversationResponse:
    row = conversation_service.create_conversation(db, user_id=str(user.id))
    return conversation_to_response(row)


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str, db: DbDep, user: CurrentUserDep
) -> ConversationResponse:
    row = conversation_service.get_conversation(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    if row is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)
    return conversation_to_response(row)


@router.delete(
    "/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_conversation(conversation_id: str, db: DbDep, user: CurrentUserDep) -> Response:
    if not conversation_service.delete_conversation(
        db, user_id=str(user.id), conversation_id=conversation_id
    ):
        raise ConversationNotFoundError(conversation_id=conversation_id)
    # Clear the in-memory session context to avoid stale state
    from app.services.ai.session_context import clear_session

    clear_session(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def get_messages(conversation_id: str, db: DbDep, user: CurrentUserDep) -> list[MessageResponse]:
    conv = conversation_service.get_conversation(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)
    rows = conversation_service.list_messages(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    return [message_to_response(r) for r in rows]


@router.post(
    "/{conversation_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> SendMessageResponse:
    conv = conversation_service.get_conversation(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)

    result = conversation_ai_service.generate_reply(
        db,
        container,
        conversation_id=conversation_id,
        content=body.content,
        diary_ids=body.diary_ids,
        user_id=str(user.id),
        auto_retrieve=body.auto_retrieve,
    )

    user_msg, reply_msg = conversation_service.add_user_message_and_reply(
        db,
        user_id=str(user.id),
        conversation_id=conversation_id,
        content=body.content,
        reply_content=result.reply_text,
        retrieved_diary_ids=result.retrieved_diary_ids,
        retrieved_memory_ids=result.retrieved_memory_ids,
        token_info=result.token_info,
    )
    return SendMessageResponse(
        message=message_to_response(user_msg),
        reply=message_to_response(reply_msg),
    )


@router.post("/{conversation_id}/night-talk", response_model=dict[str, Any])
def generate_night_talk(
    conversation_id: str, db: DbDep, user: CurrentUserDep, container: ContainerDep
) -> dict[str, Any]:
    """Generate a night talk (关系记忆) from conversation history."""
    conv = conversation_service.get_conversation(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)
    return conversation_ai_service.generate_night_talk(
        db,
        container,
        user_id=str(user.id),
        conversation_id=conversation_id,
    )
