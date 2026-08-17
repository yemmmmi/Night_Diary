"""Replayable background-job service (robustness P2-6).

Fire-and-forget sidecars are recorded as durable ``jobs`` rows before being
dispatched to the task queue, so a process crash/restart does not silently
lose them. On startup :func:`requeue_stale_jobs` re-dispatches jobs that
were left ``pending``/``running`` by a dead process (bounded retries).

Job kinds and handlers:
- ``entity_extraction`` → :func:`app.domain.agents.entity_extractor._run_extraction_sync`
  (payload: user_id, conversation_id, text, source_label)

All functions are best-effort — a failed job row write must never break the
caller's main flow.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.models.job import JobRow

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
STALE_AFTER_S = 300  # pending/running longer than this (dead process) → requeue


# ── CRUD ────────────────────────────────────────────────────────────────


def enqueue_job(
    db: Session,
    *,
    kind: str,
    payload: dict[str, Any],
    user_id: str = "default",
) -> JobRow:
    """Insert a pending job row (durable before dispatch)."""
    row = JobRow(
        user_id=user_id,
        kind=kind,
        payload_json=json.dumps(payload, ensure_ascii=False, default=str),
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def claim_job(db: Session, job_id: str) -> JobRow | None:
    """Mark a pending job as running (returns None if already claimed)."""
    row = db.query(JobRow).filter(JobRow.id == job_id).first()
    if row is None or row.status != "pending":
        return None
    row.status = "running"
    row.attempts += 1
    db.commit()
    db.refresh(row)
    return row


def finish_job(
    db: Session, job_id: str, *, status: str = "done", error: str | None = None
) -> None:
    """Mark a job done/failed (failed keeps the error for observability)."""
    row = db.query(JobRow).filter(JobRow.id == job_id).first()
    if row is None:
        return
    row.status = status
    row.error = (error or "")[:2000] if error else None
    db.commit()


# ── Dispatch & runner ────────────────────────────────────────────────────


def _job_handler(kind: str) -> Any:
    """Return the callable that runs a job's payload, or None for unknown kinds."""
    if kind == "entity_extraction":
        from app.domain.agents.entity_extractor import _run_extraction_sync

        return _run_extraction_sync
    return None


def _run_job(session_factory: Any, job_id: str) -> None:
    """Run one job (background thread). Claim → handler → finish, all safe."""
    try:
        with session_factory() as db:
            job = claim_job(db, job_id)
            if job is None:
                return
            # Capture plain values before the session closes (accessing the
            # ORM object after ``with`` exit would lazy-refresh a detached
            # instance and raise).
            kind = job.kind
            payload = json.loads(job.payload_json or "{}")
            handler = _job_handler(kind)
            if handler is None:
                finish_job(db, job_id, status="failed", error=f"unknown kind {kind}")
                return
            db.commit()  # release claim before the long handler runs
        if kind == "entity_extraction":
            handler(
                session_factory,
                str(payload.get("user_id", "default")),
                str(payload.get("conversation_id", "")),
                str(payload.get("text", "")),
                str(payload.get("source_label", "conversation")),
            )
        with session_factory() as db:
            finish_job(db, job_id, status="done")
    except Exception as exc:
        logger.warning("Job %s failed: %s", job_id, exc)
        try:
            with session_factory() as db:
                finish_job(db, job_id, status="failed", error=str(exc))
        except Exception as inner:
            logger.warning("Failed to record job failure %s: %s", job_id, inner)


def dispatch_job(container: Any, job: JobRow) -> None:
    """Dispatch a job row to the background queue (fire-and-forget)."""
    from app.infrastructure.task_queue import enqueue_task

    session_factory = getattr(container, "session_factory", None)
    if session_factory is None:
        return
    enqueue_task(_run_job, session_factory, job.id)


def enqueue_and_dispatch(
    container: Any,
    *,
    kind: str,
    payload: dict[str, Any],
    user_id: str = "default",
) -> JobRow | None:
    """Record a durable job row then dispatch it (best-effort, never raises).

    Returns the job row, or ``None`` when the container has no session
    factory (e.g. degraded) — the caller falls back to plain fire-and-forget.
    """
    session_factory = getattr(container, "session_factory", None)
    if session_factory is None:
        return None
    try:
        with session_factory() as db:
            job = enqueue_job(db, kind=kind, payload=payload, user_id=user_id)
        dispatch_job(container, job)
        return job
    except Exception as exc:
        logger.warning("Job enqueue failed (fall back to plain dispatch): %s", exc)
        return None


# ── Startup compensation ─────────────────────────────────────────────────


def requeue_stale_jobs(
    container: Any,
    *,
    stale_after_s: int = STALE_AFTER_S,
    max_attempts: int = MAX_ATTEMPTS,
) -> int:
    """Re-dispatch jobs left pending/running by a dead process.

    Called on startup: jobs that never finished are re-queued (bounded by
    ``max_attempts``); exhausted jobs are marked failed. Returns the number
    of re-queued jobs.
    """
    session_factory = getattr(container, "session_factory", None)
    if session_factory is None:
        return 0
    requeued = 0
    try:
        with session_factory() as db:
            cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_s)
            stale = (
                db.query(JobRow)
                .filter(
                    JobRow.status.in_(("pending", "running")),
                    JobRow.updated_at < cutoff,
                )
                .all()
            )
            for job in stale:
                if job.attempts >= max_attempts:
                    job.status = "failed"
                    job.error = "max attempts reached after restart"
                else:
                    job.status = "pending"
                    requeued += 1
            db.commit()
            stale_ids = [j.id for j in stale]
        for job_id in stale_ids:
            with session_factory() as db:
                job = db.query(JobRow).filter(JobRow.id == job_id).first()
                if job is not None and job.status == "pending":
                    dispatch_job(container, job)
    except Exception as exc:
        logger.warning("Requeue stale jobs failed (best-effort): %s", exc)
    if requeued:
        logger.info("Requeued %d stale job(s) after restart", requeued)
    return requeued


__all__ = [
    "MAX_ATTEMPTS",
    "STALE_AFTER_S",
    "claim_job",
    "dispatch_job",
    "enqueue_and_dispatch",
    "enqueue_job",
    "finish_job",
    "requeue_stale_jobs",
]
