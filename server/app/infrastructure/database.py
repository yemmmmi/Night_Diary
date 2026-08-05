"""SQLAlchemy 引擎与会话辅助工具（SQLite + MySQL 双引擎）。"""

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
    """ORM 模型的声明式基类。"""


def create_db_engine(database_url: str) -> Engine:
    """根据 URL 协议为 SQLite 或 MySQL 创建 SQLAlchemy 引擎。"""
    is_sqlite = database_url.startswith("sqlite")
    is_mysql = database_url.startswith("mysql")

    if is_sqlite:
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn: Any, connection_record: Any) -> None:
            """在每个新连接上启用 WAL 模式及相关 pragma。

            - ``journal_mode=WAL``：读操作不会阻塞写操作，反之亦然。
            - ``synchronous=NORMAL``：与 WAL 配合安全，比 FULL 更快。
            - ``foreign_keys=ON``：强制外键约束。
            - ``busy_timeout=5000``：锁竞争时等待 5 秒后再报错。
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
        # 通用回退（PostgreSQL 等）
        engine = create_engine(database_url, pool_pre_ping=True)

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(engine: Engine) -> None:
    """创建所有已注册的 ORM 表。"""
    # 导入模型以便在 create_all() 之前填充元数据。
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
    from app.infrastructure.models import user as _user_models  # noqa: F401
    from app.infrastructure.models import weekly_report as _weekly_report_models  # noqa: F401

    Base.metadata.create_all(engine)
    _run_lightweight_migrations(engine)


def _table_columns(conn: Any, table: str) -> set[str]:
    """通过 ``conn`` 返回 ``table`` 已有列名的集合。"""
    return {col["name"] for col in inspect(conn).get_columns(table)}


def _run_lightweight_migrations(engine: Engine) -> None:
    """添加表首次创建后引入的列。

    ``create_all`` 只创建*缺失的表*，不会修改已存在的表。
    对于单用户本地数据库，我们应用累加式、幂等的
    ``ALTER TABLE ... ADD COLUMN`` 语句，以便升级时不会破坏
    已有的数据库。此处只能添加可空列。

    同时适用于 SQLite 和 MySQL：MySQL 使用反引号引用标识符，
    而 SQLite 使用双引号。``ai_ans -> reply`` 的复制迁移
    也依赖带引号的标识符，使源列在两种后端上都被读取为
    列引用（而非字符串字面量）。
    """
    is_mysql = engine.dialect.name == "mysql"

    def q(identifier: str) -> str:
        """为当前方言引用标识符。"""
        return f"`{identifier}`" if is_mysql else f'"{identifier}"'

    additive_columns: dict[str, dict[str, str]] = {
        "memory_cards": {"emotions_json": "TEXT", "user_id": "VARCHAR(64)"},
        "chat_messages": {"token_info": "TEXT"},
        "diary_entries": {"user_id": "VARCHAR(64)"},
        "conversations": {"user_id": "VARCHAR(64)"},
        "llm_call_logs": {"user_id": "VARCHAR(64)"},
        "agent_decisions": {"user_id": "VARCHAR(64)"},
        "tags": {"user_id": "VARCHAR(64)"},
        "weekly_reports": {"user_id": "VARCHAR(64)"},
        "model_providers": {"user_id": "VARCHAR(64)"},
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

        # 重命名 ai_ans → reply（SQLite < 3.35 不支持 DROP COLUMN，因此采用添加 + 复制方式）
        for table, col in [("diary_entries", "reply")]:
            cols = _table_columns(conn, table)
            if col not in cols and "ai_ans" in cols:
                conn.execute(text(f"ALTER TABLE {q(table)} ADD COLUMN {q(col)} TEXT"))
                conn.execute(text(f"UPDATE {q(table)} SET {q(col)} = {q('ai_ans')}"))
                logger.info("Migrated %s.%s from ai_ans", table, col)

        # 用 'default' 用户哨兵回填旧的单用户行。
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
