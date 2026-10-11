"""User-facing skill registry — declarative, discoverable, extensible.

TRAE-style skill system: every user-callable skill registers an identity
spec (id / label / description) plus a unified run adapter. Dispatch,
request validation, and the ``GET /api/v1/skills`` discovery endpoint all
read from this single registry — adding a skill is one spec + one
``register()`` call; no dispatch branches or whitelists to edit elsewhere.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.domain.skills.record_skill import SkillRunOutcome
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UserSkillSpec:
    """Declarative identity of one user-callable skill.

    ``doc_path`` names the SKILL.md file (relative to
    :data:`app.domain.skills.skill_loader.USER_SKILL_DOCS_DIR`) that carries the
    skill's Level-1 disclosure body; ``token_cost`` is the estimated cost of
    loading it, surfaced in the Level-0 catalog.
    """

    id: str
    label: str
    description: str
    sort: int = 0
    doc_path: str = ""
    token_cost: int = 0


#: Unified adapter signature: (db, *, llm, content, user_id, conversation_id, container).
#: Each adapter maps the shared call onto its skill's native ``run``.
UserSkillRun = Callable[..., Any]


class UserSkillRegistry:
    """Registry of user-callable skills (记录 / 洞悉 / 计划 / …)."""

    def __init__(self) -> None:
        self._specs: dict[str, UserSkillSpec] = {}
        self._runs: dict[str, UserSkillRun] = {}

    def register(self, spec: UserSkillSpec, run: UserSkillRun) -> None:
        if spec.id in self._specs:
            logger.warning("User skill '%s' already registered; overwriting", spec.id)
        self._specs[spec.id] = spec
        self._runs[spec.id] = run
        logger.info("User skill registered: id=%s label=%s", spec.id, spec.label)

    def has(self, skill_id: str) -> bool:
        return skill_id in self._specs

    def spec(self, skill_id: str) -> UserSkillSpec | None:
        return self._specs.get(skill_id)

    def specs(self) -> list[UserSkillSpec]:
        """All specs in display order (used by progressive disclosure)."""
        return self._sorted()

    def ids(self) -> list[str]:
        return [spec.id for spec in self._sorted()]

    def labels(self) -> list[str]:
        return [spec.label for spec in self._sorted()]

    def listing(self) -> list[dict[str, Any]]:
        """Discovery payload for ``GET /api/v1/skills``."""
        return [
            {"id": spec.id, "label": spec.label, "description": spec.description}
            for spec in self._sorted()
        ]

    def run(
        self,
        db: Session,
        container: ServiceContainer,
        llm: Any,
        *,
        skill_id: str,
        content: str,
        user_id: str,
        conversation_id: str,
        skill_doc: str = "",
    ) -> SkillRunOutcome | None:
        """Dispatch one skill via its registered adapter.

        *skill_doc* is the skill's Level-1 disclosure body (SKILL.md) loaded
        on demand by the caller; adapters forward it so the skill can ground
        its generation in the documented contract.
        """
        run = self._runs.get(skill_id)
        if run is None:
            return None
        outcome: SkillRunOutcome | None = run(
            db,
            llm=llm,
            content=content,
            user_id=user_id,
            conversation_id=conversation_id,
            container=container,
            skill_doc=skill_doc,
        )
        return outcome

    def _sorted(self) -> list[UserSkillSpec]:
        return sorted(self._specs.values(), key=lambda spec: (spec.sort, spec.id))


def create_user_skill_registry() -> UserSkillRegistry:
    """Factory: register the built-in skills. New skills plug in here."""

    def _run_record(
        db: Session,
        *,
        llm: Any,
        content: str,
        user_id: str,
        conversation_id: str,
        container: ServiceContainer,
        skill_doc: str = "",
    ) -> Any:
        from app.domain.skills import record_skill

        return record_skill.run(
            db,
            llm=llm,
            content=content,
            user_id=user_id,
            conversation_id=conversation_id,
            collection_manager=container.diary_collection,
            container=container,
            skill_doc=skill_doc,
        )

    def _run_insight(
        db: Session,
        *,
        llm: Any,
        content: str,
        user_id: str,
        conversation_id: str,
        container: ServiceContainer,
        skill_doc: str = "",
    ) -> Any:
        from app.domain.skills import insight_skill

        return insight_skill.run(
            db,
            llm=llm,
            content=content,
            user_id=user_id,
            conversation_id=conversation_id,
            skill_doc=skill_doc,
        )

    def _run_plan(
        db: Session,
        *,
        llm: Any,
        content: str,
        user_id: str,
        conversation_id: str,
        container: ServiceContainer,
        skill_doc: str = "",
    ) -> Any:
        from app.domain.skills import plan_skill

        return plan_skill.run(
            db,
            llm=llm,
            content=content,
            user_id=user_id,
            conversation_id=conversation_id,
            skill_doc=skill_doc,
        )

    registry = UserSkillRegistry()
    registry.register(
        UserSkillSpec(
            id="record",
            label="记录",
            description="把这封信转写成一篇日记",
            sort=1,
            doc_path="record.md",
            token_cost=180,
        ),
        _run_record,
    )
    registry.register(
        UserSkillSpec(
            id="insight",
            label="洞悉",
            description="以心理视角分析这封信",
            sort=2,
            doc_path="insight.md",
            token_cost=220,
        ),
        _run_insight,
    )
    registry.register(
        UserSkillSpec(
            id="plan",
            label="计划",
            description="把这封信整理成一个计划",
            sort=3,
            doc_path="plan.md",
            token_cost=200,
        ),
        _run_plan,
    )
    return registry


_registry: UserSkillRegistry | None = None


def get_user_skill_registry() -> UserSkillRegistry:
    """Process-wide singleton (registry contents are static after startup)."""
    global _registry
    if _registry is None:
        _registry = create_user_skill_registry()
    return _registry
