"""Add intent column to analyses (scene-1 tree-hole, V3 treehole).

Revision ID: 005_analysis_intent
Revises: 004_daily_digest
Create Date: 2026-08-12

The scene-1 tree-hole pipeline persists the diary intent (4-class) on the
analysis row so it survives beyond the log string. Idempotent: adds the
column only if missing (``init_db`` / ``create_all`` may already have it).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "005_analysis_intent"
down_revision = "004_daily_digest"
branch_labels = None
depends_on = None


def _column_exists(bind, table: str, column: str) -> bool:
    if table not in inspect(bind).get_table_names():
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    """Add analyses.intent if missing."""
    bind = op.get_bind()
    if not _column_exists(bind, "analyses", "intent"):
        op.add_column(
            "analyses",
            sa.Column("intent", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    """Drop analyses.intent if present."""
    bind = op.get_bind()
    if _column_exists(bind, "analyses", "intent"):
        op.drop_column("analyses", "intent")
