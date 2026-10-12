"""Add mode/sink to scheduled_tasks for E3/E4.

Revision ID: 018_scheduled_task_mode_sink
Revises: 017_scheduled_tasks
Create Date: 2026-10-11

E3: ``mode`` distinguishes zero-LLM data tasks (``script``) from generation
tasks (``agent``). E4: ``sink`` names the result-delivery channel (default the
in-app mailbox). Existing ``weekly_insight`` tasks are backfilled to ``agent``
because they are inherently generation tasks.

``init_db``'s ``create_all`` may pre-create these columns from the ORM model,
so the migration checks for each column before adding it (idempotent).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "018_scheduled_task_mode_sink"
down_revision = "017_scheduled_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "scheduled_tasks" not in set(inspector.get_table_names()):
        return

    columns = {col["name"] for col in inspector.get_columns("scheduled_tasks")}
    if "mode" not in columns:
        op.add_column(
            "scheduled_tasks",
            sa.Column("mode", sa.String(length=16), nullable=False, server_default="script"),
        )
    if "sink" not in columns:
        op.add_column(
            "scheduled_tasks",
            sa.Column("sink", sa.String(length=32), nullable=False, server_default="inbox"),
        )

    # Weekly insight generates a letter through the LLM — mark it as agent mode.
    op.execute(
        "UPDATE scheduled_tasks SET mode = 'agent' "
        "WHERE kind = 'weekly_insight' AND mode = 'script'"
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "scheduled_tasks" not in set(inspector.get_table_names()):
        return
    columns = {col["name"] for col in inspector.get_columns("scheduled_tasks")}
    if "sink" in columns:
        op.drop_column("scheduled_tasks", "sink")
    if "mode" in columns:
        op.drop_column("scheduled_tasks", "mode")