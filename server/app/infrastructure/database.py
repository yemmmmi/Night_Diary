"""SQLAlchemy engine and session helpers (SQLite + MySQL dual-engine)."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


def create_db_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine for SQLite or MySQL based on URL scheme."""
    is_sqlite = database_url.startswith("sqlite")
    is_mysql = database_url.startswith("mysql")

    if is_sqlite:
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn: Any, connection_record: Any) -> None:
            """Enable WAL mode and related pragmas on every new connection.

            - ``journal_mode=WAL``: readers don't block writers and vice-versa.
            - ``synchronous=NORMAL``: safe with WAL, faster than FULL.
            - ``foreign_keys=ON``: enforce FK constraints.
            - ``busy_timeout=5000``: wait 5 s on lock contention before erroring.
            """
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    elif is_mysql:
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            connect_args={"charset": "utf8mb4"},
        )
        logger.info(
            "MySQL engine created: %s",
            database_url.split("@")[-1] if "@" in database_url else "(unknown host)",
        )
    else:
        # Generic fallback (PostgreSQL, etc.)
        engine = create_engine(database_url, pool_pre_ping=True)

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(engine: Engine) -> None:
    """Create all registered ORM tables."""
    # Import models so metadata is populated before create_all().
    from app.infrastructure.models import agent_decision as _agent_decision_models  # noqa: F401
    from app.infrastructure.models import analysis as _analysis_models  # noqa: F401
    from app.infrastructure.models import app_config as _app_config_models  # noqa: F401
    from app.infrastructure.models import conversation as _conversation_models  # noqa: F401
    from app.infrastructure.models import daily_digest as _daily_digest_models  # noqa: F401
    from app.infrastructure.models import diary_entry as _diary_entry_models  # noqa: F401
    from app.infrastructure.models import feedback as _feedback_models  # noqa: F401
    from app.infrastructure.models import feedback_record as _feedback_record_models  # noqa: F401
    from app.infrastructure.models import job as _job_models  # noqa: F401
    from app.infrastructure.models import llm_call_log as _llm_call_log_models  # noqa: F401
    from app.infrastructure.models import memory as _memory_models  # noqa: F401
    from app.infrastructure.models import memory_card as _memory_card_models  # noqa: F401
    from app.infrastructure.models import model_provider as _model_provider_models  # noqa: F401
    from app.infrastructure.models import plan as _plan_models  # noqa: F401
    from app.infrastructure.models import reply_quality as _reply_quality_models  # noqa: F401
    from app.infrastructure.models import skill_activation as _skill_activation_models  # noqa: F401
    from app.infrastructure.models import tag as _tag_models  # noqa: F401
    from app.infrastructure.models import user as _user_models  # noqa: F401
    from app.infrastructure.models import weekly_report as _weekly_report_models  # noqa: F401

    Base.metadata.create_all(engine)
    _run_lightweight_migrations(engine)


def _table_columns(conn: Any, table: str) -> set[str]:
    """Return the set of existing column names for ``table`` via ``conn``."""
    return {col["name"] for col in inspect(conn).get_columns(table)}


def _run_lightweight_migrations(engine: Engine) -> None:
    """Add columns introduced after a table was first created.

    ``create_all`` only creates *missing tables*; it never alters an existing
    one. For the single-user local DB we apply additive, idempotent
    ``ALTER TABLE ... ADD COLUMN`` statements so upgrades don't break on
    pre-existing databases. Only ever add nullable columns here.

    Works for both SQLite and MySQL: MySQL uses backticks for identifiers
    while SQLite uses double quotes. The ``ai_ans -> reply`` copy migration
    also relies on quoted identifiers so the source column is read as a
    column reference (not a string literal) on both backends.
    """
    is_mysql = engine.dialect.name == "mysql"

    def q(identifier: str) -> str:
        """Quote an identifier for the active dialect."""
        return f"`{identifier}`" if is_mysql else f'"{identifier}"'

    additive_columns: dict[str, dict[str, str]] = {
        "memory_cards": {"emotions_json": "TEXT", "user_id": "VARCHAR(64)"},
        "chat_messages": {"token_info": "TEXT"},
        "diary_entries": {"user_id": "VARCHAR(64)"},
        "conversations": {"user_id": "VARCHAR(64)"},
        "llm_call_logs": {"user_id": "VARCHAR(64)"},
        "agent_decisions": {"user_id": "VARCHAR(64)"},
        "tags": {"user_id": "VARCHAR(64)"},
        "analyses": {"intent": "VARCHAR(32)"},
        "weekly_reports": {
            "user_id": "VARCHAR(64)",
            "plan_executions_json": "TEXT",
            "week_tasks_json": "TEXT",
        },
        "model_providers": {"user_id": "VARCHAR(64)"},
        "plans": {
            "recurrence": "VARCHAR(32)",
            "target_value": "REAL",
            "target_unit": "VARCHAR(16)",
            "target_period": "VARCHAR(16)",
        },
        "tasks": {"actual_value": "REAL"},
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
                    conn.execute(text(f"ALTER TABLE {q(table)} ADD COLUMN {q(column)} {ddl_type}"))

        # Rename ai_ans → reply (SQLite < 3.35 can't DROP COLUMN, so we add + copy)
        for table, col in [("diary_entries", "reply")]:
            cols = _table_columns(conn, table)
            if col not in cols and "ai_ans" in cols:
                conn.execute(text(f"ALTER TABLE {q(table)} ADD COLUMN {q(col)} TEXT"))
                conn.execute(text(f"UPDATE {q(table)} SET {q(col)} = {q('ai_ans')}"))
                logger.info("Migrated %s.%s from ai_ans", table, col)

        # Backfill legacy single-user rows with the 'default' user sentinel.
        user_scoped_tables = [
            "diary_entries",
            "memory_cards",
            "conversations",
            "llm_call_logs",
            "agent_decisions",
            "tags",
            "weekly_reports",
            "model_providers",
        ]
        for table in user_scoped_tables:
            if table not in existing_tables:
                continue
            conn.execute(
                text(
                    f"UPDATE {q(table)} SET {q('user_id')} = 'default' WHERE {q('user_id')} IS NULL"
                )
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
