"""Custom-skill service (A2) — user-authored reply-shaping advisories.

This is the CRUD + reply-injection layer for :mod:`app.domain.skills.custom_skill`.
Unlike the built-in skills (记录 / 洞悉 / 计划), a custom skill is authored by the
user in settings, reviewed for safety on every write, and loaded **read-only**
at reply time. The agent has no tool that can create or edit one, so the
「提案-确认、Agent 零写权限」 invariant holds.

Two responsibilities:

* **Management** — :func:`create_skill` / :func:`update_skill` gate every write
  through :func:`review_custom_skill` and reject anything that tries to override
  the tone baseline, coerce the user, disable the crisis mechanism, or run
  tools/writes. Rejected writes raise :class:`ValidationError` with the exact
  reasons.
* **Injection** — :func:`build_custom_skill_block` returns the volatile block
  appended to the reply prompt *only* when one of the user's enabled skills has
  a trigger that occurs in the current message. The block is budget-capped and
  best-effort: a failure here degrades to no block and never breaks a reply.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.domain.skills.custom_skill import (
    MAX_BLOCK_CHARS,
    MAX_MATCHED_SKILLS,
    CustomSkillDefinition,
    match_triggers,
    review_custom_skill,
)
from app.infrastructure.user_skill_repository import SqliteUserSkillStore
from app.shared.errors import NotFoundError, ValidationError

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

DEFAULT_USER_ID = "default"

#: Header for the injected block; the wording stresses that the global tone and
#: safety baseline still win, so a custom skill is an *advisory*, not a reset.
_BLOCK_HEADER = "## 用户自定义回信偏好（本轮命中）"
_BLOCK_FOOTER = "以上是用户为这类话题设置的偏好，请在不违背全局语气与安全底线的前提下参考。"


def _store(container: ServiceContainer) -> SqliteUserSkillStore:
    return SqliteUserSkillStore(container.session_factory)


def _to_dict(definition: CustomSkillDefinition) -> dict[str, Any]:
    return {
        "id": definition.skill_id,
        "name": definition.name,
        "description": definition.description,
        "triggers": list(definition.triggers),
        "instruction": definition.instruction,
        "enabled": definition.enabled,
        "version": definition.version,
        "created_at": definition.created_at,
        "updated_at": definition.updated_at,
    }


def list_skills(container: ServiceContainer, *, user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    """Return the user's custom skills, oldest first."""
    return [_to_dict(d) for d in _store(container).list_skills(user_id)]


def get_skill(
    container: ServiceContainer, skill_id: int, *, user_id: str = DEFAULT_USER_ID
) -> dict[str, Any]:
    definition = _store(container).get_skill(user_id, skill_id)
    if definition is None:
        raise NotFoundError(resource="自定义技能", resource_id=skill_id)
    return _to_dict(definition)


def _review_or_raise(
    *, name: str, description: str, triggers: list[str], instruction: str
) -> None:
    result = review_custom_skill(
        name=name, description=description, triggers=triggers, instruction=instruction
    )
    if not result.ok:
        detail = "；".join(v.message for v in result.violations)
        raise ValidationError(f"自定义技能未通过安全审查：{detail}")


def create_skill(
    container: ServiceContainer,
    *,
    user_id: str = DEFAULT_USER_ID,
    name: str,
    description: str = "",
    triggers: list[str],
    instruction: str,
    enabled: bool = True,
) -> dict[str, Any]:
    """Create a custom skill after safety review."""
    _review_or_raise(name=name, description=description, triggers=triggers, instruction=instruction)
    definition = _store(container).create(
        user_id,
        name=name.strip(),
        description=description.strip(),
        triggers=triggers,
        instruction=instruction.strip(),
        enabled=enabled,
    )
    return _to_dict(definition)


def update_skill(
    container: ServiceContainer,
    skill_id: int,
    *,
    user_id: str = DEFAULT_USER_ID,
    name: str,
    description: str = "",
    triggers: list[str],
    instruction: str,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Update a custom skill after safety review; snapshots the prior revision."""
    _review_or_raise(name=name, description=description, triggers=triggers, instruction=instruction)
    definition = _store(container).update(
        user_id,
        skill_id,
        name=name.strip(),
        description=description.strip(),
        triggers=triggers,
        instruction=instruction.strip(),
        enabled=enabled,
    )
    if definition is None:
        raise NotFoundError(resource="自定义技能", resource_id=skill_id)
    return _to_dict(definition)


def set_enabled(
    container: ServiceContainer, skill_id: int, *, user_id: str = DEFAULT_USER_ID, enabled: bool
) -> dict[str, Any]:
    """Toggle a skill's enabled flag (no content change, no version bump)."""
    definition = _store(container).set_enabled(user_id, skill_id, enabled)
    if definition is None:
        raise NotFoundError(resource="自定义技能", resource_id=skill_id)
    return _to_dict(definition)


def delete_skill(
    container: ServiceContainer, skill_id: int, *, user_id: str = DEFAULT_USER_ID
) -> None:
    if not _store(container).delete(user_id, skill_id):
        raise NotFoundError(resource="自定义技能", resource_id=skill_id)


def list_versions(
    container: ServiceContainer, skill_id: int, *, user_id: str = DEFAULT_USER_ID
) -> list[dict[str, Any]]:
    """Return prior revisions (newest first) of a custom skill."""
    if _store(container).get_skill(user_id, skill_id) is None:
        raise NotFoundError(resource="自定义技能", resource_id=skill_id)
    return _store(container).list_versions(user_id, skill_id)


def build_block_from_definitions(
    definitions: list[CustomSkillDefinition],
    content: str,
    *,
    max_matched: int = MAX_MATCHED_SKILLS,
    max_chars: int = MAX_BLOCK_CHARS,
) -> str:
    """Build the injected block from already-loaded definitions (pure).

    Only *enabled* skills whose triggers occur in *content* are considered; at
    most *max_matched* are used, and the whole block is truncated to *max_chars*
    so it can never bloat the prompt. Returns ``""`` when nothing matches.
    """
    matched = [
        d
        for d in definitions
        if d.enabled and d.instruction.strip() and match_triggers(d.triggers, content)
    ]
    if not matched:
        return ""
    matched = matched[:max_matched]

    lines = [_BLOCK_HEADER]
    for d in matched:
        label = d.name.strip() or "自定义技能"
        lines.append(f"- 「{label}」：{d.instruction.strip()}")
    lines.append(_BLOCK_FOOTER)

    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[: max(0, max_chars - 1)].rstrip() + "…"
    return block


def build_custom_skill_block(
    container: ServiceContainer, *, user_id: str = DEFAULT_USER_ID, content: str
) -> str:
    """Load the user's enabled skills and build the volatile reply block.

    Best-effort: any storage failure returns ``""`` so reply generation is never
    interrupted by a custom-skill problem.
    """
    try:
        definitions = _store(container).list_enabled(user_id)
    except Exception:
        return ""
    return build_block_from_definitions(definitions, content)


__all__ = [
    "build_block_from_definitions",
    "build_custom_skill_block",
    "create_skill",
    "delete_skill",
    "get_skill",
    "list_skills",
    "list_versions",
    "set_enabled",
    "update_skill",
]