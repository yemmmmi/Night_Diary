"""Create pipeline_traces table and add trace_id to tracing tables.

Revision ID: 002_pipeline_traces
Revises: 001_conversation_feedback
Create Date: 2026-07-06

Adds a new ``pipeline_traces`` table that stores the full JSON payload of
each pipeline execution, plus a ``trace_id`` foreign-reference column on the
three existing tracing tables (``llm_call_logs``, ``agent_decisions``,
``skill_activations``) so individual spans can be correlated back to the
parent trace.

This migration is **idempotent**: it checks whether each object already
exists before creating it. This is necessary because ``init_db`` calls
``Base.metadata.create_all`` at application startup, which may have already
created the ``pipeline_traces`` table (and its indexes) before the Alembic
migration runs. The ``trace_id`` columns on the three existing tables,
however, are only ever added by this migration since ``create_all`` does
not alter existing tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect
from alembic import op

# revision identifiers, used by Alembic.
revision = "002_pipeline_traces"
down_revision = "001_conversation_feedback"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helper predicates
# ---------------------------------------------------------------------------

def _table_exists(bind, table_name: str) -> bool:
    return table_name in inspect(bind).get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return column_name in {c["name"] for c in inspect(bind).get_columns(table_name)}


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return index_name in {i["name"] for i in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    """Create pipeline_traces table; add trace_id to tracing tables."""
    bind = op.get_bind()

    # 1. Create pipeline_traces table (skip if create_all already made it)
    if not _table_exists(bind, "pipeline_traces"):
        op.create_table(
            "pipeline_traces",
            sa.Column("trace_id", sa.String(length=64), nullable=False),
            sa.Column("scenario", sa.String(length=16), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("started_at", sa.String(length=32), nullable=False),
            sa.Column("ended_at", sa.String(length=32), nullable=True),
            sa.Column("duration_ms", sa.Float(), nullable=True),
            sa.Column("span_count", sa.Integer(), nullable=True),
            sa.Column("ref_id", sa.String(length=64), nullable=True),
            sa.Column("trace_json", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("trace_id"),
        )

    # 2. Create composite indexes on pipeline_traces (skip if they exist)
    if not _index_exists(bind, "pipeline_traces", "idx_traces_user"):
        op.create_index(
            "idx_traces_user",
            "pipeline_traces",
            ["user_id", "started_at"],
        )
    if not _index_exists(bind, "pipeline_traces", "idx_traces_scenario"):
        op.create_index(
            "idx_traces_scenario",
            "pipeline_traces",
            ["scenario", "started_at"],
        )

    # 3. Add trace_id column + index to llm_call_logs
    if not _column_exists(bind, "llm_call_logs", "trace_id"):
        with op.batch_alter_table("llm_call_logs", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("trace_id", sa.String(length=64), nullable=True)
            )
            batch_op.create_index("ix_llm_call_logs_trace_id", ["trace_id"])
    elif not _index_exists(bind, "llm_call_logs", "ix_llm_call_logs_trace_id"):
        with op.batch_alter_table("llm_call_logs", schema=None) as batch_op:
            batch_op.create_index("ix_llm_call_logs_trace_id", ["trace_id"])

    # 4. Add trace_id column + index to agent_decisions
    if not _column_exists(bind, "agent_decisions", "trace_id"):
        with op.batch_alter_table("agent_decisions", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("trace_id", sa.String(length=64), nullable=True)
            )
            batch_op.create_index("ix_agent_decisions_trace_id", ["trace_id"])
    elif not _index_exists(bind, "agent_decisions", "ix_agent_decisions_trace_id"):
        with op.batch_alter_table("agent_decisions", schema=None) as batch_op:
            batch_op.create_index("ix_agent_decisions_trace_id", ["trace_id"])

    # 5. Add trace_id column + index to skill_activations
    if not _column_exists(bind, "skill_activations", "trace_id"):
        with op.batch_alter_table("skill_activations", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("trace_id", sa.String(length=64), nullable=True)
            )
            batch_op.create_index("ix_skill_activations_trace_id", ["trace_id"])
    elif not _index_exists(bind, "skill_activations", "ix_skill_activations_trace_id"):
        with op.batch_alter_table("skill_activations", schema=None) as batch_op:
            batch_op.create_index("ix_skill_activations_trace_id", ["trace_id"])


def downgrade() -> None:
    """Drop trace_id from tracing tables; drop pipeline_traces table."""
    bind = op.get_bind()

    # 1. Drop trace_id from skill_activations
    if _column_exists(bind, "skill_activations", "trace_id"):
        with op.batch_alter_table("skill_activations", schema=None) as batch_op:
            if _index_exists(bind, "skill_activations", "ix_skill_activations_trace_id"):
                batch_op.drop_index("ix_skill_activations_trace_id")
            batch_op.drop_column("trace_id")

    # 2. Drop trace_id from agent_decisions
    if _column_exists(bind, "agent_decisions", "trace_id"):
        with op.batch_alter_table("agent_decisions", schema=None) as batch_op:
            if _index_exists(bind, "agent_decisions", "ix_agent_decisions_trace_id"):
                batch_op.drop_index("ix_agent_decisions_trace_id")
            batch_op.drop_column("trace_id")

    # 3. Drop trace_id from llm_call_logs
    if _column_exists(bind, "llm_call_logs", "trace_id"):
        with op.batch_alter_table("llm_call_logs", schema=None) as batch_op:
            if _index_exists(bind, "llm_call_logs", "ix_llm_call_logs_trace_id"):
                batch_op.drop_index("ix_llm_call_logs_trace_id")
            batch_op.drop_column("trace_id")

    # 4. Drop composite indexes on pipeline_traces
    if _index_exists(bind, "pipeline_traces", "idx_traces_scenario"):
        op.drop_index("idx_traces_scenario", table_name="pipeline_traces")
    if _index_exists(bind, "pipeline_traces", "idx_traces_user"):
        op.drop_index("idx_traces_user", table_name="pipeline_traces")

    # 5. Drop pipeline_traces table
    if _table_exists(bind, "pipeline_traces"):
        op.drop_table("pipeline_traces")
