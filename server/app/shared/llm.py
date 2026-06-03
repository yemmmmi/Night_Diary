"""Minimal LLM client port for dependency injection across the AI pipeline.

This is the single LLM *port* the domain layer depends on. Agents (B-8) receive
an object satisfying :class:`LLMClient` through their constructor and never
construct an LLM themselves (no ``ChatOpenAI()`` / ``os.getenv`` inside agents).

Two methods are declared on purpose:

* ``invoke`` — synchronous; used by the eval :class:`~tests.eval.judge.LLMJudge`
  and by sync callers (e.g. ``SentimentSkill``).
* ``ainvoke`` — asynchronous; used by the Worker Agents, which run concurrently
  under the B-9 ``asyncio.gather`` fan-out.

Both return ``Any`` because the response is *message-like*: callers read the
text via ``getattr(response, "content", response)`` and pull token usage with
:func:`app.domain.agents.state.extract_token_usage` (which reads
``response.response_metadata``). A bare ``str`` therefore also satisfies the
content extraction path (usage degrades to zeros).

The concrete implementation — a LangChain ``BaseChatModel`` (which natively
provides both ``invoke`` and ``ainvoke``) wired from a per-tier model config —
arrives with the :class:`LLMFactory` in Phase C-3. Until then this Protocol
keeps ``langchain-openai`` out of the runtime dependency set: unit tests inject
a mock and the offline eval injects a thin HTTP adapter.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Structural port for an LLM chat model used via dependency injection."""

    def invoke(self, prompt: str) -> Any:
        """Synchronously complete ``prompt`` and return a message-like result."""
        ...

    async def ainvoke(self, prompt: str) -> Any:
        """Asynchronously complete ``prompt`` and return a message-like result."""
        ...


def message_text(response: Any) -> str:
    """Extract the text body from a message-like LLM response.

    Accepts a LangChain ``AIMessage`` (``.content``) or a plain ``str`` so the
    same call site works for the production model and a stubbed reply.
    """
    content = getattr(response, "content", response)
    return str(content)


__all__ = ["LLMClient", "message_text"]
