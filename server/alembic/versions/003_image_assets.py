"""Create image_assets table for uploaded image processing.

Revision ID: 003_image_assets
Revises: 002_pipeline_traces
Create Date: 2026-07-07

Adds the ``image_assets`` table that records user-uploaded images and the
async image-processing pipeline results (``semantic_description``,
``extracted_text``, ``content_type``, ``processing_path``). Rows are scoped
to a user via ``user_id`` for multi-tenant isolation.

This migration is **idempotent**: it checks whether the table already exists
before creating it, because ``init_db`` calls ``Base.metadata.create_all`` at
application startup, which may have already created the table before the
Alembic migration runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect
from alembic import op

# revision identifiers, used by Alembic.
revision = "003_image_assets"
down_revision = "002_pipeline_traces"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in inspect(bind).get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return index_name in {i["name"] for i in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    """Create image_assets table with user_id index."""
    bind = op.get_bind()

    if not _table_exists(bind, "image_assets"):
        op.create_table(
            "image_assets",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=True),
            sa.Column("stored_filename", sa.String(length=255), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=64), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("semantic_description", sa.Text(), nullable=True),
            sa.Column("extracted_text", sa.Text(), nullable=True),
            sa.Column(
                "content_type", sa.String(length=32), nullable=False, server_default="unknown"
            ),
            sa.Column(
                "processing_path",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("model_used", sa.String(length=128), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists(bind, "image_assets", "ix_image_assets_user_id"):
        op.create_index(
            "ix_image_assets_user_id",
            "image_assets",
            ["user_id"],
        )


def downgrade() -> None:
    """Drop image_assets table."""
    bind = op.get_bind()

    if _index_exists(bind, "image_assets", "ix_image_assets_user_id"):
        op.drop_index("ix_image_assets_user_id", table_name="image_assets")

    if _table_exists(bind, "image_assets"):
        op.drop_table("image_assets")
