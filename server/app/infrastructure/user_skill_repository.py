"""Persistence for user-defined custom skills (A2).

:class:`SqliteUserSkillStore` owns the ``user_skills`` / ``user_skill_versions``
tables. Updates are versioned: the *previous* revision is snapshotted into
``user_skill_versions`` before the live row is mutated, so history is never lost.
"""

from __future__ import annotations

import json
import time

from sqlalchemy.orm import Session, sessionmaker

from app.domain.skills.custom_skill import (
    CustomSkillDefinition,
    normalize_triggers,
)
from app.infrastructure.models.user_skill import UserSkillRow, UserSkillVersionRow


def _row_to_definition(row: UserSkillRow) -> CustomSkillDefinition:
    try:
        triggers = tuple(str(t) for t in json.loads(row.triggers_json or "[]"))
    except (ValueError, TypeError):
        triggers = ()
    return CustomSkillDefinition(
        skill_id=int(row.id),
        user_id=row.user_id,
        name=row.name or "",
        description=row.description or "",
        triggers=triggers,
        instruction=row.instruction or "",
        enabled=bool(row.enabled),
        version=int(row.version or 1),
        created_at=float(row.created_at or 0.0),
        updated_at=float(row.updated_at or 0.0),
    )


class SqliteUserSkillStore:
    """CRUD + version history for user-authored custom skills."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_skills(self, user_id: str) -> list[CustomSkillDefinition]:
        with self._session_factory() as session:
            rows = (
                session.query(UserSkillRow)
                .filter(UserSkillRow.user_id == user_id)
                .order_by(UserSkillRow.created_at.asc(), UserSkillRow.id.asc())
                .all()
            )
            return [_row_to_definition(row) for row in rows]

    def list_enabled(self, user_id: str) -> list[CustomSkillDefinition]:
        with self._session_factory() as session:
            rows = (
                session.query(UserSkillRow)
                .filter(UserSkillRow.user_id == user_id, UserSkillRow.enabled.is_(True))
                .order_by(UserSkillRow.created_at.asc(), UserSkillRow.id.asc())
                .all()
            )
            return [_row_to_definition(row) for row in rows]

    def get_skill(self, user_id: str, skill_id: int) -> CustomSkillDefinition | None:
        with self._session_factory() as session:
            row = (
                session.query(UserSkillRow)
                .filter(UserSkillRow.user_id == user_id, UserSkillRow.id == skill_id)
                .one_or_none()
            )
            return _row_to_definition(row) if row is not None else None

    def create(
        self,
        user_id: str,
        *,
        name: str,
        description: str,
        triggers: list[str] | tuple[str, ...],
        instruction: str,
        enabled: bool = True,
    ) -> CustomSkillDefinition:
        now = time.time()
        triggers_tuple = normalize_triggers(triggers)
        with self._session_factory() as session:
            row = UserSkillRow(
                user_id=user_id,
                name=name,
                description=description,
                triggers_json=json.dumps(list(triggers_tuple), ensure_ascii=False),
                instruction=instruction,
                enabled=enabled,
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _row_to_definition(row)

    def update(
        self,
        user_id: str,
        skill_id: int,
        *,
        name: str,
        description: str,
        triggers: list[str] | tuple[str, ...],
        instruction: str,
        enabled: bool | None = None,
    ) -> CustomSkillDefinition | None:
        """Mutate a skill, snapshotting the previous revision first."""
        now = time.time()
        triggers_tuple = normalize_triggers(triggers)
        with self._session_factory() as session:
            row = (
                session.query(UserSkillRow)
                .filter(UserSkillRow.user_id == user_id, UserSkillRow.id == skill_id)
                .one_or_none()
            )
            if row is None:
                return None

            session.add(
                UserSkillVersionRow(
                    skill_id=int(row.id),
                    user_id=row.user_id,
                    version=int(row.version or 1),
                    name=row.name or "",
                    description=row.description or "",
                    triggers_json=row.triggers_json or "[]",
                    instruction=row.instruction or "",
                    enabled=bool(row.enabled),
                    created_at=now,
                )
            )

            row.name = name
            row.description = description
            row.triggers_json = json.dumps(list(triggers_tuple), ensure_ascii=False)
            row.instruction = instruction
            if enabled is not None:
                row.enabled = enabled
            row.version = int(row.version or 1) + 1
            row.updated_at = now
            session.commit()
            session.refresh(row)
            return _row_to_definition(row)

    def set_enabled(self, user_id: str, skill_id: int, enabled: bool) -> CustomSkillDefinition | None:
        """Toggle a skill without bumping its version (no content change)."""
        with self._session_factory() as session:
            row = (
                session.query(UserSkillRow)
                .filter(UserSkillRow.user_id == user_id, UserSkillRow.id == skill_id)
                .one_or_none()
            )
            if row is None:
                return None
            row.enabled = enabled
            row.updated_at = time.time()
            session.commit()
            session.refresh(row)
            return _row_to_definition(row)

    def delete(self, user_id: str, skill_id: int) -> bool:
        with self._session_factory() as session:
            row = (
                session.query(UserSkillRow)
                .filter(UserSkillRow.user_id == user_id, UserSkillRow.id == skill_id)
                .one_or_none()
            )
            if row is None:
                return False
            session.query(UserSkillVersionRow).filter(
                UserSkillVersionRow.skill_id == skill_id,
                UserSkillVersionRow.user_id == user_id,
            ).delete()
            session.delete(row)
            session.commit()
            return True

    def list_versions(self, user_id: str, skill_id: int) -> list[dict[str, object]]:
        """Return prior revisions, newest first (excludes the live revision)."""
        with self._session_factory() as session:
            rows = (
                session.query(UserSkillVersionRow)
                .filter(
                    UserSkillVersionRow.user_id == user_id,
                    UserSkillVersionRow.skill_id == skill_id,
                )
                .order_by(UserSkillVersionRow.version.desc(), UserSkillVersionRow.id.desc())
                .all()
            )
            return [
                {
                    "version": int(row.version or 1),
                    "name": row.name or "",
                    "description": row.description or "",
                    "triggers": _decode_triggers(row.triggers_json),
                    "instruction": row.instruction or "",
                    "enabled": bool(row.enabled),
                    "created_at": float(row.created_at or 0.0),
                }
                for row in rows
            ]


def _decode_triggers(raw: str | None) -> list[str]:
    try:
        return [str(t) for t in json.loads(raw or "[]")]
    except (ValueError, TypeError):
        return []