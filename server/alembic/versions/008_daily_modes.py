"""Create daily_modes table for the scene-2 user-mode system (V3.x mode).

Revision ID: 008_daily_modes
Revises: 007_jobs
Create Date: 2026-08-18

One user's judged mode baseline per calendar day (see
``app/infrastructure/models/daily_mode.py``). Mode internal codes are
``daily`` / ``followup`` / ``introspection`` — these are internal and never
shown to the user (user-visible names are 日常 / 跟进 / 内视).

Idempotent (init_db create_all may have created it first). Autoincrement
Integer id + UniqueConstraint(user_id, date); plain String(64) user_id without
FK, mirroring every other user-scoped table.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "008_daily_modes"
down_revision = "007_jobs"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in inspect(bind).get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return index_name in {i["name"] for i in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    """Create the daily_modes table with its indexes."""
    bind = op.get_bind()

    if not _table_exists(bind, "daily_modes"):
        op.create_table(
            "daily_modes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("baseline_mode", sa.String(length=20), nullable=False),
            sa.Column("auto_switched", sa.Boolean(), nullable=False),
            sa.Column("switch_count", sa.Integer(), nullable=False),
            sa.Column("mood_signals_json", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "date", name="uq_daily_modes_user_date"),
        )

    if not _index_exists(bind, "daily_modes", "ix_daily_modes_user_id"):
        op.create_index("ix_daily_modes_user_id", "daily_modes", ["user_id"])
    if not _index_exists(bind, "daily_modes", "ix_daily_modes_date"):
        op.create_index("ix_daily_modes_date", "daily_modes", ["date"])


def downgrade() -> None:
    """Drop the daily_modes table."""
    bind = op.get_bind()

    if _table_exists(bind, "daily_modes"):
        if _index_exists(bind, "daily_modes", "ix_daily_modes_user_id"):
            op.drop_index("ix_daily_modes_user_id", table_name="daily_modes")
        if _index_exists(bind, "daily_modes", "ix_daily_modes_date"):
            op.drop_index("ix_daily_modes_date", table_name="daily_modes")
        op.drop_table("daily_modes")
