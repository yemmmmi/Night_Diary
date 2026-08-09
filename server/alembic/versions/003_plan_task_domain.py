"""Create plans and tasks tables for the plan/task domain (V3 P2).

Revision ID: 003_plan_task
Revises: 002_pipeline_traces
Create Date: 2026-08-09

Adds two new tables:

* ``plans`` — a named container of related tasks with a motivation and
  source references (diary/memory citations).
* ``tasks`` — a single to-do item, optionally belonging to a plan.

Both tables carry ``source`` (manual vs agent) and
``created_from_conversation_id`` so we can audit which plans/tasks
originated from an Agent proposal vs direct user creation.

This migration is **idempotent**: it checks whether each object already
exists before creating it. This is necessary because ``init_db`` calls
``Base.metadata.create_all`` at application startup, which may have already
created these tables (and their indexes) before the Alembic migration runs.

Note: ``user_id`` is a plain ``String(64)`` without a foreign key to
``users.id`` (whose PK is ``Integer``). This mirrors the convention used by
every other user-scoped table and avoids a ``String`` → ``Integer`` type
mismatch that would break the MySQL backend.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "003_plan_task"
down_revision = "002_pipeline_traces"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helper predicates
# ---------------------------------------------------------------------------


def _table_exists(bind, table_name: str) -> bool:
    return table_name in inspect(bind).get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return index_name in {i["name"] for i in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    """Create plans and tasks tables with their indexes."""
    bind = op.get_bind()

    # 1. Create plans table (skip if create_all already made it)
    if not _table_exists(bind, "plans"):
        op.create_table(
            "plans",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("motivation", sa.Text(), nullable=True),
            sa.Column("source_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
            sa.Column("created_from_conversation_id", sa.String(length=32), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists(bind, "plans", "ix_plans_user_id"):
        op.create_index("ix_plans_user_id", "plans", ["user_id"])

    # 2. Create tasks table (skip if create_all already made it)
    if not _table_exists(bind, "tasks"):
        op.create_table(
            "tasks",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column(
                "plan_id",
                sa.String(length=32),
                sa.ForeignKey("plans.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
            sa.Column("created_from_conversation_id", sa.String(length=32), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists(bind, "tasks", "ix_tasks_plan_id"):
        op.create_index("ix_tasks_plan_id", "tasks", ["plan_id"])
    if not _index_exists(bind, "tasks", "ix_tasks_user_id"):
        op.create_index("ix_tasks_user_id", "tasks", ["user_id"])


def downgrade() -> None:
    """Drop tasks and plans tables."""
    bind = op.get_bind()

    if _table_exists(bind, "tasks"):
        if _index_exists(bind, "tasks", "ix_tasks_user_id"):
            op.drop_index("ix_tasks_user_id", table_name="tasks")
        if _index_exists(bind, "tasks", "ix_tasks_plan_id"):
            op.drop_index("ix_tasks_plan_id", table_name="tasks")
        op.drop_table("tasks")

    if _table_exists(bind, "plans"):
        if _index_exists(bind, "plans", "ix_plans_user_id"):
            op.drop_index("ix_plans_user_id", table_name="plans")
        op.drop_table("plans")
