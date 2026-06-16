"""SQLAlchemy engine and session helpers for SQLite."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
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
    from app.infrastructure.models import analysis as _analysis_models  # noqa: F401
    from app.infrastructure.models import app_config as _app_config_models  # noqa: F401
    from app.infrastructure.models import conversation as _conversation_models  # noqa: F401
    from app.infrastructure.models import diary_entry as _diary_entry_models  # noqa: F401
    from app.infrastructure.models import feedback as _feedback_models  # noqa: F401
    from app.infrastructure.models import feedback_record as _feedback_record_models  # noqa: F401
    from app.infrastructure.models import llm_call_log as _llm_call_log_models  # noqa: F401
    from app.infrastructure.models import memory as _memory_models  # noqa: F401
    from app.infrastructure.models import memory_card as _memory_card_models  # noqa: F401
    from app.infrastructure.models import model_provider as _model_provider_models  # noqa: F401
    from app.infrastructure.models import skill_activation as _skill_activation_models  # noqa: F401
    from app.infrastructure.models import tag as _tag_models  # noqa: F401
    from app.infrastructure.models import weekly_report as _weekly_report_models  # noqa: F401

    Base.metadata.create_all(engine)
    _run_lightweight_migrations(engine)


def _run_lightweight_migrations(engine: Engine) -> None:
    """Add columns introduced after a table was first created.

    SQLite + ``create_all`` only creates *missing tables*; it never alters an
    existing one. For the single-user local DB we apply additive, idempotent
    ``ALTER TABLE ... ADD COLUMN`` statements so upgrades don't break on
    pre-existing databases. Only ever add nullable columns here.
    """
    additive_columns: dict[str, dict[str, str]] = {
        "memory_cards": {"emotions_json": "TEXT"},
    }

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in additive_columns.items():
            if table not in existing_tables:
                continue
            present = {col["name"] for col in inspector.get_columns(table)}
            for column, ddl_type in columns.items():
                if column not in present:
                    conn.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl_type}')
                    )


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
