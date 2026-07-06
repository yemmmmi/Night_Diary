"""ReAct-style agent executor with tool calls (no LangGraph dependency)."""

from __future__ import annotations

import logging

from app.services.ai.prompts import AGENT_SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.services.ai.tool_factory import ToolFn, specs_for_names
from app.services.ai.utils import extract_token_usage, merge_token_info
from app.shared.llm import LLMClient, message_text
from app.shared.tool_protocol import build_tool_hint, parse_text_tag_calls, strip_tool_tags

logger = logging.getLogger(__name__)


def run_agent(
    llm: LLMClient,
    context: dict[str, str],
    tools: dict[str, ToolFn],
) -> tuple[str, dict[str, int], str]:
    tool_hint = build_tool_hint(specs_for_names(list(tools.keys()))) if tools else ""
    prompt = (
        f"{AGENT_SYSTEM_PROMPT}{tool_hint}\n\n"
        + USER_PROMPT_TEMPLATE.format(**context)
    )
    response = llm.invoke(prompt)
    token_info = extract_token_usage(response)
    result_text = message_text(response)
    thk_log_parts = ["[Agent]"]

    tool_calls = parse_text_tag_calls(result_text)
    if tool_calls:
        thk_log_parts.append("tools called:")
        tool_results: list[str] = []
        for tc in tool_calls:
            thk_log_parts.append(f"  - {tc.name}({tc.args})")
            fn = tools.get(tc.name)
            if fn is None:
                tool_results.append(f"[{tc.name}]: 未知工具")
                continue
            try:
                tool_results.append(f"[{tc.name}]: {fn(**tc.args)}")
            except Exception as exc:
                logger.warning("Tool %s failed: %s", tc.name, exc)
                tool_results.append(f"[{tc.name} error]: {exc}")

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

    # Clean up tool-call tags from final response
    final_text = strip_tool_tags(result_text)

    thk_log_parts.append(
        f"[Token] total={token_info['total_tokens_used']} "
        f"cache_hit={token_info['cache_hit_tokens']} "
        f"miss={token_info['cache_miss_tokens']} "
        f"output={token_info['output_tokens']}"
    )
    return final_text, token_info, "\n".join(thk_log_parts)
