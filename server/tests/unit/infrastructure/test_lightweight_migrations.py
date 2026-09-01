"""Lightweight migration tests: additive columns on legacy schemas."""

from __future__ import annotations

import sqlalchemy as sa
import sqlalchemy.exc as sa_exc

from app.infrastructure import database as db_module
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


def test_init_db_tolerates_concurrent_duplicate_column_race(tmp_path, monkeypatch):
    """多进程并发迁移时, 输家收到 duplicate column 错误应被吞掉而非炸引导。

    Docker 部署 uvicorn --workers 4 + worker 容器同跑 init_db: 赢家先 ALTER
    成功, 输家反射的表结构是加列前的快照, 重放 ALTER 撞 1060/duplicate。
    模拟: patch 模块级 inspect, 让 analyses 的反射结果永远少 intent。
    """
    engine = create_db_engine(f"sqlite:///{tmp_path / 'race.db'}")
    legacy = sa.Table(
        "analyses",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("diary_id", sa.Integer, nullable=False),
    )
    legacy.create(engine)

    # 赢家已完成加列
    init_db(engine)
    assert "intent" in {c["name"] for c in sa.inspect(engine).get_columns("analyses")}

    # 输家: 反射快照里没有 intent, 会重放 ALTER
    real_inspect = db_module.inspect

    def stale_inspect(subject):
        real = real_inspect(subject)

        class StaleInspector:
            def get_columns(self, table, *args, **kwargs):
                cols = real.get_columns(table, *args, **kwargs)
                if table == "analyses":
                    return [c for c in cols if c["name"] != "intent"]
                return cols

            def __getattr__(self, name):
                return getattr(real, name)

        return StaleInspector()

    monkeypatch.setattr(db_module, "inspect", stale_inspect)

    # 不得抛出 — duplicate 视为「赢家已加过」并继续完成迁移
    init_db(engine)


def test_duplicate_column_classifier_matches_mysql_1060():
    """MySQL 输家路径: SQLAlchemy 包裹的 1060 错误要被识别为重复列。"""
    orig = RuntimeError("(1060, \"Duplicate column name 'recurrence'\")")
    exc = sa_exc.OperationalError("ALTER TABLE `plans`", None, orig)
    assert db_module._is_duplicate_column_error(exc)


def test_duplicate_column_classifier_rejects_unrelated_errors():
    exc = sa_exc.OperationalError("ALTER TABLE `plans`", None, RuntimeError("(1064, 'syntax error')"))
    assert not db_module._is_duplicate_column_error(exc)
