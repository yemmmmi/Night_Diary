"""Add source_links_json to tasks for per-node web-search provenance.

Revision ID: 012_plan_task_source_links
Revises: 011_process_info
Create Date: 2026-09-08

Stores, per milestone-template learning node, the web-search provenance the
agent gathered when building the plan: the search query and the candidate
sources (url/title/snippet/domain/multi_source/is_primary). This makes the
plan generation auditable instead of a single opaque ``link``.

Legacy rows keep NULL. ``init_db`` may have already added the column via
``Base.metadata.create_all`` before Alembic runs, so this is idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "012_plan_task_source_links"
down_revision = "011_process_info"
branch_labels = None
depends_on = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if table_name not in inspect(bind).get_table_names():
        return False
    return column_name in {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "tasks", "source_links_json"):
        op.add_column("tasks", sa.Column("source_links_json", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "tasks", "source_links_json"):
        op.drop_column("tasks", "source_links_json")
