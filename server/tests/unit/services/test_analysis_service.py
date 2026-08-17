"""Unit tests for analysis_service orchestration."""

from __future__ import annotations

import pytest

from app.services import analysis_service, diary_service
from app.services.ai.router import ExecutionPlanner
from app.shared.errors import AnalysisNotFoundError, AnalysisUnchangedError, DiaryAlreadyExistsError
from app.shared.llm_factory import StubLLMClient
from app.shared.tracing import InMemoryAgentDecisionLogger


def _planner() -> ExecutionPlanner:
    return ExecutionPlanner(
        llm_by_tier={
            "light": StubLLMClient(),
            "medium": StubLLMClient(),
            "default": StubLLMClient(),
        },
        decision_logger=InMemoryAgentDecisionLogger(),
        multi_agent_enabled=False,
    )


class _FakeContainer:
    def __init__(self, planner: ExecutionPlanner) -> None:
        self._planner = planner

    def build_execution_planner(self, *, user_id: str = "default") -> ExecutionPlanner:
        return self._planner


def test_create_analysis_persists_result(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="今天工作很累。")
    analysis, mem_count = analysis_service.create_analysis(
        db_session, entry.id, user_id="default", planner=_planner()
    )

    assert analysis.id is not None
    assert analysis.diary_id == entry.id
    db_session.refresh(entry)
    assert entry.reply
    assert analysis.execution_tier
    assert mem_count == 0  # no episodic memory in stub planner


def test_create_analysis_rejects_duplicate(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="重复分析测试")
    analysis_service.create_analysis(db_session, entry.id, user_id="default", planner=_planner())
    with pytest.raises(DiaryAlreadyExistsError):
        analysis_service.create_analysis(
            db_session, entry.id, user_id="default", planner=_planner()
        )


def test_update_analysis_rejects_unchanged_content(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="固定内容")
    analysis_service.create_analysis(db_session, entry.id, user_id="default", planner=_planner())
    with pytest.raises(AnalysisUnchangedError):
        analysis_service.update_analysis(
            db_session, entry.id, user_id="default", planner=_planner()
        )


def test_regenerate_analysis_replaces_existing(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="重新生成测试")
    first, _ = analysis_service.create_analysis(
        db_session, entry.id, user_id="default", planner=_planner()
    )
    second, _ = analysis_service.regenerate_analysis(
        db_session,
        entry.id,
        user_id="default",
        container=_FakeContainer(_planner()),
    )
    assert second.diary_id == entry.id
    db_session.refresh(entry)
    assert entry.reply
    from app.infrastructure.models.analysis import AnalysisRow

    assert db_session.query(AnalysisRow).filter_by(diary_id=entry.id).count() == 1
    assert db_session.query(type(first)).filter_by(diary_id=entry.id).count() == 1


def test_delete_analysis_for_diary_clears_reply(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="删除分析测试")
    analysis_service.create_analysis(db_session, entry.id, user_id="default", planner=_planner())
    assert (
        analysis_service.delete_analysis_for_diary(db_session, entry.id, user_id="default") is True
    )
    db_session.refresh(entry)
    assert entry.reply is None
    with pytest.raises(AnalysisNotFoundError):
        analysis_service.get_analysis(db_session, entry.id, user_id="default")


# ── trigger_analysis_streaming (V3 P4 Task 3) ──────────────────────────


@pytest.mark.asyncio
async def test_trigger_analysis_streaming_publishes_events(
    db_session, stub_container
):
    """trigger_analysis_streaming 应发布 REPLY_START/TEXT_DELTA/REPLY_END。"""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-scene1-stream"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    async def mock_run_streaming(*, graph, state, workers=None):
        for token in ["你", "好"]:
            yield token

    mock_graph = MagicMock()
    mock_state = MagicMock()
    with patch.object(
        analysis_service, "_prepare_analysis_graph",
        new_callable=AsyncMock, return_value=(mock_graph, mock_state),
    ), patch(
        "app.services.ai.multi_agent_executor.run_multi_agent_streaming",
        side_effect=mock_run_streaming,
    ), patch.object(
        analysis_service, "_persist_analysis_streaming"
    ):
        await analysis_service.trigger_analysis_streaming(
            db=db_session, container=stub_container,
            diary_id=1, user_id="user-1", trace_id=trace_id,
        )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    types = [e.get("type") for e in events]
    assert StreamingEventType.REPLY_START in types, f"Missing REPLY_START in {types}"
    assert StreamingEventType.TEXT_END in types
    assert StreamingEventType.REPLY_END in types
    deltas = [e for e in events if e.get("type") == StreamingEventType.TEXT_DELTA]
    delta_texts = "".join(d.get("text", "") for d in deltas)
    assert "你" in delta_texts and "好" in delta_texts


@pytest.mark.asyncio
async def test_trigger_analysis_streaming_persists_analysis(
    db_session, stub_container
):
    """流式结束后应调 _persist_analysis_streaming。"""
    from unittest.mock import AsyncMock, MagicMock, patch

    trace_id = "test-scene1-persist"

    async def mock_run_streaming(*, graph, state, workers=None):
        yield "测试回复"

    with patch.object(
        analysis_service, "_prepare_analysis_graph",
        new_callable=AsyncMock, return_value=(MagicMock(), MagicMock()),
    ), patch(
        "app.services.ai.multi_agent_executor.run_multi_agent_streaming",
        side_effect=mock_run_streaming,
    ), patch.object(
        analysis_service, "_persist_analysis_streaming"
    ) as mock_persist:
        await analysis_service.trigger_analysis_streaming(
            db=db_session, container=stub_container,
            diary_id=1, user_id="user-1", trace_id=trace_id,
        )
        assert mock_persist.called
        call_kwargs = mock_persist.call_args.kwargs
        assert call_kwargs.get("reply_text") == "测试回复"


@pytest.mark.asyncio
async def test_trigger_analysis_streaming_guarantees_reply_end(
    db_session, stub_container
):
    """LLM 失败时仍应发 REPLY_END(P1 终止保证)。"""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-scene1-fail"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    async def mock_run_streaming(*, graph, state, workers=None):
        raise RuntimeError("LLM down")
        yield  # 让它成为 async generator

    with patch.object(
        analysis_service, "_prepare_analysis_graph",
        new_callable=AsyncMock, return_value=(MagicMock(), MagicMock()),
    ), patch(
        "app.services.ai.multi_agent_executor.run_multi_agent_streaming",
        side_effect=mock_run_streaming,
    ):
        await analysis_service.trigger_analysis_streaming(
            db=db_session, container=stub_container,
            diary_id=1, user_id="user-1", trace_id=trace_id,
        )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    types = [e.get("type") for e in events]
    assert StreamingEventType.REPLY_END in types, f"REPLY_END must be sent on failure: {types}"


# ── V3 P7: streaming memory write-back (gap fix regression) ────────────


@pytest.mark.asyncio
async def test_trigger_analysis_streaming_dispatches_memory_write_back(db_session):
    """V3 P7：流式分析完成后应调度 episodic 记忆写回（修复缺口回归）。

    The sync paths (create_analysis / update_analysis) persist the diary
    event into episodic memory via _sync_diary_to_memory; the streaming path
    previously did not. FinalizeMiddleware must dispatch persist_atom.
    """
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.infrastructure.models.diary_entry import DiaryEntryRow

    entry = DiaryEntryRow(
        user_id="user-1",
        content="今天加班很晚，有点焦虑",
        date=date(2026, 8, 12),
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    async def mock_run_streaming(*, graph, state, workers=None):
        yield "注意休息，别太累。"
        yield "明天会好起来的。"

    container = MagicMock()
    container.episodic_memory = object()  # 非 None：记忆层可用
    container.long_term_memory = None

    with patch.object(
        analysis_service, "_prepare_analysis_graph",
        new_callable=AsyncMock, return_value=(MagicMock(), MagicMock()),
    ), patch(
        "app.services.ai.multi_agent_executor.run_multi_agent_streaming",
        side_effect=mock_run_streaming,
    ), patch.object(
        analysis_service, "_persist_analysis_streaming"
    ), patch(
        "app.infrastructure.task_queue.enqueue_task"
    ) as mock_enqueue:
        await analysis_service.trigger_analysis_streaming(
            db=db_session, container=container,
            diary_id=entry.id, user_id="user-1", trace_id="test-scene1-writeback",
        )

    assert mock_enqueue.called
    args = mock_enqueue.call_args.args
    assert callable(args[0]) and args[0].__name__ == "persist_atom"
    assert args[1].source == "diary"
    assert "加班" in args[1].event_summary
