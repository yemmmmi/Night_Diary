"""Create jobs table for replayable background tasks (robustness P2-6).

Revision ID: 007_jobs
Revises: 006_reply_quality
Create Date: 2026-08-17

Idempotent (init_db create_all may have created it first). Plain String(64)
user_id without FK, mirroring every other user-scoped table.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "007_jobs"
down_revision = "006_reply_quality"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in inspect(bind).get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return index_name in {i["name"] for i in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    """Create the jobs table with its indexes."""
    bind = op.get_bind()

    if not _table_exists(bind, "jobs"):
        op.create_table(
            "jobs",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists(bind, "jobs", "ix_jobs_user_id"):
        op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    if not _index_exists(bind, "jobs", "ix_jobs_kind"):
        op.create_index("ix_jobs_kind", "jobs", ["kind"])
    if not _index_exists(bind, "jobs", "ix_jobs_status"):
        op.create_index("ix_jobs_status", "jobs", ["status"])


def downgrade() -> None:
    """Drop the jobs table."""
    bind = op.get_bind()

    if _table_exists(bind, "jobs"):
        for index in ("ix_jobs_user_id", "ix_jobs_kind", "ix_jobs_status"):
            if _index_exists(bind, "jobs", index):
                op.drop_index(index, table_name="jobs")
        op.drop_table("jobs")
