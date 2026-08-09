"""Shared test doubles for the Worker Agent / IntentClassifier unit tests.

All LLM access is mocked here (no network): ``FakeLLM`` returns a message-like
object carrying ``content`` + ``response_metadata`` so the agents' token-usage
extraction and tracing paths exercise the real code. ``FailingLLM`` raises to
drive every agent's ``fallback()`` path.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.domain.knowledge.types import KnowledgeHit
from app.shared.tracing import InMemoryLLMCallTracer


@dataclass
class FakeMessage:
    """Minimal stand-in for a LangChain ``AIMessage``."""

    content: str
    response_metadata: dict[str, Any] = field(default_factory=dict)


def usage_metadata(prompt_tokens: int = 120, completion_tokens: int = 60) -> dict[str, Any]:
    return {
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_cache_miss_tokens": prompt_tokens,
        }
    }


class FakeLLM:
    """Async/sync LLM stub returning a fixed reply with token usage."""

    def __init__(self, reply: str = "这是一段温暖的测试回应。") -> None:
        self.reply = reply
        self.calls: list[str] = []

    def invoke(self, prompt: str) -> FakeMessage:
        self.calls.append(prompt)
        return FakeMessage(content=self.reply, response_metadata=usage_metadata())

    async def ainvoke(self, prompt: str) -> FakeMessage:
        self.calls.append(prompt)
        return FakeMessage(content=self.reply, response_metadata=usage_metadata())

    async def astream(self, prompt: str) -> AsyncGenerator[str, None]:
        """Stream ``reply`` in 2-character chunks (mimics token streaming)."""
        self.calls.append(prompt)
        for i in range(0, len(self.reply), 2):
            yield self.reply[i : i + 2]


class FailingLLM:
    """LLM stub that always raises — drives the agents' fallback paths."""

    def invoke(self, prompt: str) -> Any:
        raise RuntimeError("LLM unreachable")

    async def ainvoke(self, prompt: str) -> Any:
        raise RuntimeError("LLM unreachable")


class StubKnowledgeStore:
    """Stand-in for ``DomainKnowledgeStore`` with a configurable hit list."""

    def __init__(self, hits: list[KnowledgeHit] | None = None) -> None:
        self._hits = hits or []
        self.queries: list[str] = []

    def query(
        self,
        query_text: str,
        max_results: int = 2,
        category_filter: str | None = None,
    ) -> list[KnowledgeHit]:
        self.queries.append(query_text)
        return self._hits[:max_results]


@pytest.fixture
def llm_tracer() -> InMemoryLLMCallTracer:
    return InMemoryLLMCallTracer()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def failing_llm() -> FailingLLM:
    return FailingLLM()


@pytest.fixture
def knowledge_store() -> StubKnowledgeStore:
    return StubKnowledgeStore()
