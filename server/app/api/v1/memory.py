"""Memory Library API — read-only views over the durable memory layers.

Exposes episodic memory (the event trail, where cards sink) and the
long-term user profile so the desktop app can visualise everything the
agent remembers. Working (session) memory is intentionally not exposed.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.api.schemas import (
    EpisodicEntryResponse,
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
