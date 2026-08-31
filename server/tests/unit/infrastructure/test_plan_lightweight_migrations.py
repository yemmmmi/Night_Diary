"""Additive-column migration tests for plan/task metric columns (PR4)."""

from __future__ import annotations

import sqlalchemy as sa

from app.infrastructure.database import create_db_engine, init_db


def _legacy_plans_table() -> sa.Table:
    return sa.Table(
        "plans",
        sa.MetaData(),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(64)),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("motivation", sa.Text),
        sa.Column("source_refs_json", sa.Text),
        sa.Column("status", sa.String(20)),
        sa.Column("source", sa.String(20)),
        sa.Column("created_from_conversation_id", sa.String(32)),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )


def _legacy_tasks_table() -> sa.Table:
    return sa.Table(
        "tasks",
        sa.MetaData(),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("plan_id", sa.String(32)),
        sa.Column("user_id", sa.String(64)),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("due_date", sa.Date),
        sa.Column("status", sa.String(20)),
        sa.Column("source", sa.String(20)),
        sa.Column("created_from_conversation_id", sa.String(32)),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )


def test_init_db_adds_metric_columns_to_legacy_plans(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    _legacy_plans_table().create(engine)

    init_db(engine)

    columns = {c["name"] for c in sa.inspect(engine).get_columns("plans")}
    assert {"recurrence", "target_value", "target_unit", "target_period"} <= columns


def test_init_db_adds_actual_value_to_legacy_tasks(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    _legacy_tasks_table().create(engine)

    init_db(engine)

    columns = {c["name"] for c in sa.inspect(engine).get_columns("tasks")}
    assert "actual_value" in columns


def test_init_db_idempotent_for_plan_metric_columns(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    _legacy_plans_table().create(engine)

    init_db(engine)
    init_db(engine)

    names = [c["name"] for c in sa.inspect(engine).get_columns("plans")]
    assert names.count("recurrence") == 1
