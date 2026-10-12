"""Add image_assets table and diary_entries.image_assets_json.

Revision ID: 020_image_assets
Revises: 019_user_skills
Create Date: 2026-10-11

B5 (Hermes lessons): diaries accept image attachments and the agent can
reference them by name. Uploaded files live on disk (``uploads_dir/<user_id>``)
while their metadata is recorded per user in ``image_assets``; a diary links to
its assets through ``diary_entries.image_assets_json`` (a JSON id list) so the
diary text itself stays clean.

``init_db``'s ``create_all`` may already have created the table/column before
Alembic runs, so this migration is idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "020_image_assets"
down_revision = "019_user_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "image_assets" not in inspector.get_table_names():
        op.create_table(
            "image_assets",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=True),
            sa.Column("stored_filename", sa.String(length=255), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=64), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    index_names = {i["name"] for i in inspect(bind).get_indexes("image_assets")}
    if "ix_image_assets_user_id" not in index_names:
        op.create_index("ix_image_assets_user_id", "image_assets", ["user_id"])

    columns = {c["name"] for c in inspect(bind).get_columns("diary_entries")}
    if "image_assets_json" not in columns:
        op.add_column(
            "diary_entries",
            sa.Column("image_assets_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = {c["name"] for c in inspect(bind).get_columns("diary_entries")}
    if "image_assets_json" in columns:
        op.drop_column("diary_entries", "image_assets_json")

    if "image_assets" in inspector.get_table_names():
        index_names = {i["name"] for i in inspect(bind).get_indexes("image_assets")}
        if "ix_image_assets_user_id" in index_names:
            op.drop_index("ix_image_assets_user_id", table_name="image_assets")
        op.drop_table("image_assets")