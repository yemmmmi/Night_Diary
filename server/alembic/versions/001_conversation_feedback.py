"""Add conversation_id to feedback, make analysis_id and diary_id nullable.

Revision ID: 001_conversation_feedback
Revises:
Create Date: 2026-07-05

Unified feedback channel: supports both diary analysis feedback (scene 1)
and conversation reply feedback (scene 2).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "001_conversation_feedback"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add conversation_id column and make analysis_id/diary_id nullable."""
    # SQLite requires batch mode for ALTER TABLE operations
    with op.batch_alter_table("feedback", schema=None) as batch_op:
        # Add conversation_id column (nullable, for scene-2 feedback)
        batch_op.add_column(sa.Column("conversation_id", sa.String(64), nullable=True))
        batch_op.create_index("ix_feedback_conversation_id", ["conversation_id"])

        # Make analysis_id nullable (was NOT NULL, now allows NULL for conversation feedback)
        batch_op.alter_column(
            "analysis_id",
            existing_type=sa.Integer(),
            nullable=True,
        )

        # Make diary_id nullable (was NOT NULL, now allows NULL for conversation feedback)
        batch_op.alter_column(
            "diary_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    """Revert: remove conversation_id, make analysis_id/diary_id NOT NULL."""
    with op.batch_alter_table("feedback", schema=None) as batch_op:
        # Revert diary_id to NOT NULL
        batch_op.alter_column(
            "diary_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        # Revert analysis_id to NOT NULL
        batch_op.alter_column(
            "analysis_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.drop_index("ix_feedback_conversation_id")
        batch_op.drop_column("conversation_id")
