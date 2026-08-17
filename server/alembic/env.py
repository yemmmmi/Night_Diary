"""Alembic migration environment — supports both SQLite and MySQL."""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Add server/ to sys.path so app imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.infrastructure.database import Base

# Import all models to populate Base.metadata. The package __init__ is empty,
# so we import each module explicitly (mirroring ``init_db``) to guarantee the
# metadata is fully populated before autogenerate runs.
from app.infrastructure.models import *  # noqa: F403
from app.infrastructure.models import agent_decision as _agent_decision_models  # noqa: F401
from app.infrastructure.models import analysis as _analysis_models  # noqa: F401
from app.infrastructure.models import app_config as _app_config_models  # noqa: F401
from app.infrastructure.models import conversation as _conversation_models  # noqa: F401
from app.infrastructure.models import daily_digest as _daily_digest_models  # noqa: F401
from app.infrastructure.models import diary_entry as _diary_entry_models  # noqa: F401
from app.infrastructure.models import feedback as _feedback_models  # noqa: F401
from app.infrastructure.models import feedback_record as _feedback_record_models  # noqa: F401
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

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url with app settings. The DATABASE_URL env var (read via
# Settings.database_url_env) takes precedence; otherwise it falls back to the
# SQLite path under DATA_DIR.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Required for SQLite ALTER TABLE support
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
