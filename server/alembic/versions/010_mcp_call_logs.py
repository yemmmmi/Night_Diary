"""Create mcp_call_logs table.

Revision ID: 010_mcp_call_logs
Revises: 009_weekly_plan_struct
Create Date: 2026-09-04

Stores one row per MCP tool call (transport, duration, snapshots) for the
Dev panel call log. Idempotent: ``init_db`` may have already created the
table via ``Base.metadata.create_all`` before Alembic runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "010_mcp_call_logs"
down_revision = "009_weekly_plan_struct"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in inspect(bind).get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return index_name in {i["name"] for i in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "mcp_call_logs"):
        op.create_table(
            "mcp_call_logs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=True),
            sa.Column("trace_id", sa.String(length=64), nullable=True),
            sa.Column("span_id", sa.String(length=64), nullable=False),
            sa.Column("endpoint_alias", sa.String(length=64), nullable=False),
            sa.Column("transport", sa.String(length=16), nullable=False),
            sa.Column("tool_name", sa.String(length=128), nullable=False),
            sa.Column("raw_tool_name", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("duration_ms", sa.Float(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("arguments_snapshot", sa.Text(), nullable=False),
            sa.Column("result_snapshot", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Float(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    for index_name, column in (
        ("ix_mcp_call_logs_user_id", "user_id"),
        ("ix_mcp_call_logs_trace_id", "trace_id"),
        ("ix_mcp_call_logs_endpoint_alias", "endpoint_alias"),
        ("ix_mcp_call_logs_status", "status"),
    ):
        if not _index_exists(bind, "mcp_call_logs", index_name):
            op.create_index(index_name, "mcp_call_logs", [column])


def downgrade() -> None:
    op.drop_table("mcp_call_logs")
