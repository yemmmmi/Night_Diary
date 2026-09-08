"""Skill discovery routes — the /skills listing for the TRAE-style picker."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUserDep
from app.domain.skills.user_skill_registry import get_user_skill_registry

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("")
def list_skills(user: CurrentUserDep) -> dict[str, Any]:
    """Discoverable user skills: id / label / description."""
    return {"items": get_user_skill_registry().listing()}
