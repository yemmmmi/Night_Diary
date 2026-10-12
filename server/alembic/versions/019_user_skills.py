"""Create user_skills and user_skill_versions for user-defined skills (A2).

Revision ID: 019_user_skills
Revises: 018_scheduled_task_mode_sink
Create Date: 2026-10-11

A2 (Hermes lessons): Hermes lets its agent create/edit/delete arbitrary skills.
夜记 opens a bounded subset — the *user* authors a reply-shaping skill by hand
(settings), it is safety-reviewed on write, and it is loaded read-only at reply
time. ``user_skill_versions`` keeps an append-only snapshot per revision.

``init_db``'s ``create_all`` may have already created these tables before Alembic
runs, so this migration is idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "019_user_skills"
down_revision = "018_scheduled_task_mode_sink"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "user_skills" not in tables:
        op.create_table(
            "user_skills",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=True),
            sa.Column("description", sa.String(length=200), nullable=True),
            sa.Column("triggers_json", sa.Text(), nullable=True),
            sa.Column("instruction", sa.Text(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.Float(), nullable=True),
            sa.Column("updated_at", sa.Float(), nullable=True),
        )
        op.create_index("ix_user_skills_user_id", "user_skills", ["user_id"])

    if "user_skill_versions" not in tables:
        op.create_table(
            "user_skill_versions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("skill_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(length=64), nullable=True),
            sa.Column("description", sa.String(length=200), nullable=True),
            sa.Column("triggers_json", sa.Text(), nullable=True),
            sa.Column("instruction", sa.Text(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.Float(), nullable=True),
        )
        op.create_index("ix_user_skill_versions_skill_id", "user_skill_versions", ["skill_id"])
        op.create_index("ix_user_skill_versions_user_id", "user_skill_versions", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "user_skill_versions" in tables:
        op.drop_table("user_skill_versions")
    if "user_skills" in tables:
        op.drop_table("user_skills")