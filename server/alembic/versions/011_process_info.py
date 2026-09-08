"""Add process_info to chat_messages.

Revision ID: 011_process_info
Revises: 010_mcp_call_logs, 010_drop_style_preferences
Create Date: 2026-09-07

Stores a per-reply agent process summary (intent, skill used, tool calls,
duration, tokens) so the chat UI can show what the agent did — without
developer mode. ``init_db`` may have already added the column via
``Base.metadata.create_all`` before Alembic runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "011_process_info"
down_revision = ("010_mcp_call_logs", "010_drop_style_preferences")
branch_labels = None
depends_on = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if table_name not in inspect(bind).get_table_names():
        return False
    return column_name in {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "chat_messages", "process_info"):
        op.add_column("chat_messages", sa.Column("process_info", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "chat_messages", "process_info"):
        op.drop_column("chat_messages", "process_info")
