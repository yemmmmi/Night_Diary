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

The concrete implementation — a LangChain ``BaseChatModel`` wired from a
per-tier :class:`~app.shared.llm_factory.LLMFactory` config — lives in
``llm_factory.py``. This Protocol keeps domain code decoupled from
``langchain-openai``: unit tests inject stubs and the offline eval injects a
thin HTTP adapter.
"""

from __future__ import annotations

import base64
from typing import Any, Literal, Protocol, TypedDict, TypeAlias, runtime_checkable


class ImageContentBlock(TypedDict):
    """A single image part of a multimodal prompt.

    Mirrors LangChain's content-block shape so a ``ChatOpenAI`` instance can
    consume it directly when wrapped in a ``LLMPrompt`` list. ``detail``
    controls the vision-token budget (``low``/``high``/``auto``).
    """

    type: Literal["image"]
    source_type: Literal["url", "base64"]
    data: str
    mime_type: str
    detail: Literal["low", "high", "auto"]


#: A prompt that is either a plain string (existing call sites) or a list of
#: text/image parts for multimodal calls. Existing ``invoke(prompt: str)``
#: call sites keep working because ``str`` satisfies this alias.
LLMPrompt: TypeAlias = "str | list[str | ImageContentBlock]"


@runtime_checkable
class LLMClient(Protocol):
    """Structural port for an LLM chat model used via dependency injection."""

    def invoke(self, prompt: str) -> Any:
        """Synchronously complete ``prompt`` and return a message-like result."""
        ...

    async def ainvoke(self, prompt: str) -> Any:
        """Asynchronously complete ``prompt`` and return a message-like result."""
        ...


@runtime_checkable
class ToolCapableLLMClient(Protocol):
    """LLM client that additionally supports native function calling.

    Implementations (e.g. ChatOpenAI) expose ``bind_tools`` returning a
    runnable that accepts tool specs and produces responses with
    ``tool_calls``. TracingLLMClient transparently delegates this.
    """

    def invoke(self, prompt: str) -> Any: ...

    async def ainvoke(self, prompt: str) -> Any: ...

    def bind_tools(self, tools: list[Any]) -> Any: ...


@runtime_checkable
class VisionCapableLLMClient(Protocol):
    """LLM client that additionally supports multimodal (image) prompts.

    Mirrors the :class:`ToolCapableLLMClient` extension pattern: existing
    ``invoke``/``ainvoke`` string call sites keep working, while image-aware
    services use ``invoke_with_images``/``ainvoke_with_images`` with a
    :data:`LLMPrompt` list. ``TracingLLMClient`` transparently delegates this.
    """

    def invoke(self, prompt: str) -> Any: ...

    async def ainvoke(self, prompt: str) -> Any: ...

    def invoke_with_images(self, prompt: LLMPrompt) -> Any: ...

    async def ainvoke_with_images(self, prompt: LLMPrompt) -> Any: ...


def build_image_block(
    image_bytes: bytes,
    mime_type: str,
    *,
    detail: Literal["low", "high", "auto"] = "auto",
) -> ImageContentBlock:
    """Build a base64 :class:`ImageContentBlock` from raw image bytes.

    ``detail="auto"`` lets the provider choose resolution; lower to ``"low"``
    for quick classification, raise to ``"high"`` for dense text/screenshots.
    """
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return ImageContentBlock(
        type="image",
        source_type="base64",
        data=encoded,
        mime_type=mime_type,
        detail=detail,
    )


def message_text(response: Any) -> str:
    """Extract the text body from a message-like LLM response.

    Accepts a LangChain ``AIMessage`` (``.content``) or a plain ``str`` so the
    same call site works for the production model and a stubbed reply.
    """
    content = getattr(response, "content", response)
    return str(content)


__all__ = [
    "ImageContentBlock",
    "LLMClient",
    "LLMPrompt",
    "ToolCapableLLMClient",
    "VisionCapableLLMClient",
    "build_image_block",
    "message_text",
]
