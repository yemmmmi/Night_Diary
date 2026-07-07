"""Unit tests for ``app.shared.pipeline_trace``.

Covers:
- ``truncate_snapshot``: long string, short string, dict keys, list items, nesting.
- ``PipelineTrace`` / ``TraceSpan``: start/end span, nested spans, end trace,
  ``to_dict`` serialization, span error recording.
- ``trace_span`` context manager: zero-overhead when no trace, error recording.
"""

from __future__ import annotations

import pytest

from app.shared.pipeline_trace import (
    PipelineTrace,
    TraceSpan,
    get_trace,
    reset_trace,
    set_trace,
    trace_span,
    truncate_snapshot,
)

# ── truncate_snapshot ────────────────────────────────────────────────────


class TestTruncateSnapshot:
    """Tests for the recursive snapshot truncation helper."""

    def test_long_string_truncated(self) -> None:
        long_str = "a" * 1000
        result = truncate_snapshot(long_str, max_str=500)
        assert isinstance(result, str)
        assert len(result) < 1000
        assert result.startswith("a" * 500)
        assert "truncated" in result
        assert "1000" in result  # original length mentioned

    def test_short_string_preserved(self) -> None:
        short_str = "hello world"
        result = truncate_snapshot(short_str, max_str=500)
        assert result == short_str

    def test_exact_max_string_preserved(self) -> None:
        exact_str = "x" * 500
        result = truncate_snapshot(exact_str, max_str=500)
        assert result == exact_str

    def test_dict_keys_truncated(self) -> None:
        big_dict = {f"key_{i}": f"val_{i}" for i in range(25)}
        result = truncate_snapshot(big_dict, max_dict_keys=20)
        assert isinstance(result, dict)
        # Only 20 real keys + 1 truncation marker = 21 entries
        assert len(result) == 21
        assert "__truncated__" in result
        assert "5 more keys" in result["__truncated__"]
        # First 20 keys are preserved
        for i in range(20):
            assert f"key_{i}" in result

    def test_small_dict_preserved(self) -> None:
        small_dict = {"a": 1, "b": 2}
        result = truncate_snapshot(small_dict, max_dict_keys=20)
        assert result == small_dict

    def test_list_truncated(self) -> None:
        big_list = list(range(10))
        result = truncate_snapshot(big_list, max_list_items=3)
        assert isinstance(result, list)
        # 3 real items + 1 truncation marker = 4 entries
        assert len(result) == 4
        assert result[:3] == [0, 1, 2]
        assert "7 more items" in result[3]

    def test_small_list_preserved(self) -> None:
        small_list = [1, 2, 3]
        result = truncate_snapshot(small_list, max_list_items=3)
        assert result == small_list

    def test_nested_dict_with_long_string(self) -> None:
        nested = {
            "prompt": "a" * 1000,
            "meta": {"inner": "b" * 1000},
        }
        result = truncate_snapshot(nested, max_str=500, max_dict_keys=20)
        assert isinstance(result, dict)
        assert isinstance(result["prompt"], str)
        assert len(result["prompt"]) < 1000
        assert "truncated" in result["prompt"]
        assert isinstance(result["meta"], dict)
        assert "truncated" in result["meta"]["inner"]

    def test_nested_list_with_dicts(self) -> None:
        nested = [
            {"text": "a" * 1000},
            {"text": "short"},
            {"text": "c" * 1000},
            {"text": "d" * 1000},
            {"text": "e" * 1000},
        ]
        result = truncate_snapshot(nested, max_str=500, max_list_items=3, max_dict_keys=20)
        assert isinstance(result, list)
        assert len(result) == 4  # 3 items + 1 marker
        # Each dict in the list should have its long string truncated
        assert "truncated" in result[0]["text"]
        assert result[1]["text"] == "short"
        assert "truncated" in result[2]["text"]

    def test_non_collection_types_returned_as_is(self) -> None:
        assert truncate_snapshot(42) == 42
        assert truncate_snapshot(3.14) == 3.14
        assert truncate_snapshot(True) is True
        assert truncate_snapshot(None) is None

    def test_custom_parameters(self) -> None:
        long_str = "x" * 100
        result = truncate_snapshot(long_str, max_str=10)
        assert len(result) < 100
        assert "100" in result

    def test_empty_collections(self) -> None:
        assert truncate_snapshot({}) == {}
        assert truncate_snapshot([]) == []


# ── PipelineTrace / TraceSpan ──────────────────────────────────────────


class TestPipelineTrace:
    """Tests for the PipelineTrace and TraceSpan data structures."""

    def test_start_and_end_span(self) -> None:
        trace = PipelineTrace(scenario="test_scenario", user_id="user-1")
        span = trace.start_span("retrieve", stage_label="Retrieval")
        assert span.stage_name == "retrieve"
        assert span.stage_label == "Retrieval"
        assert span.status == "running"
        assert span.span_id  # auto-generated UUID
        assert span in trace.spans
        assert span in trace._span_stack

        ended = trace.end_span()
        assert ended is span
        assert span.status == "completed"
        assert span.ended_at is not None
        assert span.duration_ms >= 0.0
        assert len(trace._span_stack) == 0

    def test_start_span_with_input_snapshot(self) -> None:
        trace = PipelineTrace()
        span = trace.start_span("generate", input_snapshot={"query": "hello" * 200})
        # Input snapshot should be truncated
        assert isinstance(span.input_snapshot, dict)
        assert "truncated" in span.input_snapshot["query"]
        trace.end_span()

    def test_nested_spans(self) -> None:
        trace = PipelineTrace(scenario="nested_test")
        parent = trace.start_span("parent")
        child1 = trace.start_span("child_1")
        child2 = trace.start_span("child_2")

        # All three on the stack
        assert trace._span_stack == [parent, child1, child2]

        # child2 nests under child1, child1 nests under parent
        assert child2 in child1.child_spans
        assert child1 in parent.child_spans
        # parent is a top-level span
        assert parent in trace.spans
        assert len(trace.spans) == 1

        # End in reverse order
        trace.end_span()  # child2
        assert child2.status == "completed"
        assert len(trace._span_stack) == 2

        trace.end_span()  # child1
        assert child1.status == "completed"
        assert len(trace._span_stack) == 1

        trace.end_span()  # parent
        assert parent.status == "completed"
        assert len(trace._span_stack) == 0

    def test_nested_spans_structure(self) -> None:
        """Verify the tree structure after all spans are ended."""
        trace = PipelineTrace()
        parent = trace.start_span("parent")
        trace.start_span("child_a")
        trace.end_span()
        trace.start_span("child_b")
        trace.end_span()
        trace.end_span()  # parent

        assert len(trace.spans) == 1
        assert trace.spans[0] is parent
        assert len(parent.child_spans) == 2
        assert parent.child_spans[0].stage_name == "child_a"
        assert parent.child_spans[1].stage_name == "child_b"

    def test_end_trace(self) -> None:
        trace = PipelineTrace(scenario="end_test")
        assert trace.status == "running"
        assert trace.ended_at is None

        trace.end()
        assert trace.status == "completed"
        assert trace.ended_at is not None
        assert trace.duration_ms >= 0.0

    def test_end_trace_with_custom_status(self) -> None:
        trace = PipelineTrace()
        trace.end(status="dispatched")
        assert trace.status == "dispatched"

    def test_to_dict(self) -> None:
        trace = PipelineTrace(scenario="dict_test", user_id="u-123")
        span = trace.start_span("stage_1", stage_label="Stage One", input_snapshot={"q": "hi"})
        span.set_output("result text")
        trace.end_span()
        trace.end()

        d = trace.to_dict()
        assert d["scenario"] == "dict_test"
        assert d["user_id"] == "u-123"
        assert d["status"] == "completed"
        assert d["trace_id"] == trace.trace_id
        assert d["duration_ms"] >= 0.0
        assert len(d["spans"]) == 1

        span_dict = d["spans"][0]
        assert span_dict["stage_name"] == "stage_1"
        assert span_dict["stage_label"] == "Stage One"
        assert span_dict["status"] == "completed"
        assert span_dict["input_snapshot"] == {"q": "hi"}
        assert span_dict["output_snapshot"] == "result text"
        assert "started_at" in span_dict
        assert "ended_at" in span_dict
        assert "duration_ms" in span_dict

    def test_to_dict_with_nested_spans(self) -> None:
        trace = PipelineTrace()
        trace.start_span("parent")
        trace.start_span("child")
        trace.end_span()
        trace.end_span()
        trace.end()

        d = trace.to_dict()
        assert len(d["spans"]) == 1
        parent_d = d["spans"][0]
        assert len(parent_d["child_spans"]) == 1
        assert parent_d["child_spans"][0]["stage_name"] == "child"

    def test_span_error(self) -> None:
        trace = PipelineTrace()
        span = trace.start_span("failing_stage")
        ended = trace.end_span(status="error", error="Something went wrong")
        assert ended is span
        assert span.status == "error"
        assert span.error == "Something went wrong"
        assert span.ended_at is not None

    def test_end_span_empty_stack_returns_none(self) -> None:
        trace = PipelineTrace()
        result = trace.end_span()
        assert result is None

    def test_set_output_with_metadata(self) -> None:
        span = TraceSpan(stage_name="test")
        span.set_output("hello", metadata={"tokens": 42})
        assert span.output_snapshot == "hello"
        assert span.metadata["tokens"] == 42

    def test_set_output_truncates_long_string(self) -> None:
        span = TraceSpan(stage_name="test")
        span.set_output("x" * 1000)
        assert isinstance(span.output_snapshot, str)
        assert len(span.output_snapshot) < 1000
        assert "truncated" in span.output_snapshot

    def test_end_span_with_output(self) -> None:
        trace = PipelineTrace()
        trace.start_span("stage")
        ended = trace.end_span(output={"result": "ok"})
        assert ended is not None
        assert ended.output_snapshot == {"result": "ok"}

    def test_trace_default_values(self) -> None:
        trace = PipelineTrace()
        assert trace.trace_id  # auto-generated
        assert trace.scenario == ""
        assert trace.user_id == ""
        assert trace.status == "running"
        assert trace.spans == []
        assert trace._span_stack == []

    def test_span_default_values(self) -> None:
        span = TraceSpan()
        assert span.span_id  # auto-generated
        assert span.stage_name == ""
        assert span.status == "running"
        assert span.child_spans == []
        assert span.metadata == {}
        assert span.error is None


# ── ContextVar + trace_span ─────────────────────────────────────────────


class TestContextAndTraceSpan:
    """Tests for ContextVar propagation and the trace_span context manager."""

    def test_get_trace_returns_none_by_default(self) -> None:
        assert get_trace() is None

    def test_set_and_get_trace(self) -> None:
        trace = PipelineTrace(scenario="ctx_test")
        token = set_trace(trace)
        assert get_trace() is trace
        reset_trace(token)
        assert get_trace() is None

    def test_trace_span_no_trace_yields_none(self) -> None:
        """When no trace is set, trace_span yields None with zero overhead."""
        assert get_trace() is None
        with trace_span("my_stage") as span:
            assert span is None
        # No trace was created
        assert get_trace() is None

    def test_trace_span_with_active_trace(self) -> None:
        trace = PipelineTrace(scenario="span_test")
        token = set_trace(trace)
        try:
            with trace_span("retrieve", stage_label="Retrieve", input_snapshot={"q": "test"}) as span:
                assert span is not None
                assert span.stage_name == "retrieve"
                assert span.stage_label == "Retrieve"
                assert span.input_snapshot == {"q": "test"}
                assert span.status == "running"
            # After exit, span should be completed
            assert len(trace.spans) == 1
            assert trace.spans[0].status == "completed"
            assert trace.spans[0].ended_at is not None
        finally:
            reset_trace(token)

    def test_trace_span_records_error_on_exception(self) -> None:
        trace = PipelineTrace(scenario="error_test")
        token = set_trace(trace)
        try:
            with pytest.raises(ValueError, match="boom"), trace_span("failing_stage") as span:
                assert span is not None
                raise ValueError("boom")
            # Span should be recorded with error status
            assert len(trace.spans) == 1
            span = trace.spans[0]
            assert span.status == "error"
            assert span.error == "boom"
            assert span.ended_at is not None
        finally:
            reset_trace(token)

    def test_trace_span_nested(self) -> None:
        trace = PipelineTrace(scenario="nested_ctx")
        token = set_trace(trace)
        try:
            with trace_span("parent") as parent_span:
                assert parent_span is not None
                with trace_span("child") as child_span:
                    assert child_span is not None
                    assert child_span.stage_name == "child"
            assert len(trace.spans) == 1
            assert trace.spans[0].stage_name == "parent"
            assert len(trace.spans[0].child_spans) == 1
            assert trace.spans[0].child_spans[0].stage_name == "child"
            assert trace.spans[0].status == "completed"
            assert trace.spans[0].child_spans[0].status == "completed"
        finally:
            reset_trace(token)

    def test_trace_span_set_output_inside_block(self) -> None:
        trace = PipelineTrace(scenario="output_test")
        token = set_trace(trace)
        try:
            with trace_span("generate") as span:
                assert span is not None
                span.set_output("generated result", metadata={"tokens": 100})
            span = trace.spans[0]
            assert span.output_snapshot == "generated result"
            assert span.metadata["tokens"] == 100
            assert span.status == "completed"
        finally:
            reset_trace(token)

    def test_trace_span_nested_error_propagates(self) -> None:
        """Error in child span marks child as error, then propagates to parent."""
        trace = PipelineTrace(scenario="nested_error")
        token = set_trace(trace)
        try:
            with pytest.raises(RuntimeError, match="child failed"), trace_span("parent") as parent_span:
                assert parent_span is not None
                with trace_span("child"):
                    raise RuntimeError("child failed")
            parent = trace.spans[0]
            assert parent.stage_name == "parent"
            # Parent also gets error status because the exception propagated
            assert parent.status == "error"
            assert parent.error == "child failed"
            # Child span
            assert len(parent.child_spans) == 1
            child = parent.child_spans[0]
            assert child.status == "error"
            assert child.error == "child failed"
        finally:
            reset_trace(token)
