"""OpenAI-compatible facade (A5).

Exposes ``POST /v1/chat/completions`` and ``GET /v1/models`` so a user can
point any OpenAI client at their own 夜记 backend. The facade is a thin
adapter over the existing pipeline:

* **Auth** reuses the JWT bearer scheme (``get_current_user``) — the token
  doubles as the API key.
* **Generation** reuses ``generate_reply`` / ``generate_reply_streaming``, so
  crisis detection, retrieval, skills, and safety are identical to the web app.
* **Delivery** stays behind the same seam as scheduled tasks (E4's
  ``ResultSink``); the OpenAI response *is* the delivery channel here.

Stateless clients resend the full ``messages`` array each turn. 夜记 keeps one
dedicated conversation per user for this entry point so continuity is preserved
without trusting client-side history; pass the ``conversation_id`` extension to
route into a specific conversation instead.

Deliberately ignored (documented, not silently mis-honored): ``n`` > 1,
``temperature``, ``top_p``, ``max_tokens``, ``user``, and client ``system`` /
``assistant`` history — 夜记 owns persona, retrieval, and length policy. Errors
the facade can detect are returned in OpenAI's error envelope.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
from app.api.schemas_openai import (
    OpenAIChatChoice,
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
    OpenAIChatMessageOut,
    OpenAIModelCard,
    OpenAIModelList,
    OpenAIUsage,
)
from app.services import conversation_ai_service, conversation_service, model_service
from app.shared.errors import ConversationNotFoundError
from app.shared.streaming_events import StreamingEventType
from app.shared.task_registry import get_task_registry
from app.shared.trace_event_bus import get_event_bus

router = APIRouter(prefix="/v1", tags=["openai-compat"])

#: Fallback model id advertised when the user has no provider configured.
FACADE_MODEL = "night-diary"

#: Upper bound on how long a streaming reply may stall before we close the SSE
#: stream (the pipeline itself is otherwise unbounded).
_STREAM_TIMEOUT_S = 300.0


def _content_to_text(content: str | list[dict[str, Any]] | None) -> str:
    """Flatten an OpenAI message ``content`` into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _last_user_text(messages: list[Any]) -> str:
    """The last non-empty ``user`` turn — the only content 夜记 acts on."""
    for message in reversed(messages):
        if message.role == "user":
            text = _content_to_text(message.content)
            if text.strip():
                return text
    return ""


def _openai_error(
    message: str,
    *,
    status_code: int,
    err_type: str = "invalid_request_error",
    code: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": err_type, "param": None, "code": code}},
    )


def _usage_from(token_info: dict[str, int] | None) -> OpenAIUsage:
    info = token_info or {}
    prompt = int(info.get("prompt_tokens", 0) or 0)
    completion = int(info.get("completion_tokens", 0) or 0)
    total = int(info.get("total_tokens_used", 0) or 0) or (prompt + completion)
    return OpenAIUsage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)


def _resolve_conversation(db: Any, user_id: str, requested_id: str | None) -> Any:
    if requested_id:
        conv = conversation_service.get_conversation(
            db, user_id=user_id, conversation_id=requested_id
        )
        if conv is None:
            raise ConversationNotFoundError(conversation_id=requested_id)
        return conv
    return conversation_service.get_or_create_api_conversation(db, user_id=user_id)


def _chunk(
    completion_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
    usage: OpenAIUsage | None = None,
) -> str:
    payload: dict[str, Any] = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage is not None:
        payload["usage"] = usage.model_dump()
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _stream_response(
    *,
    db: Any,
    container: Any,
    user_id: str,
    conversation_id: str,
    content: str,
    model: str,
    trace_id: str | None,
) -> StreamingResponse:
    async def event_stream() -> Any:
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())
        stream_trace_id = trace_id or uuid.uuid4().hex
        bus = get_event_bus()
        queue = await bus.subscribe(stream_trace_id)
        task = asyncio.create_task(
            conversation_ai_service.generate_reply_streaming(
                db=db,
                container=container,
                conversation_id=conversation_id,
                content=content,
                diary_ids=[],
                user_id=user_id,
                trace_id=stream_trace_id,
            )
        )
        get_task_registry().register(stream_trace_id, task)
        try:
            yield _chunk(completion_id, created, model, {"role": "assistant"})
            usage: OpenAIUsage | None = None
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=_STREAM_TIMEOUT_S)
                event_type = event.get("type")
                if event_type == StreamingEventType.TEXT_DELTA:
                    text = event.get("text") or ""
                    if text:
                        yield _chunk(completion_id, created, model, {"content": text})
                elif event_type == StreamingEventType.RETRACT:
                    # Crisis override: the stream can't un-send prior deltas, so
                    # append the safe replacement (clients see the correction).
                    replacement = event.get("replacement") or ""
                    if replacement:
                        yield _chunk(completion_id, created, model, {"content": replacement})
                elif event_type == StreamingEventType.REPLY_END:
                    usage = _usage_from(event.get("usage") or {})
                    break
            yield _chunk(completion_id, created, model, {}, finish_reason="stop", usage=usage)
            yield "data: [DONE]\n\n"
        except TimeoutError:
            yield _chunk(completion_id, created, model, {}, finish_reason="stop")
            yield "data: [DONE]\n\n"
        finally:
            # Cancel first (synchronous) so a client disconnect never leaves the
            # generation running; then best-effort release the bus subscriber.
            if not task.done():
                task.cancel()
            with contextlib.suppress(Exception):
                await bus.unsubscribe(stream_trace_id, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat/completions")
async def chat_completions(
    body: OpenAIChatCompletionRequest,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
    http_request: Request,
) -> Any:
    user_text = _last_user_text(body.messages)
    if not user_text:
        return _openai_error(
            "messages 必须包含至少一条非空的 user 消息", status_code=400
        )
    if body.n is not None and body.n > 1:
        return _openai_error("暂不支持 n > 1", status_code=400)

    user_id = str(user.id)
    try:
        conv = _resolve_conversation(db, user_id, body.conversation_id)
    except ConversationNotFoundError as exc:
        return _openai_error(exc.message, status_code=404, err_type="invalid_request_error")

    model = body.model or FACADE_MODEL
    trace_id = http_request.headers.get("X-Trace-Id")

    if body.stream:
        return _stream_response(
            db=db,
            container=container,
            user_id=user_id,
            conversation_id=conv.id,
            content=user_text,
            model=model,
            trace_id=trace_id,
        )

    result = await asyncio.to_thread(
        conversation_ai_service.generate_reply,
        db,
        container,
        conversation_id=conv.id,
        content=user_text,
        diary_ids=[],
        user_id=user_id,
        trace_id=trace_id,
    )
    await asyncio.to_thread(
        conversation_service.add_user_message_and_reply,
        db,
        user_id=user_id,
        conversation_id=conv.id,
        content=user_text,
        reply_content=result.reply_text,
        retrieved_diary_ids=result.retrieved_diary_ids,
        retrieved_memory_ids=result.retrieved_memory_ids,
        process_info=result.process_info,
        token_info=result.token_info,
    )
    return OpenAIChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        model=model,
        choices=[
            OpenAIChatChoice(
                index=0,
                message=OpenAIChatMessageOut(content=result.reply_text),
                finish_reason="stop",
            )
        ],
        usage=_usage_from(result.token_info),
    )


@router.get("/models")
def list_models(db: DbDep, user: CurrentUserDep) -> OpenAIModelList:
    """Advertise the user's configured provider names so clients can pick one."""
    ids: list[str] = []
    with contextlib.suppress(Exception):
        for row in model_service.list_models(db, user_id=str(user.id)):
            name = (row.model_name or "").strip()
            if name and name not in ids:
                ids.append(name)
    if not ids:
        ids = [FACADE_MODEL]
    created = int(time.time())
    return OpenAIModelList(data=[OpenAIModelCard(id=name, created=created) for name in ids])