"""Unit tests for the replayable job service (robustness P2-6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from app.infrastructure.models.job import JobRow
from app.services.job_service import (
    MAX_ATTEMPTS,
    claim_job,
    enqueue_and_dispatch,
    enqueue_job,
    finish_job,
    requeue_stale_jobs,
)


def _make_container(db_session) -> MagicMock:
    """Container whose session_factory yields independent sessions on the
    same SQLite file (the runner's ``with session_factory() as db`` closes
    sessions on exit, so sharing the test session would break)."""
    from sqlalchemy.orm import sessionmaker

    container = MagicMock()
    container.session_factory = sessionmaker(bind=db_session.get_bind())
    return container


def test_enqueue_job_creates_pending_row(db_session):
    row = enqueue_job(
        db_session,
        kind="entity_extraction",
        payload={"user_id": "u1", "text": "今天见到了李总"},
        user_id="u1",
    )
    assert row.id
    assert row.status == "pending"
    assert row.kind == "entity_extraction"
    assert "李总" in row.payload_json


def test_claim_job_marks_running_and_counts_attempts(db_session):
    row = enqueue_job(db_session, kind="entity_extraction", payload={}, user_id="u1")
    claimed = claim_job(db_session, row.id)
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempts == 1
    # 二次 claim 失败（已运行中）
    assert claim_job(db_session, row.id) is None


def test_finish_job_records_error(db_session):
    row = enqueue_job(db_session, kind="entity_extraction", payload={}, user_id="u1")
    finish_job(db_session, row.id, status="failed", error="boom")
    db_session.refresh(row)
    assert row.status == "failed"
    assert row.error == "boom"


def test_requeue_stale_jobs_redispatch_and_fail_exhausted(db_session):
    # 一个超过 stale 阈值的 pending 任务 → 重新派发
    stale = enqueue_job(db_session, kind="entity_extraction", payload={"text": "x"}, user_id="u1")
    stale.created_at = datetime.now(UTC) - timedelta(minutes=10)
    stale.updated_at = datetime.now(UTC) - timedelta(minutes=10)
    db_session.commit()

    # 一个 attempts 打满的 stale 任务 → 标记 failed
    exhausted = enqueue_job(
        db_session, kind="entity_extraction", payload={"text": "y"}, user_id="u1"
    )
    exhausted.created_at = datetime.now(UTC) - timedelta(minutes=10)
    exhausted.updated_at = datetime.now(UTC) - timedelta(minutes=10)
    exhausted.attempts = MAX_ATTEMPTS
    db_session.commit()

    container = _make_container(db_session)
    with MagicMock() as enqueue_task_mock:
        from unittest.mock import patch

        with patch(
            "app.infrastructure.task_queue.enqueue_task", enqueue_task_mock
        ):
            requeued = requeue_stale_jobs(container)
        assert requeued == 1  # 只有 stale 被重新派发

    db_session.expire_all()
    stale = db_session.query(JobRow).filter(JobRow.id == stale.id).first()
    exhausted = db_session.query(JobRow).filter(JobRow.id == exhausted.id).first()
    assert stale is not None and stale.status == "pending"
    assert exhausted is not None and exhausted.status == "failed"
    assert "max attempts" in (exhausted.error or "")


def test_enqueue_and_dispatch_records_job(db_session):
    from unittest.mock import patch

    container = _make_container(db_session)
    with MagicMock() as enqueue_task_mock:
        with patch(
            "app.infrastructure.task_queue.enqueue_task", enqueue_task_mock
        ):
            job = enqueue_and_dispatch(
                container,
                kind="entity_extraction",
                payload={"text": "abc", "user_id": "u1"},
                user_id="u1",
            )
        assert job is not None
        assert job.status == "pending"
        enqueue_task_mock.assert_called_once()


def test_enqueue_and_dispatch_returns_none_without_factory(db_session):
    container = MagicMock()
    container.session_factory = None
    job = enqueue_and_dispatch(container, kind="entity_extraction", payload={})
    assert job is None


def test_unknown_job_kind_runs_to_failed(db_session):
    """未知 kind 的 job 被 runner 标为 failed（不静默丢失）。"""
    from app.services.job_service import _run_job

    row = enqueue_job(db_session, kind="no_such_kind", payload={}, user_id="u1")
    _run_job(_make_container(db_session).session_factory, row.id)
    db_session.expire_all()
    row = db_session.query(JobRow).filter(JobRow.id == row.id).first()
    assert row is not None
    assert row.status == "failed"
    assert "unknown kind" in (row.error or "")


def test_entity_extraction_job_flow(db_session):
    """entity_extraction job 完整闭环：pending → running → done。"""
    from unittest.mock import patch

    from app.services.job_service import _run_job

    row = enqueue_job(
        db_session,
        kind="entity_extraction",
        payload={
            "user_id": "u1",
            "conversation_id": "c1",
            "text": "今天见到李总",
            "source_label": "diary",
        },
        user_id="u1",
    )
    # 隔离真实提取（Neo4j/知识库），仅验证 job 状态机
    with patch(
        "app.services.job_service._job_handler",
        return_value=lambda *a, **k: None,
    ):
        _run_job(_make_container(db_session).session_factory, row.id)
    db_session.expire_all()
    row = db_session.query(JobRow).filter(JobRow.id == row.id).first()
    assert row is not None
    assert row.status == "done"
