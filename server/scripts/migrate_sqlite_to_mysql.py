#!/usr/bin/env python3
"""SQLite -> MySQL data migration script.

Migrates all table data from the existing SQLite database to a freshly
created MySQL database.  Run this *after* ``init_db`` has created the
schema on MySQL (see PR1 step 4 in the fix plan).

Usage::

    # Preview what will be migrated (no writes)
    python scripts/migrate_sqlite_to_mysql.py --dry-run

    # Perform the migration
    python scripts/migrate_sqlite_to_mysql.py

    # Overwrite non-empty target tables
    python scripts/migrate_sqlite_to_mysql.py --force

Pre-conditions:
    1. MySQL running (``docker compose up -d mysql``)
    2. Schema created (``init_db`` + ``alembic stamp head``)
    3. ``DATABASE_URL`` env var points to the MySQL instance

The script never deletes the source SQLite file — it remains as a
rollback safety net.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

# Ensure the app package is importable when running from server/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.infrastructure.database import Base, create_db_engine

# Import every model module so Base.metadata is fully populated (mirrors
# the import list in database.init_db).  F401 is disabled per-file in
# pyproject.toml: ruff's autofix would otherwise strip these side-effect
# imports.
from app.infrastructure.models import (
    agent_decision,
    analysis,
    app_config,
    conversation,
    diary_entry,
    feedback,
    feedback_record,
    llm_call_log,
    memory,
    memory_card,
    model_provider,
    pipeline_trace,
    skill_activation,
    tag,
    user,
    weekly_report,
)

logger = logging.getLogger("migrate")

BATCH_SIZE = 100


def _resolve_sqlite_url() -> str:
    """Resolve the source SQLite URL.

    Priority:
      1. ``--sqlite-url`` CLI flag
      2. ``SQLITE_SOURCE_URL`` env var
      3. The default data_dir path (``<data_dir>/night_diary.db``)
    """
    settings = get_settings()
    db_path = Path(settings.data_dir) / "night_diary.db"
    if not db_path.exists():
        raise FileNotFoundError(
            f"SQLite database not found at {db_path}. "
            "Use --sqlite-url to specify an alternative path."
        )
    return f"sqlite:///{db_path}"


def _resolve_mysql_url() -> str:
    """Resolve the destination MySQL URL from DATABASE_URL env var."""
    url = os.getenv("DATABASE_URL", "")
    if not url:
        settings = get_settings()
        url = settings.database_url
    if not url.startswith("mysql"):
        raise ValueError(
            f"DATABASE_URL must point to MySQL (got '{url[:40]}...'). "
            "Set DATABASE_URL env var or .env file."
        )
    return url


def _backup_sqlite(sqlite_url: str) -> Path | None:
    """Copy the SQLite file to a timestamped backup before migration."""
    if not sqlite_url.startswith("sqlite:///"):
        return None
    db_path = Path(sqlite_url.replace("sqlite:///", "", 1))
    if not db_path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = db_path.with_name(f"{db_path.stem}_pre_mysql_migration_{ts}.db")
    shutil.copy2(db_path, backup)
    logger.info("SQLite backed up to %s", backup)
    return backup


def _get_source_tables(src_engine: Engine) -> set[str]:
    """Tables that actually exist in the source SQLite database."""
    return set(inspect(src_engine).get_table_names())


def _get_destination_tables(dst_engine: Engine) -> set[str]:
    """Tables that exist in the destination MySQL database."""
    return set(inspect(dst_engine).get_table_names())


def _check_target_empty(
    dst_engine: Engine, tables: list, *, force: bool
) -> bool:
    """Return True if safe to proceed (all target tables empty or --force)."""
    with dst_engine.connect() as conn:
        for table in tables:
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM `{table.name}`")
            ).scalar()
            if count and count > 0 and not force:
                logger.error(
                    "Target table `%s` has %d rows. "
                    "Use --force to truncate before migration.",
                    table.name,
                    count,
                )
                return False
    return True


def _migrate_table(
    src_engine: Engine,
    dst_conn,
    table,
    dst_columns: set[str],
    *,
    dry_run: bool,
) -> int:
    """Migrate a single table. Returns number of rows migrated.

    Only columns present in *dst_columns* (the destination schema) are
    inserted — source-only legacy columns (e.g. a renamed field) are
    silently dropped so the migration is resilient to schema drift.
    """
    table_name = table.name

    # Read all rows from SQLite
    with src_engine.connect() as src_conn:
        rows = src_conn.execute(
            text(f'SELECT * FROM "{table_name}"')
        ).mappings().all()

    if not rows:
        logger.info("  %-25s 0 rows (skip)", table_name)
        return 0

    if dry_run:
        logger.info("  %-25s %d rows [DRY RUN]", table_name, len(rows))
        return len(rows)

    # Intersect source columns with destination columns to handle drift
    src_columns = set(rows[0].keys())
    columns = [c for c in rows[0] if c in dst_columns]
    dropped = src_columns - dst_columns
    if dropped:
        logger.warning(
            "  %-25s dropping source-only columns: %s",
            table_name,
            ", ".join(sorted(dropped)),
        )

    # Truncate target
    dst_conn.execute(text(f"DELETE FROM `{table_name}`"))

    col_list = ", ".join(f"`{c}`" for c in columns)
    param_list = ", ".join(f":{c}" for c in columns)
    insert_sql = text(
        f"INSERT INTO `{table_name}` ({col_list}) VALUES ({param_list})"
    )

    migrated = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = [
            {c: row[c] for c in columns}
            for row in rows[i : i + BATCH_SIZE]
        ]
        dst_conn.execute(insert_sql, batch)
        migrated += len(batch)

    logger.info("  %-25s %d rows migrated", table_name, migrated)
    return migrated


def _verify(
    src_engine: Engine,
    dst_engine: Engine,
    tables: list,
) -> None:
    """Verify row counts match between source and destination."""
    logger.info("\nVerification:")
    all_ok = True
    with src_engine.connect() as s, dst_engine.connect() as d:
        for table in tables:
            src_count = s.execute(
                text(f'SELECT COUNT(*) FROM "{table.name}"')
            ).scalar()
            dst_count = d.execute(
                text(f"SELECT COUNT(*) FROM `{table.name}`")
            ).scalar()
            status = "OK" if src_count == dst_count else "MISMATCH"
            if src_count != dst_count:
                all_ok = False
            logger.info(
                "  %-25s src=%-6d dst=%-6d [%s]",
                table.name,
                src_count,
                dst_count,
                status,
            )
    if not all_ok:
        logger.warning("Row count mismatch detected! Check logs above.")


def migrate(
    sqlite_url: str,
    mysql_url: str,
    *,
    dry_run: bool,
    force: bool,
) -> None:
    logger.info("Source (SQLite): %s", sqlite_url)
    logger.info("Destination (MySQL): %s", mysql_url.split("@")[-1])

    src_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    dst_engine = create_db_engine(mysql_url)

    src_tables = _get_source_tables(src_engine)
    dst_tables = _get_destination_tables(dst_engine)

    # Tables in dependency order, filtered to those present in both DBs
    sorted_tables = [
        t for t in Base.metadata.sorted_tables
        if t.name in src_tables and t.name in dst_tables
    ]

    missing_in_dst = src_tables - dst_tables
    if missing_in_dst:
        logger.warning(
            "Tables in source but missing in destination: %s", missing_in_dst
        )

    logger.info("\nTables to migrate (%d):", len(sorted_tables))
    for t in sorted_tables:
        logger.info("  - %s", t.name)

    # Build a map of destination column names per table (for drift handling)
    dst_columns_map: dict[str, set[str]] = {}
    with dst_engine.connect() as conn:
        for table in sorted_tables:
            cols = inspect(dst_engine).get_columns(table.name)
            dst_columns_map[table.name] = {c["name"] for c in cols}

    if not dry_run:
        if not _check_target_empty(dst_engine, sorted_tables, force=force):
            logger.error("Aborting: target tables not empty (use --force).")
            return
        _backup_sqlite(sqlite_url)

    total = 0
    if dry_run:
        for table in sorted_tables:
            total += _migrate_table(
                src_engine, None, table,
                dst_columns_map[table.name], dry_run=True,
            )
        logger.info("\nTotal (dry run): %d rows would be migrated", total)
    else:
        with dst_engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for table in sorted_tables:
                total += _migrate_table(
                    src_engine, conn, table,
                    dst_columns_map[table.name], dry_run=False,
                )
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        logger.info("\nTotal: %d rows migrated", total)
        _verify(src_engine, dst_engine, sorted_tables)

    src_engine.dispose()
    dst_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate data from SQLite to MySQL."
    )
    parser.add_argument(
        "--sqlite-url",
        default=None,
        help="Source SQLite URL (default: <data_dir>/night_diary.db)",
    )
    parser.add_argument(
        "--mysql-url",
        default=None,
        help="Destination MySQL URL (default: from DATABASE_URL env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing any data",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Truncate non-empty target tables before migration",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    sqlite_url = args.sqlite_url or os.getenv("SQLITE_SOURCE_URL") or _resolve_sqlite_url()
    mysql_url = args.mysql_url or _resolve_mysql_url()

    try:
        migrate(
            sqlite_url,
            mysql_url,
            dry_run=args.dry_run,
            force=args.force,
        )
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
