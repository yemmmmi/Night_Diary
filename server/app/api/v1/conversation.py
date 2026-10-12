"""Conversation API routes."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Request, Response, status

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
from app.api.mappers import conversation_to_response, message_to_response
from app.api.schemas import (
    ConversationResponse,
    MessageResponse,
    RegenerateResponse,
    RollbackResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from app.config import get_settings
from app.services import conversation_ai_service, conversation_service, memory_service
from app.shared.errors import ConversationNotFoundError, NotFoundError, ValidationError
from app.shared.task_registry import get_task_registry

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
    http_request: Request,
) -> SendMessageResponse:
    conv = conversation_service.get_conversation(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)

    trace_id = http_request.headers.get("X-Trace-Id")
    reply_message_id = uuid.uuid4().hex
    result = conversation_ai_service.generate_reply(
        db,
        container,
        conversation_id=conversation_id,
        content=body.content,
        diary_ids=body.diary_ids,
        user_id=str(user.id),
        auto_retrieve=body.auto_retrieve,
        trace_id=trace_id,
        card_ids=body.card_ids,
        plan_ids=body.plan_ids,
        tag_names=body.tag_names,
        forced_skill=body.skill,
        reply_message_id=reply_message_id,
    )

    user_msg, reply_msg = conversation_service.add_user_message_and_reply(
        db,
        user_id=str(user.id),
        conversation_id=conversation_id,
        content=body.content,
        reply_content=result.reply_text,
        retrieved_diary_ids=result.retrieved_diary_ids,
        retrieved_memory_ids=result.retrieved_memory_ids,
        attached_card_ids=body.card_ids,
        attached_plan_ids=body.plan_ids,
        attached_tag_names=body.tag_names,
        skill_result=result.skill_result,
        process_info=result.process_info,
        token_info=result.token_info,
        reply_message_id=reply_message_id,
    )
    return SendMessageResponse(
        message=message_to_response(user_msg),
        reply=message_to_response(reply_msg),
    )


@router.post(
    "/{conversation_id}/messages/stream",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def send_message_streaming(
    conversation_id: str,
    body: SendMessageRequest,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
    http_request: Request,
) -> dict[str, Any]:
    """Streaming endpoint - returns ``trace_id`` immediately.

    Content streams via SSE at ``/api/v1/dev/traces/{trace_id}/stream``.

    When ``STREAMING_ENABLED=false`` (the default), this endpoint returns
    ``{"streaming": False, "trace_id": ""}`` so the frontend can fall back
    to the synchronous :http:post:`/conversations/{id}/messages` endpoint.

    When ``STREAMING_ENABLED=true``, it launches
    :func:`generate_reply_streaming` as a background task and returns a
    ``trace_id`` that the frontend subscribes to for SSE events.
    """
    settings = get_settings()
    trace_id = http_request.headers.get("X-Trace-Id") or str(uuid.uuid4())

    conv = conversation_service.get_conversation(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)

    if not settings.streaming_enabled:
        # Fallback: tell the frontend to use the synchronous endpoint.
        return {"streaming": False, "trace_id": ""}

    # Launch streaming generation as a background task so this endpoint
    # returns immediately. The frontend subscribes to the trace_id SSE
    # stream to receive TEXT_DELTA / REPLY_END events.
    reply_message_id = uuid.uuid4().hex
    task = asyncio.create_task(
        conversation_ai_service.generate_reply_streaming(
            db=db,
            container=container,
            conversation_id=conversation_id,
            content=body.content,
            diary_ids=body.diary_ids or [],
            user_id=str(user.id),
            auto_retrieve=body.auto_retrieve,
            trace_id=trace_id,
            card_ids=body.card_ids,
            plan_ids=body.plan_ids,
            tag_names=body.tag_names,
            forced_skill=body.skill,
            reply_message_id=reply_message_id,
        )
    )
    # Register with TaskRegistry for lifecycle management (cancel on abort,
    # auto-cleanup on done, cancel_all on shutdown).
    get_task_registry().register(trace_id, task)

    return {"streaming": True, "trace_id": trace_id}


@router.post(
    "/{conversation_id}/messages/abort",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def abort_message(
    conversation_id: str,
    body: dict[str, Any],
    user: CurrentUserDep,
) -> dict[str, Any]:
    """Abort a streaming reply by trace_id.

    Returns ``{"cancelled": bool}`` indicating whether a live task was
    found and cancelled. The cancelled task's ``_terminating_reply``
    finally-block will still emit ``REPLY_END(error="cancelled")`` so the
    frontend can exit the streaming state cleanly.
    """
    trace_id = body.get("trace_id", "")
    if not trace_id:
        return {"cancelled": False}

    cancelled = await get_task_registry().cancel(trace_id)
    return {"cancelled": cancelled}


@router.post(
    "/{conversation_id}/messages/{message_id}/rollback",
    response_model=RollbackResponse,
)
def rollback_messages(
    conversation_id: str,
    message_id: str,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> RollbackResponse:
    """Roll a conversation back to before a message (B3).

    Deletes the given message and every message after it. Memory entries
    written by the removed turns are undone via their ``source_message_id``
    provenance so the memory store stays consistent with the shorter
    conversation. The cached session is dropped so the next turn rebuilds its
    context from the database.
    """
    _require_message(db, user_id=str(user.id), conversation_id=conversation_id, message_id=message_id)
    removed_ids = conversation_service.delete_messages_from(
        db, user_id=str(user.id), conversation_id=conversation_id, message_id=message_id
    )
    removed_memories = memory_service.delete_by_source_messages(
        container, user_id=str(user.id), message_ids=removed_ids
    )
    _reset_session(conversation_id)
    remaining = conversation_service.list_messages(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    return RollbackResponse(
        removed_message_ids=removed_ids,
        removed_memories=removed_memories,
        messages=[message_to_response(m) for m in remaining],
    )


@router.post(
    "/{conversation_id}/messages/{message_id}/regenerate",
    response_model=RegenerateResponse,
)
def regenerate_reply(
    conversation_id: str,
    message_id: str,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
    http_request: Request,
) -> RegenerateResponse:
    """Regenerate an assistant reply (B3).

    Deletes the target reply and every message after it, then regenerates a
    reply from its preceding user message. The old reply's memory writes are
    undone; the new reply writes fresh ones. Attachments (cards/plans/tags) are
    inherited from the user message; pinned diaries are not persisted, so
    regeneration re-retrieves by content (``auto_retrieve``).
    """
    target = _require_message(
        db, user_id=str(user.id), conversation_id=conversation_id, message_id=message_id
    )
    if target.role != "assistant":
        raise ValidationError("只能重新生成夜记的回信")

    messages = conversation_service.list_messages(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    index = next((i for i, m in enumerate(messages) if m.id == message_id), None)
    if index is None or index == 0 or messages[index - 1].role != "user":
        raise ValidationError("找不到这条回信对应的来信")
    source = messages[index - 1]

    removed_ids = conversation_service.delete_messages_from(
        db, user_id=str(user.id), conversation_id=conversation_id, message_id=message_id
    )
    removed_memories = memory_service.delete_by_source_messages(
        container, user_id=str(user.id), message_ids=removed_ids
    )
    _reset_session(conversation_id)

    reply_message_id = uuid.uuid4().hex
    result = conversation_ai_service.generate_reply(
        db,
        container,
        conversation_id=conversation_id,
        content=source.content,
        diary_ids=[],
        user_id=str(user.id),
        auto_retrieve=True,
        trace_id=http_request.headers.get("X-Trace-Id"),
        card_ids=json.loads(source.attached_card_ids) if source.attached_card_ids else None,
        plan_ids=json.loads(source.attached_plan_ids) if source.attached_plan_ids else None,
        tag_names=json.loads(source.attached_tag_names) if source.attached_tag_names else None,
        reply_message_id=reply_message_id,
    )
    reply_msg = conversation_service.add_message(
        db,
        user_id=str(user.id),
        conversation_id=conversation_id,
        role="assistant",
        content=result.reply_text,
        message_id=reply_message_id,
        retrieved_diary_ids=result.retrieved_diary_ids,
        retrieved_memory_ids=result.retrieved_memory_ids,
        skill_result=result.skill_result,
        process_info=result.process_info,
        token_info=result.token_info,
    )
    remaining = conversation_service.list_messages(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    return RegenerateResponse(
        removed_message_ids=removed_ids,
        removed_memories=removed_memories,
        reply=message_to_response(reply_msg),
        messages=[message_to_response(m) for m in remaining],
    )


def _require_message(
    db: Any, *, user_id: str, conversation_id: str, message_id: str
) -> Any:
    """Return the owned message or raise 404 (shared by rollback/regenerate)."""
    if conversation_service.get_conversation(
        db, user_id=user_id, conversation_id=conversation_id
    ) is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)
    message = conversation_service.get_message(
        db, user_id=user_id, conversation_id=conversation_id, message_id=message_id
    )
    if message is None:
        raise NotFoundError(resource="消息", resource_id=message_id)
    return message


def _reset_session(conversation_id: str) -> None:
    """Drop the cached session so the next turn rebuilds from the (shorter) DB history."""
    from app.services.ai.session_context import clear_session

    clear_session(conversation_id)


@router.post("/{conversation_id}/generate-card", response_model=dict[str, Any])
def generate_card_from_conversation(
    conversation_id: str, db: DbDep, user: CurrentUserDep, container: ContainerDep
) -> dict[str, Any]:
    """Extract a memory-card draft from conversation history."""
    conv = conversation_service.get_conversation(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)
    return conversation_ai_service.generate_card_from_conversation(
        db,
        container,
        user_id=str(user.id),
        conversation_id=conversation_id,
    )
