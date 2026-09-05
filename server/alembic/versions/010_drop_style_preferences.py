"""Drop unused style_preferences table (Thompson Sampling remnant).

Revision ID: 010_drop_style_preferences
Revises: 009_weekly_plan_struct
Create Date: 2026-09-05

The Beta-preference store was never read after Thompson Sampling / PromptTuner
were removed. Explicit thumbs feedback stays on ``feedback`` (FeedbackRow).
"""

from __future__ import annotations

from sqlalchemy import inspect

from alembic import op

revision = "010_drop_style_preferences"
down_revision = "009_weekly_plan_struct"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "style_preferences"):
        op.drop_table("style_preferences")


def downgrade() -> None:
    # Table is unused; do not recreate on downgrade.
    return
