"""Unit tests for digest_worker — day-level digest rebuild for typed entries."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.services import diary_service, digest_service
from app.services import digest_worker as dw
from app.shared.digest import CardDigest, DiaryDigest


def _make_entry(
    user_id: str,
    day: date,
    content: str,
    created_at: datetime | None = None,
) -> DiaryEntryRow:
    entry = DiaryEntryRow(
        user_id=user_id,
        content=content,
        date=day,
        created_at=created_at or datetime(2026, 9, 2, 12, 0, 0),
    )
    entry.id = 1
    return entry


@pytest.fixture()
def frozen_entries(db_session):
    def _add(user_id: str, day: date, contents: list[str]) -> list[DiaryEntryRow]:
        rows = []
        for i, text in enumerate(contents):
            entry = DiaryEntryRow(
                user_id=user_id,
                content=text,
                date=day,
                created_at=datetime(2026, 9, 2, 10 + i, 0, 0),
            )
            db_session.add(entry)
            rows.append(entry)
        db_session.commit()
        for row in rows:
            db_session.refresh(row)
        return rows

    return _add


# ── run_day_digest_refresh ──────────────────────────────────────────────


def test_worker_aggregates_all_day_entries(db_session, frozen_entries) -> None:
    day = date(2026, 9, 2)
    entries = frozen_entries("u1", day, ["上午跑了五公里。", "下午读了一章书。"])
    content_seen: list[str] = []

    def fake_run(content: str, **kwargs: object) -> object:
        content_seen.append(content)
        outcome = MagicMock()
        outcome.digest = DiaryDigest(digest_type="basic", date=day, source="llm")
        return outcome

    container = MagicMock()
    container._llm_for_tier.return_value = MagicMock()
    with (
        patch.object(dw, "_build_container", return_value=container),
        patch.object(dw, "_get_session_factory", lambda: (lambda: db_session)),
        patch("app.services.ai.treehole.run_treehole", side_effect=fake_run),
        patch("app.services.ai.treehole.detect_crisis", return_value=False),
    ):
        dw.run_day_digest_refresh("u1", "2026-09-02", entries[1].id)

    assert len(content_seen) == 1
    assert "上午跑了五公里。" in content_seen[0]
    assert "下午读了一章书。" in content_seen[0]
    assert dw._CONTENT_SEPARATOR in content_seen[0]


def test_worker_single_entry_no_separator(db_session, frozen_entries) -> None:
    day = date(2026, 9, 2)
    entries = frozen_entries("u1", day, ["只有一篇日记。"])
    content_seen: list[str] = []

    def fake_run(content: str, **kwargs: object) -> object:
        content_seen.append(content)
        outcome = MagicMock()
        outcome.digest = DiaryDigest(digest_type="basic", date=day, source="llm")
        return outcome

    container = MagicMock()
    container._llm_for_tier.return_value = MagicMock()
    with (
        patch.object(dw, "_build_container", return_value=container),
        patch.object(dw, "_get_session_factory", lambda: (lambda: db_session)),
        patch("app.services.ai.treehole.run_treehole", side_effect=fake_run),
        patch("app.services.ai.treehole.detect_crisis", return_value=False),
    ):
        dw.run_day_digest_refresh("u1", "2026-09-02", entries[0].id)

    assert content_seen == ["只有一篇日记。"]


def test_worker_clears_diary_section_when_no_entries(db_session) -> None:
    day = date(2026, 9, 2)
    digest_service.upsert_digest(
        db_session,
        user_id="u1",
        day=day,
        digest=DiaryDigest(
            digest_type="complex",
            date=day,
            source="llm",
            cards=[CardDigest(emotion="开心", summary="卡片")],
        ),
    )
    db_session.commit()

    with (
        patch.object(dw, "_build_container", return_value=None),
        patch.object(dw, "_get_session_factory", lambda: (lambda: db_session)),
    ):
        dw.run_day_digest_refresh("u1", "2026-09-02", 999)

    stored = digest_service.get_digest(db_session, user_id="u1", day=day)
    assert stored is not None
    assert stored.diary.summary == ""
    assert stored.cards and stored.cards[0].summary == "卡片"
    assert stored.source == "card"


def test_worker_preserves_cards_section(db_session, frozen_entries) -> None:
    day = date(2026, 9, 2)
    entries = frozen_entries("u1", day, ["今天的日记内容。"])
    cards = [CardDigest(emotion="平静", tags=["阅读"], summary="读书卡片")]
    digest_service.upsert_digest(
        db_session,
        user_id="u1",
        day=day,
        digest=DiaryDigest(digest_type="basic", date=day, source="card", cards=cards),
    )
    db_session.commit()

    def fake_run(content: str, **kwargs: object) -> object:
        outcome = MagicMock()
        # LLM outcome with EMPTY cards — preservation must restore them.
        digest = DiaryDigest(digest_type="basic", date=day, source="llm", cards=[])
        digest.diary.summary = "今天写了日记"
        outcome.digest = digest
        return outcome

    container = MagicMock()
    container._llm_for_tier.return_value = MagicMock()
    with (
        patch.object(dw, "_build_container", return_value=container),
        patch.object(dw, "_get_session_factory", lambda: (lambda: db_session)),
        patch("app.services.ai.treehole.run_treehole", side_effect=fake_run),
        patch("app.services.ai.treehole.detect_crisis", return_value=False),
    ):
        dw.run_day_digest_refresh("u1", "2026-09-02", entries[0].id)

    stored = digest_service.get_digest(db_session, user_id="u1", day=day)
    assert stored is not None
    assert stored.cards and stored.cards[0].summary == "读书卡片"
    assert stored.source == "card+llm"


def test_worker_falls_back_to_rules_without_llm(db_session, frozen_entries) -> None:
    day = date(2026, 9, 2)
    frozen_entries("u1", day, ["今天有点累，但完成了任务。"])

    container = MagicMock()
    container._llm_for_tier.return_value = None
    with (
        patch.object(dw, "_build_container", return_value=container),
        patch.object(dw, "_get_session_factory", lambda: (lambda: db_session)),
        patch("app.services.ai.treehole.detect_crisis", return_value=False),
    ):
        dw.run_day_digest_refresh("u1", "2026-09-02", 1)

    stored = digest_service.get_digest(db_session, user_id="u1", day=day)
    assert stored is not None
    assert stored.source == "rule"


def test_worker_crisis_short_circuits(db_session, frozen_entries) -> None:
    day = date(2026, 9, 2)
    frozen_entries("u1", day, ["我不想活了，太痛苦了。"])

    with (
        patch.object(dw, "_build_container", return_value=None),
        patch.object(dw, "_get_session_factory", lambda: (lambda: db_session)),
        patch("app.services.ai.treehole.detect_crisis", return_value=True),
    ):
        dw.run_day_digest_refresh("u1", "2026-09-02", 1)

    stored = digest_service.get_digest(db_session, user_id="u1", day=day)
    assert stored is not None
    assert stored.diary.intent == "crisis_signal"


def test_worker_dispatches_memory_sync(db_session, frozen_entries) -> None:
    day = date(2026, 9, 2)
    entries = frozen_entries("u1", day, ["值得记住的一天。"])
    entry_ids: list[int] = []

    def fake_sync(entry: object, reply: str, container: object, digest: object) -> None:
        entry_ids.append(int(entry.id))

    container = MagicMock()
    container._llm_for_tier.return_value = None

    def fake_run(content: str, **kwargs: object) -> object:
        outcome = MagicMock()
        digest = DiaryDigest(digest_type="basic", date=day, source="llm")
        digest.diary.summary = "值得记住的一天"
        outcome.digest = digest
        return outcome

    with (
        patch.object(dw, "_build_container", return_value=container),
        patch.object(dw, "_get_session_factory", lambda: (lambda: db_session)),
        patch("app.services.ai.treehole.detect_crisis", return_value=False),
        patch.object(dw, "_resolve_llm", return_value=MagicMock()),
        patch("app.services.ai.treehole.run_treehole", side_effect=fake_run),
        patch(
            "app.services.analysis_service._sync_diary_to_memory",
            side_effect=fake_sync,
        ),
    ):
        dw.run_day_digest_refresh("u1", "2026-09-02", entries[0].id)

    assert entry_ids == [entries[0].id]


def test_worker_invalid_day_is_noop(db_session) -> None:
    from app.infrastructure.models.diary_entry import DiaryEntryRow

    with patch.object(dw, "_build_container", return_value=None):
        dw.run_day_digest_refresh("u1", "not-a-date", 1)
    stored = db_session.query(DiaryEntryRow).count()
    assert stored == 0


def test_worker_never_raises_on_internal_error(db_session) -> None:
    with (
        patch.object(dw, "_build_container", return_value=None),
        patch.object(dw, "_get_session_factory", side_effect=RuntimeError("db down")),
    ):
        dw.run_day_digest_refresh("u1", "2026-09-02", 1)


# ── schedule_day_digest_refresh ────────────────────────────────────────


def test_schedule_deduplicates_in_flight(db_session) -> None:
    enqueued: list[tuple[str, str, int]] = []

    def fake_enqueue(func: str, *args: object) -> str:
        enqueued.append((func, args[0], args[1]))  # type: ignore[index]
        return "job-1"

    with (
        patch("app.infrastructure.task_queue.enqueue_task", side_effect=fake_enqueue),
        patch.object(dw, "_release_in_flight", lambda *a: None),
    ):
        dw.schedule_day_digest_refresh("u1", "2026-09-02", 1)
        second = dw.schedule_day_digest_refresh("u1", "2026-09-02", 2)

    assert len(enqueued) == 1
    assert second is None


def test_schedule_releases_key_when_enqueue_fails() -> None:
    calls: list[str] = []

    def broken_enqueue(func: str, *args: object) -> str:
        calls.append(func)
        raise RuntimeError("queue down")

    with patch(
        "app.infrastructure.task_queue.enqueue_task", side_effect=broken_enqueue
    ):
        dw.schedule_day_digest_refresh("u2", "2026-09-03", 1)
        # Key must have been released: a second call retries instead of dedup.
        result = dw.schedule_day_digest_refresh("u2", "2026-09-03", 1)

    assert len(calls) == 2
    assert result is None


def test_schedule_different_days_not_deduped() -> None:
    enqueued: list[str] = []

    def fake_enqueue(func: str, *args: object) -> str:
        enqueued.append(str(args[1]))
        return "job"

    with patch(
        "app.infrastructure.task_queue.enqueue_task", side_effect=fake_enqueue
    ):
        dw.schedule_day_digest_refresh("u3", "2026-09-02", 1)
        dw.schedule_day_digest_refresh("u3", "2026-09-03", 1)

    assert enqueued == ["2026-09-02", "2026-09-03"]


# ── diary_service wiring ───────────────────────────────────────────────


def test_create_entry_schedules_digest_refresh(db_session) -> None:
    scheduled: list[tuple[str, str, int]] = []

    def fake_schedule(user_id: str, day: str, diary_id: int) -> None:
        scheduled.append((user_id, day, diary_id))

    with patch(
        "app.services.digest_worker.schedule_day_digest_refresh",
        side_effect=fake_schedule,
    ):
        entry = diary_service_create(db_session, container=object())

    assert scheduled and scheduled[0][0] == "default"
    assert scheduled[0][1] == entry.date.isoformat()
    assert scheduled[0][2] == entry.id


def test_create_entry_without_container_skips(db_session) -> None:
    with patch(
        "app.services.digest_worker.schedule_day_digest_refresh"
    ) as mock_schedule:
        diary_service_create(db_session, container=None)

    mock_schedule.assert_not_called()


def test_update_entry_schedules_refresh(db_session) -> None:
    entry = diary_service.create_entry(
        db_session, user_id="default", content="原始内容。"
    )
    with patch(
        "app.services.digest_worker.schedule_day_digest_refresh"
    ) as mock_schedule:
        diary_service.update_entry(
            db_session,
            entry.id,
            user_id="default",
            content="修改后的内容。",
            container=object(),
        )

    mock_schedule.assert_called_once()


def test_delete_entry_schedules_refresh(db_session) -> None:
    entry = diary_service.create_entry(
        db_session, user_id="default", content="待删除。"
    )
    with patch(
        "app.services.digest_worker.schedule_day_digest_refresh"
    ) as mock_schedule:
        diary_service.delete_entry(
            db_session, entry.id, user_id="default", container=object()
        )

    mock_schedule.assert_called_once()


# ── record skill wiring ────────────────────────────────────────────────


def test_record_skill_passes_container_to_create(db_session) -> None:
    from app.domain.skills import record_skill

    with patch(
        "app.domain.skills.record_skill.diary_service.create_entry",
        return_value=_make_entry("default", date(2026, 9, 2), "内容"),
    ) as mock_create:
        record_skill.run(
            db_session,
            llm=None,
            content="记一下今天的跑步。",
            user_id="default",
            container=object(),
        )

    kwargs = mock_create.call_args.kwargs
    assert kwargs.get("container") is not None


# ── helpers ────────────────────────────────────────────────────────────


def diary_service_create(db_session, container):
    from app.services import diary_service as ds

    return ds.create_entry(
        db_session,
        user_id="default",
        content="今天写下新的一篇。",
        container=container,
    )


