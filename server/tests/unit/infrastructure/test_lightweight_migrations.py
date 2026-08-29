"""Lightweight migration tests: additive columns on legacy schemas."""

from __future__ import annotations

import sqlalchemy as sa

from app.infrastructure.database import create_db_engine, init_db


def test_init_db_adds_new_columns_to_legacy_weekly_reports(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    legacy = sa.Table(
        "weekly_reports",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("user_id", sa.String(64)),
    )
    legacy.create(engine)

    init_db(engine)

    columns = {c["name"] for c in sa.inspect(engine).get_columns("weekly_reports")}
    assert "plan_executions_json" in columns
    assert "week_tasks_json" in columns


def test_init_db_adds_intent_to_legacy_analyses(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    legacy = sa.Table(
        "analyses",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("diary_id", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime),
        sa.Column("log", sa.Text),
    )
    legacy.create(engine)

    init_db(engine)

    columns = {c["name"] for c in sa.inspect(engine).get_columns("analyses")}
    assert "intent" in columns


def test_init_db_is_idempotent_for_additive_columns(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    legacy = sa.Table(
        "analyses",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("diary_id", sa.Integer, nullable=False),
    )
    legacy.create(engine)

    init_db(engine)
    init_db(engine)

    columns = {c["name"] for c in sa.inspect(engine).get_columns("analyses")}
    assert "intent" in columns
