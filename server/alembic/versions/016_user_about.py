"""Create user_abouts for the user-authored 「关于我」 file.

Revision ID: 016_user_about
Revises: 015_attached_tag_names
Create Date: 2026-10-11

B2 (Hermes lessons): Hermes keeps a user-editable ``USER.md`` separate from its
agent-managed ``MEMORY.md``. 夜记's analog is a user-authored 「关于我」 text —
background, preferences and expected tone — stored per user and frozen into the
system-prompt prefix alongside the system-inferred long-term profile.

``init_db``'s ``create_all`` may have already created the table before Alembic
runs, so this migration is idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "016_user_about"
down_revision = "015_attached_tag_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "user_abouts" in inspector.get_table_names():
        return
    op.create_table(
        "user_abouts",
        sa.Column("user_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "user_abouts" not in inspector.get_table_names():
        return
    op.drop_table("user_abouts")