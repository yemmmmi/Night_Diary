"""记忆库 API —— 持久记忆层的视图与管理。

暴露情景记忆（事件轨迹，卡片沉淀之处）和长期用户画像，
以便桌面应用能够可视化智能体记住的一切。工作（会话）记忆有意不予暴露。
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import ContainerDep, CurrentUserDep
from app.api.schemas import (
    EpisodicEntryResponse,
    EpisodicEntryUpdateRequest,
    MemoryOverviewResponse,
    UserProfileResponse,
)
from app.services import memory_service

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/episodic", response_model=list[EpisodicEntryResponse])
def list_episodic(container: ContainerDep, user: CurrentUserDep) -> list[EpisodicEntryResponse]:
    container.ensure_memory(user_id=str(user.id))
    return [
        EpisodicEntryResponse.model_validate(entry)
        for entry in memory_service.list_episodic(container, user_id=str(user.id))
    ]


@router.patch("/episodic/{entry_id}", response_model=EpisodicEntryResponse)
def update_episodic_entry(
    entry_id: str,
    body: EpisodicEntryUpdateRequest,
    container: ContainerDep,
    user: CurrentUserDep,
) -> EpisodicEntryResponse:
    container.ensure_memory(user_id=str(user.id))
    updated = memory_service.update_episodic(
        container,
        entry_id,
        event_summary=body.event_summary,
        emotion=body.emotion,
        reply_insight=body.reply_insight,
        importance=body.importance,
        user_id=str(user.id),
    )
    return EpisodicEntryResponse.model_validate(updated)


@router.delete(
    "/episodic/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_episodic_entry(entry_id: str, container: ContainerDep, user: CurrentUserDep) -> Response:
    container.ensure_memory(user_id=str(user.id))
    memory_service.delete_episodic(container, entry_id, user_id=str(user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/profile", response_model=UserProfileResponse | None)
def get_profile(container: ContainerDep, user: CurrentUserDep) -> UserProfileResponse | None:
    container.ensure_memory(user_id=str(user.id))
    profile = memory_service.get_profile(container, user_id=str(user.id))
    if profile is None:
        return None
    return UserProfileResponse.model_validate(profile)


@router.get("/overview", response_model=MemoryOverviewResponse)
def get_overview(container: ContainerDep, user: CurrentUserDep) -> MemoryOverviewResponse:
    container.ensure_memory(user_id=str(user.id))
    return MemoryOverviewResponse.model_validate(
        memory_service.get_overview(container, user_id=str(user.id))
    )
