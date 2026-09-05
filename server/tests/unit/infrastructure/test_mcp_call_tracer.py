"""Unit tests for mcp_call_logs persistence."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.mcp_call_tracer import McpCallRecord, McpCallTracer, list_calls


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _record(**overrides: object) -> McpCallRecord:
    fields: dict[str, object] = {
        "user_id": "u1",
        "trace_id": "t1",
        "span_id": "s1",
        "endpoint_alias": "tavily",
        "transport": "stdio",
        "tool_name": "mcp__tavily__search",
        "raw_tool_name": "search",
        "status": "success",
        "duration_ms": 123.0,
        "error_message": None,
        "arguments_snapshot": '{"query": "x"}',
        "result_snapshot": "ok",
    }
    fields.update(overrides)
    return McpCallRecord(**fields)  # type: ignore[arg-type]


class TestRecord:
    def test_writes_row(self, session_factory) -> None:
        tracer = McpCallTracer(session_factory)
        tracer.record(_record())
        with session_factory() as db:
            items, total = list_calls(db)
        assert total == 1
        assert items[0]["tool_name"] == "mcp__tavily__search"
        assert items[0]["user_id"] == "u1"

    def test_truncates_snapshots_to_2kb(self, session_factory) -> None:
        tracer = McpCallTracer(session_factory)
        big = "x" * 5000
        tracer.record(_record(arguments_snapshot=big, result_snapshot=big))
        with session_factory() as db:
            items, _ = list_calls(db)
        assert len(items[0]["arguments_snapshot"]) == 2048
        assert len(items[0]["result_snapshot"]) == 2048

    def test_write_failure_never_raises(self) -> None:
        class _BrokenFactory:
            def __call__(self):
                raise RuntimeError("db down")

        tracer = McpCallTracer(_BrokenFactory())  # type: ignore[arg-type]
        tracer.record(_record())  # must not raise


class TestListCalls:
    @pytest.fixture()
    def filled(self, session_factory):
        tracer = McpCallTracer(session_factory)
        tracer.record(_record(status="success", endpoint_alias="a", user_id="u1"))
        tracer.record(_record(status="error", endpoint_alias="b", user_id="u2"))
        tracer.record(_record(status="timeout", endpoint_alias="a", user_id="u1"))
        return session_factory

    def test_filters_and_pagination(self, filled) -> None:
        with filled() as db:
            assert list_calls(db, endpoint="a")[1] == 2
            assert list_calls(db, status="error")[1] == 1
            assert list_calls(db, user_id="u2")[1] == 1
            items, total = list_calls(db, page=1, page_size=2)
        assert total == 3
        assert len(items) == 2

    def test_empty(self, session_factory) -> None:
        with session_factory() as db:
            items, total = list_calls(db)
        assert items == []
        assert total == 0
