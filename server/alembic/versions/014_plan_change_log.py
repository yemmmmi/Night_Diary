"""Create plan_change_log for versioned plan/task changes with undo.

Revision ID: 014_plan_change_log
Revises: 013_provider_key_pool
Create Date: 2026-10-11

A3 (Hermes lessons): plan/task mutations were previously applied directly with
no undo. This append-only log stores the entity's ``before``/``after`` JSON for
every create/update/delete, so a change can be replayed (undone) later and
linked back to the agent proposal / chat reply that produced it.

``init_db`` may have already created the table via ``Base.metadata.create_all``
before Alembic runs, so this is idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "014_plan_change_log"
down_revision = "013_provider_key_pool"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "plan_change_log" in inspect(bind).get_table_names():
        return
    op.create_table(
        "plan_change_log",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_id", sa.String(32), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("proposal_id", sa.String(64), nullable=True),
        sa.Column("conversation_id", sa.String(32), nullable=True),
        sa.Column("message_id", sa.String(64), nullable=True),
        sa.Column("undone", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("undone_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_plan_change_log_user_id", "plan_change_log", ["user_id"])
    op.create_index("ix_plan_change_log_entity_id", "plan_change_log", ["entity_id"])
    op.create_index("ix_plan_change_log_proposal_id", "plan_change_log", ["proposal_id"])
    op.create_index(
        "ix_plan_change_log_conversation_id", "plan_change_log", ["conversation_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "plan_change_log" in inspect(bind).get_table_names():
        op.drop_table("plan_change_log")