"""Create daily_digests table for the scene-1 tree-hole digest (V3 treehole).

Revision ID: 004_daily_digest
Revises: 003_plan_task
Create Date: 2026-08-12

Adds one new table:

* ``daily_digests`` — per-day structured digest (user_id + date unique),
  aggregating the day's memory cards (user-authored, zero LLM) with the
  typed diary extraction (LLM or rule). Scene 2 reads this instead of full
  diary content when referencing a day.

This migration is **idempotent**: it checks whether each object already
exists before creating it, because ``init_db`` calls
``Base.metadata.create_all`` at application startup (which may create the
table before Alembic runs). ``user_id`` is a plain ``String(64)`` without a
foreign key, mirroring every other user-scoped table.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "004_daily_digest"
down_revision = "003_plan_task"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in inspect(bind).get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return index_name in {i["name"] for i in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    """Create the daily_digests table with its indexes."""
    bind = op.get_bind()

    if not _table_exists(bind, "daily_digests"):
        op.create_table(
            "daily_digests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("digest_json", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "date", name="uq_daily_digests_user_date"),
        )

    if not _index_exists(bind, "daily_digests", "ix_daily_digests_user_id"):
        op.create_index("ix_daily_digests_user_id", "daily_digests", ["user_id"])


def downgrade() -> None:
    """Drop the daily_digests table."""
    bind = op.get_bind()

    if _table_exists(bind, "daily_digests"):
        if _index_exists(bind, "daily_digests", "ix_daily_digests_user_id"):
            op.drop_index("ix_daily_digests_user_id", table_name="daily_digests")
        op.drop_table("daily_digests")
