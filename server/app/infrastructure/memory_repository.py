"""SQLite-backed repositories for domain memory stores."""

from __future__ import annotations

import time

from sqlalchemy.orm import Session, sessionmaker

from app.domain.memory.types import EpisodicEntry, UserProfile
from app.infrastructure.models.memory import EpisodicMemoryRow, LongTermProfileRow


class SqliteEpisodicMemoryStore:
    """Persist episodic entries in SQLite."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def load_entries(self, user_id: str) -> list[EpisodicEntry]:
        with self._session_factory() as session:
            rows = (
                session.query(EpisodicMemoryRow)
                .filter(EpisodicMemoryRow.user_id == user_id)
                .order_by(EpisodicMemoryRow.timestamp.asc())
                .all()
            )
            return [EpisodicEntry.model_validate_json(row.payload_json) for row in rows]

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
