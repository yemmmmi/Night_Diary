"""Create reply_quality table for the online quality sentinel (P1-4).

Revision ID: 006_reply_quality
Revises: 005_analysis_intent
Create Date: 2026-08-17

Idempotent (init_db create_all may have created it first). Plain String(64)
user_id without FK, mirroring every other user-scoped table.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "006_reply_quality"
down_revision = "005_analysis_intent"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in inspect(bind).get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return index_name in {i["name"] for i in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    """Create the reply_quality table with its indexes."""
    bind = op.get_bind()

    if not _table_exists(bind, "reply_quality"):
        op.create_table(
            "reply_quality",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("scenario", sa.String(length=32), nullable=False),
            sa.Column("ref_id", sa.String(length=64), nullable=False),
            sa.Column("reply_text", sa.Text(), nullable=False),
            sa.Column("scores_json", sa.Text(), nullable=True),
            sa.Column("overall", sa.Float(), nullable=True),
            sa.Column("judge_model", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists(bind, "reply_quality", "ix_reply_quality_user_id"):
        op.create_index("ix_reply_quality_user_id", "reply_quality", ["user_id"])
    if not _index_exists(bind, "reply_quality", "ix_reply_quality_ref_id"):
        op.create_index("ix_reply_quality_ref_id", "reply_quality", ["ref_id"])


def downgrade() -> None:
    """Drop the reply_quality table."""
    bind = op.get_bind()

    if _table_exists(bind, "reply_quality"):
        if _index_exists(bind, "reply_quality", "ix_reply_quality_user_id"):
            op.drop_index("ix_reply_quality_user_id", table_name="reply_quality")
        if _index_exists(bind, "reply_quality", "ix_reply_quality_ref_id"):
            op.drop_index("ix_reply_quality_ref_id", table_name="reply_quality")
        op.drop_table("reply_quality")
