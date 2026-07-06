"""Unified tool protocol — bridges native function calling and text-tag protocol.

Two paths:
1. Native: if the LLM client exposes ``bind_tools``, call it with ToolSpec
   schemas and parse ``tool_calls`` from the response.
2. Fallback: inject a text-tag hint into the prompt and parse
   ``<tool>name</tool><args>{...}</args>`` from the response text.

The caller (ConversationLoop / AgentExecutor) uses ``invoke_with_tools`` which
auto-detects the path. This keeps the loop logic protocol-agnostic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

#: Text-tag fallback pattern (shared, single source of truth).
TOOL_CALL_PATTERN = re.compile(r"<tool>(\w+)</tool>\s*<args>(.*?)</args>", re.DOTALL)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Schema description for a tool, used in native function calling."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class ToolCallResult:
    """A parsed tool call from either protocol path."""

    name: str
    args: dict[str, Any]


def parse_text_tag_calls(text: str) -> list[ToolCallResult]:
    """Parse ``<tool>name</tool><args>json</args>`` from text (fallback path)."""
    results: list[ToolCallResult] = []
    for match in TOOL_CALL_PATTERN.finditer(text):
        name = match.group(1)
        raw_args = match.group(2).strip()
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            args = {"query": raw_args}
        results.append(ToolCallResult(name=name, args=args))
    return results


def strip_tool_tags(text: str) -> str:
    """Remove tool-call tags from final response text."""
    return TOOL_CALL_PATTERN.sub("", text).strip()


def build_tool_hint(tool_specs: list[ToolSpec]) -> str:
    """Build the text-tag hint appended to the prompt (fallback path)."""
    lines = [
        '\n\n如需调用工具查询信息，请输出：<tool>工具名</tool> <args>{"参数": "值"}</args>',
        "可用工具：",
    ]
    for spec in tool_specs:
        lines.append(f"- {spec.name}（{spec.description}）")
    lines.append("仅当确需查询信息时才调用工具。")
    return "\n".join(lines)


def supports_native_tools(llm: Any) -> bool:
    """Detect whether an LLM client supports native function calling."""
    return hasattr(llm, "bind_tools") and callable(llm.bind_tools)


def extract_native_tool_calls(response: Any) -> list[ToolCallResult]:
    """Extract tool_calls from a LangChain AIMessage (native path).

    Handles both dict and object formats for compatibility across
    LangChain versions.
    """
    results: list[ToolCallResult] = []
    tool_calls = getattr(response, "tool_calls", None) or []
    for tc in tool_calls:
        if isinstance(tc, dict):
            name = tc.get("name", "")
            args = tc.get("args", {})
        else:
            name = getattr(tc, "name", "")
            args = getattr(tc, "args", {})
        if name:
            results.append(ToolCallResult(name=name, args=dict(args)))
    return results


__all__ = [
    "TOOL_CALL_PATTERN",
    "ToolCallResult",
    "ToolSpec",
    "build_tool_hint",
    "extract_native_tool_calls",
    "parse_text_tag_calls",
    "strip_tool_tags",
    "supports_native_tools",
]
