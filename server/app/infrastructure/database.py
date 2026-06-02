"""SQLAlchemy engine and session helpers for SQLite."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


def create_db_engine(database_url: str) -> Engine:
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(engine: Engine) -> None:
    """Create all registered ORM tables."""
    # Import models so metadata is populated before create_all().
    from app.infrastructure.models import agent_decision as _agent_decision_models  # noqa: F401
    from app.infrastructure.models import feedback as _feedback_models  # noqa: F401
    from app.infrastructure.models import llm_call_log as _llm_call_log_models  # noqa: F401
    from app.infrastructure.models import memory as _memory_models  # noqa: F401
    from app.infrastructure.models import skill_activation as _skill_activation_models  # noqa: F401

    Base.metadata.create_all(engine)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
