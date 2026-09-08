"""Add structured plan-execution columns to weekly_reports.

Revision ID: 009_weekly_plan_struct
Revises: 008_daily_modes
Create Date: 2026-08-25

The weekly letter now persists a structured snapshot of plan executions and
standalone tasks for the report period (see ``weekly_service``
``_plan_executions_snapshot`` / ``_week_tasks_snapshot``), so the frontend can
render plan-vs-actual blocks without re-parsing the letter text. Legacy rows
keep NULL columns; the API maps NULL to an empty list.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "009_weekly_plan_struct"
down_revision = "008_daily_modes"
branch_labels = None
depends_on = None


def _columns(bind) -> set[str]:
    table = "weekly_reports" if "weekly_reports" in inspect(bind).get_table_names() else ""
    if not table:
        return set()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    with op.batch_alter_table("weekly_reports") as batch_op:
        if "plan_executions_json" not in existing:
            batch_op.add_column(sa.Column("plan_executions_json", sa.Text(), nullable=True))
        if "week_tasks_json" not in existing:
            batch_op.add_column(sa.Column("week_tasks_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("weekly_reports") as batch_op:
        batch_op.drop_column("week_tasks_json")
        batch_op.drop_column("plan_executions_json")
