"""SQLite-backed repository for style preference records."""

from __future__ import annotations

import time

from sqlalchemy.orm import Session, sessionmaker

from app.domain.feedback.types import StylePreferenceRecord
from app.infrastructure.models.feedback import StylePreferenceRow


class SqliteStylePreferenceStore:
    """Persist Thompson Sampling Beta parameters in SQLite."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_preferences(self, user_id: str) -> list[StylePreferenceRecord]:
        with self._session_factory() as session:
            rows = (
                session.query(StylePreferenceRow)
                .filter(StylePreferenceRow.user_id == user_id)
                .all()
            )
            return [
                StylePreferenceRecord(
                    style=row.style,
                    alpha=row.alpha,
                    beta=row.beta,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    def ensure_preferences(self, user_id: str, styles: list[str]) -> list[StylePreferenceRecord]:
        with self._session_factory() as session:
            rows = (
                session.query(StylePreferenceRow)
                .filter(StylePreferenceRow.user_id == user_id)
                .all()
            )
            existing = {row.style for row in rows}
            now = time.time()
            for style in styles:
                if style not in existing:
                    session.add(
                        StylePreferenceRow(
                            user_id=user_id,
                            style=style,
                            alpha=1.0,
                            beta=1.0,
                            updated_at=now,
                        )
                    )
            if len(existing) < len(styles):
                session.commit()
                rows = (
                    session.query(StylePreferenceRow)
                    .filter(StylePreferenceRow.user_id == user_id)
                    .all()
                )
            return [
                StylePreferenceRecord(
                    style=row.style,
                    alpha=row.alpha,
                    beta=row.beta,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    def update_preference(self, user_id: str, style: str, *, alpha: float, beta: float) -> None:
        with self._session_factory() as session:
            row = (
                session.query(StylePreferenceRow)
                .filter(
                    StylePreferenceRow.user_id == user_id,
                    StylePreferenceRow.style == style,
                )
                .first()
            )
            if row is None:
                session.add(
                    StylePreferenceRow(
                        user_id=user_id,
                        style=style,
                        alpha=alpha,
                        beta=beta,
                        updated_at=time.time(),
                    )
                )
            else:
                row.alpha = alpha
                row.beta = beta
                row.updated_at = time.time()
            session.commit()
