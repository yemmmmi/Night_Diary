"""Tests for SQLite WAL mode and related PRAGMA settings."""

from __future__ import annotations

import threading
import time

from sqlalchemy import text

from app.infrastructure.database import create_db_engine, init_db


def _pragma_value(conn, name: str) -> str:
    return conn.execute(text(f"PRAGMA {name}")).fetchone()[0]


class TestWalPragmas:
    def test_journal_mode_is_wal(self, tmp_path):
        engine = create_db_engine(f"sqlite:///{tmp_path}/test_wal.db")
        init_db(engine)
        with engine.connect() as conn:
            assert _pragma_value(conn, "journal_mode") == "wal"
        engine.dispose()

    def test_synchronous_is_normal(self, tmp_path):
        engine = create_db_engine(f"sqlite:///{tmp_path}/test_sync.db")
        init_db(engine)
        with engine.connect() as conn:
            assert _pragma_value(conn, "synchronous") == 1  # NORMAL
        engine.dispose()

    def test_foreign_keys_on(self, tmp_path):
        engine = create_db_engine(f"sqlite:///{tmp_path}/test_fk.db")
        init_db(engine)
        with engine.connect() as conn:
            assert _pragma_value(conn, "foreign_keys") == 1
        engine.dispose()

    def test_busy_timeout_5000(self, tmp_path):
        engine = create_db_engine(f"sqlite:///{tmp_path}/test_bt.db")
        init_db(engine)
        with engine.connect() as conn:
            assert _pragma_value(conn, "busy_timeout") == 5000
        engine.dispose()


class TestConcurrentReadWrite:
    """WAL allows concurrent readers and a single writer without 'database is locked'."""

    def test_concurrent_read_during_write(self, tmp_path):
        engine = create_db_engine(f"sqlite:///{tmp_path}/test_concurrent.db")
        init_db(engine)

        with engine.begin() as conn:
            conn.execute(
                text("CREATE TABLE IF NOT EXISTS test_wal (id INTEGER PRIMARY KEY, val TEXT)")
            )

        errors: list[str] = []

        def writer():
            try:
                with engine.begin() as conn:
                    for i in range(30):
                        conn.execute(text(f"INSERT INTO test_wal (val) VALUES ('w-{i}')"))
                        time.sleep(0.002)
            except Exception as exc:
                errors.append(f"writer: {exc}")

        def reader():
            try:
                for _ in range(30):
                    with engine.connect() as conn:
                        conn.execute(text("SELECT COUNT(*) FROM test_wal")).fetchone()
                    time.sleep(0.002)
            except Exception as exc:
                errors.append(f"reader: {exc}")

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        assert not errors, f"Concurrent errors: {errors}"
        engine.dispose()
