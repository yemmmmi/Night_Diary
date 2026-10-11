"""Custom-skill REST API (A2).

User-authored, safety-reviewed reply-shaping advisories. All routes require
auth and scope to the current user via the service layer. The agent has no tool
that can create or edit a custom skill — these endpoints are the only write
path, keeping the 「提案-确认、Agent 零写权限」 invariant intact.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import ContainerDep, CurrentUserDep
from app.api.schemas import (
    CustomSkillCreateRequest,
    CustomSkillResponse,
    CustomSkillToggleRequest,
    CustomSkillUpdateRequest,
    CustomSkillVersionResponse,
)
from app.services import custom_skill_service as svc

router = APIRouter(prefix="/custom-skills", tags=["custom-skill"])


@router.get("", response_model=list[CustomSkillResponse])
def list_custom_skills(
    container: ContainerDep, user: CurrentUserDep
) -> list[CustomSkillResponse]:
    return [
        CustomSkillResponse.model_validate(s)
        for s in svc.list_skills(container, user_id=str(user.id))
    ]


@router.post("", response_model=CustomSkillResponse, status_code=status.HTTP_201_CREATED)
def create_custom_skill(
    body: CustomSkillCreateRequest, container: ContainerDep, user: CurrentUserDep
) -> CustomSkillResponse:
    data = svc.create_skill(
        container,
        user_id=str(user.id),
        name=body.name,
        description=body.description,
        triggers=body.triggers,
        instruction=body.instruction,
        enabled=body.enabled,
    )
    return CustomSkillResponse.model_validate(data)


@router.get("/{skill_id}", response_model=CustomSkillResponse)
def get_custom_skill(
    skill_id: int, container: ContainerDep, user: CurrentUserDep
) -> CustomSkillResponse:
    return CustomSkillResponse.model_validate(
        svc.get_skill(container, skill_id, user_id=str(user.id))
    )


@router.patch("/{skill_id}", response_model=CustomSkillResponse)
def update_custom_skill(
    skill_id: int,
    body: CustomSkillUpdateRequest,
    container: ContainerDep,
    user: CurrentUserDep,
) -> CustomSkillResponse:
    data = svc.update_skill(
        container,
        skill_id,
        user_id=str(user.id),
        name=body.name,
        description=body.description,
        triggers=body.triggers,
        instruction=body.instruction,
        enabled=body.enabled,
    )
    return CustomSkillResponse.model_validate(data)


@router.patch("/{skill_id}/enabled", response_model=CustomSkillResponse)
def toggle_custom_skill(
    skill_id: int,
    body: CustomSkillToggleRequest,
    container: ContainerDep,
    user: CurrentUserDep,
) -> CustomSkillResponse:
    """Enable/disable a skill without editing its content."""
    return CustomSkillResponse.model_validate(
        svc.set_enabled(container, skill_id, user_id=str(user.id), enabled=body.enabled)
    )


@router.delete(
    "/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_custom_skill(
    skill_id: int, container: ContainerDep, user: CurrentUserDep
) -> Response:
    svc.delete_skill(container, skill_id, user_id=str(user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{skill_id}/versions", response_model=list[CustomSkillVersionResponse])
def list_custom_skill_versions(
    skill_id: int, container: ContainerDep, user: CurrentUserDep
) -> list[CustomSkillVersionResponse]:
    """Prior revisions of a skill, newest first (history is append-only)."""
    return [
        CustomSkillVersionResponse.model_validate(v)
        for v in svc.list_versions(container, skill_id, user_id=str(user.id))
    ]