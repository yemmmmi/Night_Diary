"""ReAct-style agent executor with tool calls (no LangGraph dependency)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.ai.prompts import AGENT_SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.services.ai.tool_factory import ToolFn
from app.services.ai.utils import extract_token_usage, merge_token_info
from app.shared.llm import LLMClient, message_text

logger = logging.getLogger(__name__)

_TOOL_CALL_PATTERN = re.compile(r"<tool>(\w+)</tool>\s*<args>(.*?)</args>", re.DOTALL)


def _parse_tool_calls(text: str) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []
    for match in _TOOL_CALL_PATTERN.finditer(text):
        name = match.group(1)
        raw_args = match.group(2).strip()
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            args = {"query": raw_args}
        calls.append((name, args))
    return calls


def run_agent(
    llm: LLMClient,
    context: dict[str, str],
    tools: dict[str, ToolFn],
) -> tuple[str, dict[str, int], str]:
    tool_hint = (
        "\n\n如需调用工具，请输出：<tool>工具名</tool> <args>{\"参数\": \"值\"}</args>"
    )
    prompt = (
        f"{AGENT_SYSTEM_PROMPT}{tool_hint}\n\n"
        + USER_PROMPT_TEMPLATE.format(**context)
    )
    response = llm.invoke(prompt)
    token_info = extract_token_usage(response)
    result_text = message_text(response)
    thk_log_parts = ["[Agent]"]

    tool_calls = _parse_tool_calls(result_text)
    if tool_calls:
        thk_log_parts.append("tools called:")
        tool_results: list[str] = []
        for tool_name, tool_args in tool_calls:
            thk_log_parts.append(f"  - {tool_name}({tool_args})")
            fn = tools.get(tool_name)
            if fn is None:
                tool_results.append(f"[{tool_name}]: 未知工具")
                continue
            try:
                tool_results.append(f"[{tool_name}]: {fn(**tool_args)}")
            except Exception as exc:
                logger.warning("Tool %s failed: %s", tool_name, exc)
                tool_results.append(f"[{tool_name} error]: {exc}")

        followup = (
            f"{AGENT_SYSTEM_PROMPT}\n\n"
            + USER_PROMPT_TEMPLATE.format(**context)
            + "\n\n## Tool Results\n"
            + "\n".join(tool_results)
        )
        final_response = llm.invoke(followup)
        token_info = merge_token_info(token_info, extract_token_usage(final_response))
        result_text = message_text(final_response)
    else:
        thk_log_parts.append("no tools needed")

    thk_log_parts.append(
        f"[Token] total={token_info['total_tokens']} "
        f"cache_hit={token_info['cache_hit_tokens']} "
        f"miss={token_info['cache_miss_tokens']} "
        f"output={token_info['output_tokens']}"
    )
    return result_text, token_info, "\n".join(thk_log_parts)
