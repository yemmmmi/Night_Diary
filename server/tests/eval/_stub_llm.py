"""Shared stub LLM clients for offline eval suites.

Provides deterministic stub LLMs so eval tests stay green in CI (no API key,
no GPU). Two variants:

- ``StubAgentLLM`` — returns a fixed empathetic reply (drop-in replacement for
  the old ``_StubAgentLLM`` in ``generation/conftest.py``).
- ``ProgrammableStubLLM`` — returns preset responses by case_id, enabling
  tool_call / skill_call eval to verify parsing logic without real LLM calls.
"""

from __future__ import annotations

import json
from typing import Any

from tests.eval._http_llm import Message, usage_block


class StubAgentLLM:
    """Deterministic empathetic-ish reply so stub-mode eval can be scored."""

    _REPLY = (
        "听起来你今天经历了不少起伏，这些情绪都是真实而值得被理解的。"
        "谢谢你愿意把它们写下来，我会一直在这里陪着你，慢慢来，不着急。"
    )

    def invoke(self, prompt: str) -> Message:
        return Message(content=self._REPLY, response_metadata=usage_block(150, 60))

    async def ainvoke(self, prompt: str) -> Message:
        return Message(content=self._REPLY, response_metadata=usage_block(150, 60))


class StubJudgeLLM:
    """Deterministic judge returning a fixed mid-high score for every dimension."""

    def invoke(self, prompt: str) -> Message:
        keys = ["empathy", "context_faithfulness", "relevance", "safety"]
        body = ", ".join(f'"{k}": 4' for k in keys)
        return Message(
            content=f'{{{body}, "rationale": "stub judge"}}',
            response_metadata=usage_block(300, 48),
        )


class ProgrammableStubLLM:
    """Stub LLM that returns preset responses by matching prompt content.

    For tool_call eval: if the prompt contains a user message that maps to a
    known case, return the preset tool-call text (e.g. ``<tool>search_diary</tool>``).
    This lets us verify the parsing pipeline (``parse_text_tag_calls``,
    ``extract_native_tool_calls``) without a real LLM.

    For intent eval: return preset JSON intent classification results.

    Args:
        responses: A list of (substring, response_text) pairs. The first
            matching substring wins. If none match, returns a default reply.
        default_response: Fallback response when no substring matches.
    """

    def __init__(
        self,
        responses: list[tuple[str, str]] | None = None,
        *,
        default_response: str = "",
    ) -> None:
        self._responses = responses or []
        self._default = default_response or "好的，我理解了。"

    def _match(self, prompt: str) -> str:
        for substring, response in self._responses:
            if substring in prompt:
                return response
        return self._default

    def invoke(self, prompt: str) -> Message:
        return Message(content=self._match(prompt), response_metadata=usage_block(100, 40))

    async def ainvoke(self, prompt: str) -> Message:
        return Message(content=self._match(prompt), response_metadata=usage_block(100, 40))

    def bind_tools(self, tool_specs: list[Any]) -> "BoundProgrammableStub":
        """Return a wrapper that simulates native tool calling."""
        return BoundProgrammableStub(self, tool_specs)


class BoundProgrammableStub:
    """Wrapper that simulates native function calling for stub mode.

    When ``invoke`` is called, it parses the stub response text for
    ``<tool>name</tool><args>json</args>`` tags and converts them into
    ``tool_calls`` on the returned Message, simulating a native function
    calling response.
    """

    def __init__(self, inner: ProgrammableStubLLM, tool_specs: list[Any]) -> None:
        self._inner = inner
        self._tool_specs = tool_specs

    def invoke(self, prompt: str) -> Message:
        from app.shared.tool_protocol import parse_text_tag_calls

        text = self._inner._match(prompt)
        # Parse text-tag calls and convert to native tool_calls format
        parsed = parse_text_tag_calls(text)
        tool_calls = [{"name": tc.name, "args": tc.args} for tc in parsed]
        # Strip tool tags from content
        from app.shared.tool_protocol import strip_tool_tags

        clean_text = strip_tool_tags(text)
        return Message(
            content=clean_text,
            response_metadata=usage_block(100, 40),
            tool_calls=tool_calls,
        )

    async def ainvoke(self, prompt: str) -> Message:
        return self.invoke(prompt)
