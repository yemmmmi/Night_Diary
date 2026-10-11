"""Add chat_messages.attached_tag_names for explicit tag references.

Revision ID: 015_attached_tag_names
Revises: 014_plan_change_log
Create Date: 2026-10-11

B1 (Hermes lessons): users can reference tags (``@标签``) in a chat turn as
explicit context. The referenced tag names are persisted on the user message
so the turn can be replayed and the UI can render the reference chips.

``init_db``'s ``create_all`` plus the lightweight additive-column migration in
``database.py`` may have already created the column before Alembic runs, so
this is idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "015_attached_tag_names"
down_revision = "014_plan_change_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "chat_messages" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("chat_messages")}
    if "attached_tag_names" in columns:
        return
    op.add_column("chat_messages", sa.Column("attached_tag_names", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "chat_messages" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("chat_messages")}
    if "attached_tag_names" not in columns:
        return
    op.drop_column("chat_messages", "attached_tag_names")