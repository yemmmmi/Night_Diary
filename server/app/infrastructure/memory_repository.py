"""SQLite-backed repositories for domain memory stores."""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.domain.memory.types import EpisodicEntry, UserProfile
from app.infrastructure.models.memory import (
    EpisodicMemoryRow,
    LongTermProfileRow,
    UserAboutRow,
)
from app.infrastructure.models.profile_change_log import ProfileChangeLogRow


class SqliteEpisodicMemoryStore:
    """Persist episodic entries in SQLite."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def load_entries(
        self, user_id: str, *, include_superseded: bool = False
    ) -> list[EpisodicEntry]:
        """Load a user's entries, by default excluding soft-superseded ones.

        Superseded entries (P2-B) carry a ``superseded_by`` pointer to the
        newer memory that replaced them; they must stay out of retrieval
        and long-term promotion, but remain in storage for audit.
        """
        with self._session_factory() as session:
            rows = (
                session.query(EpisodicMemoryRow)
                .filter(EpisodicMemoryRow.user_id == user_id)
                .order_by(EpisodicMemoryRow.timestamp.asc())
                .all()
            )
            entries = [EpisodicEntry.model_validate_json(row.payload_json) for row in rows]
            if include_superseded:
                return entries
            return [entry for entry in entries if entry.superseded_by is None]

    def get_entry(self, user_id: str, entry_id: str) -> EpisodicEntry | None:
        with self._session_factory() as session:
            row = session.get(EpisodicMemoryRow, entry_id)
            if row is None or row.user_id != user_id:
                return None
            return EpisodicEntry.model_validate_json(row.payload_json)

    def upsert_entry(self, user_id: str, entry: EpisodicEntry) -> None:
        with self._session_factory() as session:
            row = session.get(EpisodicMemoryRow, entry.entry_id)
            payload = entry.model_dump_json()
            if row is None:
                session.add(
                    EpisodicMemoryRow(
                        entry_id=entry.entry_id,
                        user_id=user_id,
                        timestamp=entry.timestamp,
                        importance=entry.importance,
                        payload_json=payload,
                    )
                )
            else:
                row.user_id = user_id
                row.timestamp = entry.timestamp
                row.importance = entry.importance
                row.payload_json = payload
            session.commit()

    def delete_entries(self, user_id: str, entry_ids: list[str]) -> None:
        if not entry_ids:
            return
        with self._session_factory() as session:
            (
                session.query(EpisodicMemoryRow)
                .filter(
                    EpisodicMemoryRow.user_id == user_id,
                    EpisodicMemoryRow.entry_id.in_(entry_ids),
                )
                .delete(synchronize_session=False)
            )
            session.commit()


class SqliteLongTermProfileStore:
    """Persist long-term profiles as JSON blobs."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_profile(self, user_id: str) -> UserProfile | None:
        with self._session_factory() as session:
            row = session.get(LongTermProfileRow, user_id)
            if row is None:
                return None
            return UserProfile.model_validate_json(row.profile_json)

    def save_profile(self, user_id: str, profile: UserProfile) -> None:
        with self._session_factory() as session:
            row = session.get(LongTermProfileRow, user_id)
            payload = profile.model_dump_json()
            now = time.time()
            if row is None:
                session.add(
                    LongTermProfileRow(
                        user_id=user_id,
                        profile_json=payload,
                        updated_at=now,
                    )
                )
            else:
                row.profile_json = payload
                row.updated_at = now
            session.commit()


class SqliteProfileChangeLogStore:
    """Persist field-level profile changes to ``profile_change_log`` (P1-B)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _dump_value(value: Any) -> str | None:
        """Serialize an audit value (None stays NULL, strings pass through)."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)

    def record_change(
        self,
        user_id: str,
        *,
        field: str,
        old_value: Any,
        new_value: Any,
        source: str,
        evidence: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._session_factory() as session:
            session.add(
                ProfileChangeLogRow(
                    user_id=user_id,
                    field=field,
                    old_value=self._dump_value(old_value),
                    new_value=self._dump_value(new_value),
                    source=source,
                    evidence_json=(
                        json.dumps(evidence, ensure_ascii=False, default=str)
                        if evidence
                        else None
                    ),
                )
            )
            session.commit()


class SqliteUserAboutStore:
    """Persist the user-authored 「关于我」 text (B2)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_about(self, user_id: str) -> tuple[str, float] | None:
        """Return ``(content, updated_at)`` or ``None`` when never saved."""
        with self._session_factory() as session:
            row = session.get(UserAboutRow, user_id)
            if row is None:
                return None
            return row.content or "", row.updated_at or 0.0

    def save_about(self, user_id: str, content: str) -> float:
        """Upsert the about text, returning the new ``updated_at`` timestamp."""
        now = time.time()
        with self._session_factory() as session:
            row = session.get(UserAboutRow, user_id)
            if row is None:
                session.add(UserAboutRow(user_id=user_id, content=content, updated_at=now))
            else:
                row.content = content
                row.updated_at = now
            session.commit()
        return now
