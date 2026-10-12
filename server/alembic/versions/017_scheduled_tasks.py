"""Create scheduled_tasks and scheduled_task_runs for A4.

Revision ID: 017_scheduled_tasks
Revises: 016_user_about
Create Date: 2026-10-11

A4 (Hermes lessons): user-orchestrable recurring tasks. ``scheduled_tasks``
holds the task definitions (cron expression + kind + payload); each execution
is recorded in ``scheduled_task_runs`` as the in-app receipt.

``init_db``'s ``create_all`` may have already created the tables before
Alembic runs, so this migration is idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "017_scheduled_tasks"
down_revision = "016_user_about"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "scheduled_tasks" not in tables:
        op.create_table(
            "scheduled_tasks",
            sa.Column("id", sa.String(length=32), primary_key=True, nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("cron_expr", sa.String(length=128), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("next_run_at", sa.DateTime(), nullable=True),
            sa.Column("last_run_at", sa.DateTime(), nullable=True),
            sa.Column("last_status", sa.String(length=16), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_scheduled_tasks_user_id", "scheduled_tasks", ["user_id"])
        op.create_index("ix_scheduled_tasks_next_run_at", "scheduled_tasks", ["next_run_at"])

    if "scheduled_task_runs" not in tables:
        op.create_table(
            "scheduled_task_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("task_id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_scheduled_task_runs_task_id", "scheduled_task_runs", ["task_id"])
        op.create_index("ix_scheduled_task_runs_user_id", "scheduled_task_runs", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "scheduled_task_runs" in tables:
        op.drop_table("scheduled_task_runs")
    if "scheduled_tasks" in tables:
        op.drop_table("scheduled_tasks")