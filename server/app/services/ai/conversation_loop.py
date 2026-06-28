"""ConversationLoop — Agentic Loop engine for scene 2 (multi-turn conversation).

Implements the 5-stage Agent session framework:

1. **Session routing**: SessionContext maintains history, usage, profile across turns
2. **Input processing**: normalize content, crisis detection, temporal keyword check
3. **Context assembly**: system prompt + profile + episodic + compressed history + tools
4. **Agentic Loop**:
   4.1 Context governance (token budget check)
   4.2 Call model
   4.3 Check if tool call is needed → yes: 4.4, no: exit loop
   4.4 Execute tool → backfill result → go to 4.1
5. **Output**: final response, usage summary, stop reason

The loop is bounded (max ``MAX_LOOP_ITERATIONS`` rounds) to prevent infinite
cycles. Tool calls use the same ``<tool>name</tool><args>{...}</args>`` protocol
as the existing :mod:`agent_executor`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.services.ai.prompts import (
    CHAT_SYSTEM_PROMPT,
    CHAT_USER_PROMPT_TEMPLATE,
    FALLBACK_FEEDBACK,
    TEMPORAL_KEYWORDS,
)
from app.services.ai.session_context import SessionContext, get_or_create_session
from app.services.ai.tool_factory import ToolFn
from app.services.ai.utils import extract_token_usage, merge_token_info
from app.shared.llm import LLMClient, message_text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

#: Maximum loop iterations (1 initial + up to 2 tool rounds).
MAX_LOOP_ITERATIONS = 3

#: Pattern to parse tool calls from LLM output.
_TOOL_CALL_PATTERN = re.compile(r"<tool>(\w+)</tool>\s*<args>(.*?)</args>", re.DOTALL)

#: Tool-calling hint appended to the system prompt.
_TOOL_HINT = (
    "\n\n如需调用工具查询信息，请输出：<tool>工具名</tool> <args>{\"参数\": \"值\"}</args>"
    "\n可用工具：search_diary（搜索历史日记）、analyze_sentiment（情感分析）"
    "\n仅当用户提到回溯性表述（如\"昨天\"\"上次\"）时才调用 search_diary。"
)


@dataclass(frozen=True, slots=True)
class LoopResult:
    """Output of the Agentic Loop — the 5th stage (output aggregation)."""

    reply_text: str
    token_info: dict[str, int]
    stop_reason: str  # "completed" | "tool_called" | "max_iterations" | "error" | "no_llm"
    tool_calls_made: list[str] = field(default_factory=list)
    is_crisis: bool = False


def _parse_tool_calls(text: str) -> list[tuple[str, dict[str, Any]]]:
    """Extract tool calls from LLM output text."""
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


def _needs_tool_call(content: str) -> bool:
    """Quick check: does the user message contain temporal references?

    This is a pre-filter — the LLM decides whether to actually call a tool,
    but we only enable tool-calling mode when temporal keywords are present.
    """
    return any(kw in content for kw in TEMPORAL_KEYWORDS)


def _execute_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    tools: dict[str, ToolFn],
) -> str:
    """Execute a single tool call, returning a result string."""
    fn = tools.get(tool_name)
    if fn is None:
        return f"[{tool_name}]: 未知工具"
    try:
        result = fn(**tool_args)
        return f"[{tool_name}]: {result}"
    except Exception as exc:
        logger.warning("Tool %s failed: %s", tool_name, exc)
        return f"[{tool_name} error]: {exc}"


def run_conversation_loop(
    db: Session,
    container: ServiceContainer,
    *,
    conversation_id: str,
    content: str,
    pinned_diaries_text: str,
    retrieved_diaries_text: str,
    episodic_text: str,
    memory_ids: list[str],
    tools: dict[str, ToolFn] | None = None,
    crisis_guard: Any | None = None,
) -> LoopResult:
    """Execute the Agentic Loop for a single conversation turn.

    This function is called by :func:`generate_reply` after context assembly
    (crisis check, profile loading, RAG retrieval) is complete. It handles the
    loop portion: model call → tool check → tool execution → re-call.
    """
    # Get or create session context (task 8)
    session = get_or_create_session(conversation_id, container=container)

    # Determine if tools should be enabled for this turn
    enable_tools = tools is not None and len(tools) > 0 and _needs_tool_call(content)

    # Build the base prompt
    system_prompt = CHAT_SYSTEM_PROMPT
    if enable_tools:
        system_prompt += _TOOL_HINT

    chat_history = session.get_history()
    topics_text = "、".join(session.profile_topics) if session.profile_topics else "（暂无）"

    base_user_prompt = CHAT_USER_PROMPT_TEMPLATE.format(
        pinned_diaries=pinned_diaries_text,
        retrieved_diaries=retrieved_diaries_text,
        episodic_memories=episodic_text,
        chat_history=chat_history,
        user_message=content.strip(),
    )
    if session.profile_style or session.profile_topics:
        base_user_prompt += (
            f"\n\n【用户画像】偏好风格：{session.profile_style or '自然'}；近期关注：{topics_text}"
        )

    # Get LLM
    llm: LLMClient | None = container._llm_for_tier(db, "medium", agent_name="chat")
    if llm is None:
        logger.warning("ConversationLoop: LLM unavailable")
        return LoopResult(
            reply_text=FALLBACK_FEEDBACK,
            token_info={},
            stop_reason="no_llm",
        )

    # ── Agentic Loop (stage 4) ──
    total_usage: dict[str, int] = {}
    tool_calls_made: list[str] = []
    tool_results_text = ""
    current_prompt = f"{system_prompt}\n\n{base_user_prompt}"

    for iteration in range(MAX_LOOP_ITERATIONS):
        # 4.1 Context governance: check token budget
        # (SessionContext already manages history compression)

        # 4.2 Call model
        try:
            if tool_results_text:
                current_prompt += f"\n\n## 工具结果\n{tool_results_text}"
            response = llm.invoke(current_prompt)
        except Exception as exc:
            logger.warning("ConversationLoop LLM invoke failed (iter %d): %s", iteration, exc)
            return LoopResult(
                reply_text=FALLBACK_FEEDBACK,
                token_info=total_usage,
                stop_reason="error",
                tool_calls_made=tool_calls_made,
            )

        turn_usage = extract_token_usage(response)
        total_usage = merge_token_info(total_usage, turn_usage)
        result_text = message_text(response).strip()

        # 4.3 Check if tool call is needed
        if not enable_tools or iteration == MAX_LOOP_ITERATIONS - 1:
            # No tools enabled, or max iterations reached
            stop_reason = "max_iterations" if (enable_tools and iteration > 0) else "completed"
            break

        tool_calls = _parse_tool_calls(result_text)
        if not tool_calls:
            # No tool calls in response — we're done
            stop_reason = "completed"
            break

        # 4.4 Execute tools and backfill results
        tool_results: list[str] = []
        for tool_name, tool_args in tool_calls:
            tool_calls_made.append(tool_name)
            result = _execute_tool(tool_name, tool_args, tools or {})
            tool_results.append(result)

        tool_results_text = "\n".join(tool_results)
        stop_reason = "tool_called"
        # Loop continues to 4.1 for the next iteration

    # Clean up tool-call tags from final response
    final_text = _TOOL_CALL_PATTERN.sub("", result_text).strip()
    if not final_text:
        final_text = FALLBACK_FEEDBACK

    # Stage 5: Output aggregation — accumulate usage in session
    session.accumulate_usage(total_usage)
    session.add_turn(content, final_text)

    logger.info(
        "ConversationLoop completed: conversation=%s iterations=%d tools=%s tokens=%d stop=%s",
        conversation_id,
        iteration + 1,
        tool_calls_made,
        total_usage.get("total_tokens_used", 0),
        stop_reason,
    )

    return LoopResult(
        reply_text=final_text,
        token_info=total_usage,
        stop_reason=stop_reason,
        tool_calls_made=tool_calls_made,
    )


__all__ = [
    "LoopResult",
    "MAX_LOOP_ITERATIONS",
    "run_conversation_loop",
]
