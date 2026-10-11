"""Unit tests for the pluggable ContextEngine registry (D1)."""

from __future__ import annotations

from app.domain.agents.context_compressor import ContextCompressor, ReferenceContextEngine
from app.domain.agents.context_engine import (
    DEFAULT_ENGINE,
    ContextEngine,
    available_engines,
    build_context_engine,
    register_engine,
)


def test_builtin_engines_registered() -> None:
    engines = available_engines()
    assert "compressor" in engines
    assert "reference" in engines


def test_build_default_engine() -> None:
    engine = build_context_engine()
    assert isinstance(engine, ContextCompressor)
    assert engine.name == DEFAULT_ENGINE


def test_build_unknown_engine_falls_back_to_default() -> None:
    engine = build_context_engine("does-not-exist")
    assert isinstance(engine, ContextCompressor)


def test_build_engine_passes_kwargs() -> None:
    engine = build_context_engine("compressor", max_tokens=42)
    assert isinstance(engine, ContextCompressor)
    assert engine.max_tokens == 42


def test_compressor_satisfies_protocol() -> None:
    assert isinstance(ContextCompressor(), ContextEngine)
    assert isinstance(ReferenceContextEngine(), ContextEngine)


def test_register_custom_engine() -> None:
    class _Echo:
        name = "echo"

        def compress(self, current_content, *, candidates=None, episodic=None):
            return current_content

    register_engine(_Echo.name, _Echo)
    try:
        engine = build_context_engine("echo")
        assert engine.compress("hello") == "hello"
    finally:
        # Keep the global registry clean for other tests.
        from app.domain.agents.context_engine import _ENGINES

        _ENGINES.pop("echo", None)


def test_reference_engine_preserves_source_ids() -> None:
    engine = ReferenceContextEngine(max_tokens=500)
    result = engine.compress(
        "回顾最近的状态。",
        candidates=[
            {"diary_id": 7, "content": "今天加班到很晚，整个人特别疲惫，需要好好休息一下才行"}
        ],
        episodic=[
            {"diary_id": 3, "content": "上周也失眠，整晚翻来覆去睡不着，白天一点精神都没有"}
        ],
    )
    assert "diary:7" in result
    assert "diary:3" in result
    assert "[引用]" in result


def test_reference_engine_no_footer_without_ids() -> None:
    engine = ReferenceContextEngine(max_tokens=500)
    result = engine.compress(
        "回顾最近的状态。",
        candidates=[{"content": "今天加班到很晚，整个人特别疲惫，需要好好休息一下才行"}],
    )
    assert "[引用]" not in result


def test_reference_engine_empty_input() -> None:
    engine = ReferenceContextEngine()
    assert engine.compress("") == ""