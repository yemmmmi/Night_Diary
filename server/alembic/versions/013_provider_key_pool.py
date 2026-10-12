"""Add api_keys_encrypted to model_providers for key-pool rotation.

Revision ID: 013_provider_key_pool
Revises: 012_plan_task_source_links
Create Date: 2026-10-11

Stores a JSON list of Fernet-encrypted *extra* API keys for a provider, used
for round-robin rotation against per-key rate limits (Hermes-inspired D5).
The primary key remains in ``api_key_encrypted``; legacy rows keep NULL and
behave exactly as before (single-key pool).

``init_db`` may have already added the column via ``Base.metadata.create_all``
before Alembic runs, so this is idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "013_provider_key_pool"
down_revision = "012_plan_task_source_links"
branch_labels = None
depends_on = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if table_name not in inspect(bind).get_table_names():
        return False
    return column_name in {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "model_providers", "api_keys_encrypted"):
        op.add_column(
            "model_providers", sa.Column("api_keys_encrypted", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "model_providers", "api_keys_encrypted"):
        op.drop_column("model_providers", "api_keys_encrypted")