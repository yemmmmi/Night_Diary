"""Memory Library API — views and management of the durable memory layers.

Exposes episodic memory (the event trail, where cards sink) and the
long-term user profile so the desktop app can visualise everything the
agent remembers. Working (session) memory is intentionally not exposed.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import ContainerDep
from app.api.schemas import (
    EpisodicEntryResponse,
    EpisodicEntryUpdateRequest,
    MemoryOverviewResponse,
    UserProfileResponse,
)
from app.services import memory_service

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/episodic", response_model=list[EpisodicEntryResponse])
def list_episodic(container: ContainerDep) -> list[EpisodicEntryResponse]:
    container.ensure_memory()
    return [
        EpisodicEntryResponse.model_validate(entry)
        for entry in memory_service.list_episodic(container)
    ]


@router.patch("/episodic/{entry_id}", response_model=EpisodicEntryResponse)
def update_episodic_entry(
    entry_id: str,
    body: EpisodicEntryUpdateRequest,
    container: ContainerDep,
) -> EpisodicEntryResponse:
    container.ensure_memory()
    updated = memory_service.update_episodic(
        container,
        entry_id,
        event=body.event,
        emotion=body.emotion,
        ai_suggestion=body.ai_suggestion,
        importance=body.importance,
    )
    return EpisodicEntryResponse.model_validate(updated)


@router.delete(
    "/episodic/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_episodic_entry(entry_id: str, container: ContainerDep) -> Response:
    container.ensure_memory()
    memory_service.delete_episodic(container, entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/profile", response_model=UserProfileResponse | None)
def get_profile(container: ContainerDep) -> UserProfileResponse | None:
    container.ensure_memory()
    profile = memory_service.get_profile(container)
    if profile is None:
        return None
    return UserProfileResponse.model_validate(profile)


@router.get("/overview", response_model=MemoryOverviewResponse)
def get_overview(container: ContainerDep) -> MemoryOverviewResponse:
    container.ensure_memory()
    return MemoryOverviewResponse.model_validate(memory_service.get_overview(container))
