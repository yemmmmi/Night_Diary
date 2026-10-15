"""Add profile_change_log table (P1-B: field-level profile change audit).

Revision ID: 021_profile_change_log
Revises: 020_image_assets
Create Date: 2026-10-14

P1-B: every field-level change to a user's long-term profile is now
audited — trigger source (promotion / mood_sync / manual), old/new values
and the memory pairs (evidence) the change was derived from. Written by
``LongTermMemory.update_profile`` through the ``ProfileChangeLogStore``
port.

``init_db``'s ``create_all`` may already have created the table before
Alembic runs, so this migration is idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "021_profile_change_log"
down_revision = "020_image_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "profile_change_log" not in inspector.get_table_names():
        op.create_table(
            "profile_change_log",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("field", sa.String(length=64), nullable=False),
            sa.Column("old_value", sa.Text(), nullable=True),
            sa.Column("new_value", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("evidence_json", sa.Text(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    index_names = {i["name"] for i in inspect(bind).get_indexes("profile_change_log")}
    if "ix_profile_change_log_user_id" not in index_names:
        op.create_index("ix_profile_change_log_user_id", "profile_change_log", ["user_id"])
    if "ix_profile_change_log_created_at" not in index_names:
        op.create_index(
            "ix_profile_change_log_created_at", "profile_change_log", ["created_at"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "profile_change_log" in inspector.get_table_names():
        index_names = {i["name"] for i in inspect(bind).get_indexes("profile_change_log")}
        if "ix_profile_change_log_user_id" in index_names:
            op.drop_index("ix_profile_change_log_user_id", table_name="profile_change_log")
        if "ix_profile_change_log_created_at" in index_names:
            op.drop_index(
                "ix_profile_change_log_created_at", table_name="profile_change_log"
            )
        op.drop_table("profile_change_log")
