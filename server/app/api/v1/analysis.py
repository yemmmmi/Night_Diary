"""Analysis API routes."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Request, Response, status

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
from app.api.mappers import analysis_to_response
from app.api.schemas import AnalysisResponse, AnalysisTriggerRequest
from app.config import get_settings
from app.domain.agents.prompts import build_style_fragment
from app.services import analysis_service, diary_service
from app.shared.errors import AnalysisNotFoundError
from app.shared.task_registry import get_task_registry

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/{diary_id}", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
def trigger_analysis(
    diary_id: int,
    db: DbDep,
    container: ContainerDep,
    user: CurrentUserDep,
    http_request: Request,
    request: AnalysisTriggerRequest | None = None,
) -> AnalysisResponse:
    req = request or AnalysisTriggerRequest()
    style_fragment = build_style_fragment(req.replier_preset, req.replier_persona)
    trace_id = http_request.headers.get("X-Trace-Id")
    row, mem_count = analysis_service.trigger_analysis(
        db,
        diary_id,
        container,
        user_id=str(user.id),
        style_fragment=style_fragment,
        trace_id=trace_id,
    )
    entry = diary_service.get_entry(db, diary_id, user_id=str(user.id))
    return analysis_to_response(
        row,
        reply=entry.reply,
        db=db,
        referenced_memory_count=mem_count,
        user_id=str(user.id),
    )


@router.post("/{diary_id}/regenerate", response_model=AnalysisResponse)
def regenerate_analysis(
    diary_id: int,
    db: DbDep,
    container: ContainerDep,
    user: CurrentUserDep,
    request: AnalysisTriggerRequest | None = None,
) -> AnalysisResponse:
    req = request or AnalysisTriggerRequest()
    style_fragment = build_style_fragment(req.replier_preset, req.replier_persona)
    row, mem_count = analysis_service.regenerate_analysis(
        db, diary_id, container, user_id=str(user.id), style_fragment=style_fragment
    )
    entry = diary_service.get_entry(db, diary_id, user_id=str(user.id))
    return analysis_to_response(
        row,
        reply=entry.reply,
        db=db,
        referenced_memory_count=mem_count,
        user_id=str(user.id),
    )


@router.get("/{diary_id}", response_model=AnalysisResponse)
def get_analysis(diary_id: int, db: DbDep, user: CurrentUserDep) -> AnalysisResponse:
    row = analysis_service.get_analysis(db, diary_id, user_id=str(user.id))
    entry = diary_service.get_entry(db, diary_id, user_id=str(user.id))
    return analysis_to_response(
        row,
        reply=entry.reply,
        db=db,
        user_id=str(user.id),
    )


@router.delete("/{diary_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_analysis(diary_id: int, db: DbDep, user: CurrentUserDep) -> Response:
    if not analysis_service.delete_analysis_for_diary(db, diary_id, user_id=str(user.id)):
        raise AnalysisNotFoundError(diary_id=diary_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── V3 P4: scene-1 streaming SSE endpoint ───────────────────────────


@router.post(
    "/{diary_id}/stream",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def trigger_analysis_stream(
    diary_id: int,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
    http_request: Request,
) -> dict[str, Any]:
    """Streaming endpoint - returns ``trace_id`` immediately.

    Content streams via SSE at ``/api/v1/dev/traces/{trace_id}/stream``.

    This mirrors the scene-2 conversation streaming endpoint
    (:http:post:`/conversations/{id}/messages/stream`) so the frontend can
    reuse the same subscription logic.

    When ``STREAMING_ENABLED=false`` (the default), this endpoint returns
    ``{"streaming": False, "trace_id": ""}`` so the frontend can fall back
    to the synchronous :http:post:`/analysis/{diary_id}` endpoint.

    When ``STREAMING_ENABLED=true``, it launches
    :func:`analysis_service.trigger_analysis_streaming` as a background
    task and returns a ``trace_id`` that the frontend subscribes to for
    SSE events.
    """
    settings = get_settings()
    trace_id = http_request.headers.get("X-Trace-Id") or str(uuid.uuid4())

    # Validate ownership/existence up-front (raises 404 if missing),
    # mirroring how the scene-2 endpoint checks the conversation exists
    # before launching the background task.
    diary_service.get_entry(db, diary_id, user_id=str(user.id))

    if not settings.streaming_enabled:
        # Fallback: tell the frontend to use the synchronous endpoint.
        return {"streaming": False, "trace_id": ""}

    # Launch streaming analysis as a background task so this endpoint
    # returns immediately. The frontend subscribes to the trace_id SSE
    # stream to receive TEXT_DELTA / REPLY_END events.
    task = asyncio.create_task(
        analysis_service.trigger_analysis_streaming(
            db=db,
            container=container,
            diary_id=diary_id,
            user_id=str(user.id),
            trace_id=trace_id,
        )
    )
    # Register with TaskRegistry for lifecycle management (cancel on abort,
    # auto-cleanup on done, cancel_all on shutdown).
    get_task_registry().register(trace_id, task)

    return {"streaming": True, "trace_id": trace_id}


@router.post(
    "/abort/{trace_id}",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def abort_analysis_stream(trace_id: str, user: CurrentUserDep) -> dict[str, Any]:
    """Abort a streaming analysis by ``trace_id``.

    Returns ``{"cancelled": bool}`` indicating whether a live task was
    found and cancelled, matching the scene-2 abort contract so the
    frontend can reuse the same handling. The cancelled task's
    ``trigger_analysis_streaming`` finally-block still emits
    ``REPLY_END(error="cancelled")`` so the frontend can exit the
    streaming state cleanly.
    """
    cancelled = await get_task_registry().cancel(trace_id)
    return {"cancelled": cancelled}
