"""Tests for FallbackLLMClient — provider fallback and key-pool rotation (D5)."""

from __future__ import annotations

from typing import Any

import pytest

from app.shared.errors import AIServiceUnavailableError
from app.shared.llm_resilience import FallbackLLMClient
from app.shared.tool_protocol import supports_native_tools


class _OkClient:
    def __init__(self, reply: str, model: str = "ok") -> None:
        self.reply = reply
        self.model = model
        self.calls = 0

    def invoke(self, prompt: str) -> Any:
        self.calls += 1
        return self.reply

    async def ainvoke(self, prompt: str) -> Any:
        self.calls += 1
        return self.reply

    async def astream(self, prompt: str):
        self.calls += 1
        yield self.reply


class _FailClient:
    def __init__(self, exc: Exception | None = None) -> None:
        self.model = "fail"
        self.calls = 0
        self.exc = exc or RuntimeError("boom")

    def invoke(self, prompt: str) -> Any:
        self.calls += 1
        raise self.exc

    async def ainvoke(self, prompt: str) -> Any:
        self.calls += 1
        raise self.exc

    async def astream(self, prompt: str):
        self.calls += 1
        raise self.exc
        yield  # pragma: no cover


def test_requires_at_least_one_attempt() -> None:
    with pytest.raises(AIServiceUnavailableError):
        FallbackLLMClient([])


def test_primary_success_does_not_touch_backup() -> None:
    primary = _OkClient("hi")
    backup = _OkClient("backup", model="b")
    client = FallbackLLMClient([primary, backup])
    assert client.invoke("p") == "hi"
    assert primary.calls == 1
    assert backup.calls == 0
    assert client.model == "ok"


def test_falls_back_on_primary_failure() -> None:
    primary = _FailClient()
    backup = _OkClient("backup", model="b")
    client = FallbackLLMClient([primary, backup])
    assert client.invoke("p") == "backup"
    assert primary.calls == 1
    assert backup.calls == 1


def test_raises_last_error_when_all_fail() -> None:
    first = _FailClient(RuntimeError("first"))
    second = _FailClient(RuntimeError("second"))
    client = FallbackLLMClient([first, second])
    with pytest.raises(RuntimeError, match="second"):
        client.invoke("p")


@pytest.mark.asyncio
async def test_ainvoke_falls_back() -> None:
    primary = _FailClient()
    backup = _OkClient("async-backup")
    client = FallbackLLMClient([primary, backup])
    assert await client.ainvoke("p") == "async-backup"


@pytest.mark.asyncio
async def test_astream_falls_back_before_any_token() -> None:
    primary = _FailClient()
    backup = _OkClient("streamed")
    client = FallbackLLMClient([primary, backup])
    tokens = [token async for token in client.astream("p")]
    assert tokens == ["streamed"]
    assert primary.calls == 1
    assert backup.calls == 1


@pytest.mark.asyncio
async def test_astream_does_not_fallback_after_partial_yield() -> None:
    class _PartialClient:
        model = "partial"

        async def astream(self, prompt: str):
            yield "half"
            raise RuntimeError("mid-stream")

    backup = _OkClient("should-not-run")
    client = FallbackLLMClient([_PartialClient(), backup])
    with pytest.raises(RuntimeError, match="mid-stream"):
        async for _ in client.astream("p"):
            pass
    assert backup.calls == 0


def test_bind_tools_absent_for_non_tool_clients() -> None:
    client = FallbackLLMClient([_OkClient("x"), _OkClient("y")])
    assert not supports_native_tools(client)


def test_bind_tools_binds_every_capable_attempt() -> None:
    class _ToolClient(_OkClient):
        def __init__(self, reply: str, model: str = "t") -> None:
            super().__init__(reply, model)
            self.bound: list[Any] | None = None

        def bind_tools(self, tools: list[Any]) -> _ToolClient:
            self.bound = tools
            return self

    first = _ToolClient("a")
    second = _ToolClient("b")
    client = FallbackLLMClient([first, second])
    assert supports_native_tools(client)

    bound = client.bind_tools([{"name": "x"}])
    assert first.bound == [{"name": "x"}]
    assert second.bound == [{"name": "x"}]
    assert bound.invoke("p") == "a"


def test_bind_tools_raises_when_no_attempt_can_bind() -> None:
    class _BadBinder(_OkClient):
        def bind_tools(self, tools: list[Any]) -> Any:
            raise AttributeError("nope")

    client = FallbackLLMClient([_BadBinder("a")])
    with pytest.raises(AttributeError):
        client.bind_tools([])