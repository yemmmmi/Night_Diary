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

import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from app.domain.agents.types import ChatIntentResult
from app.services.ai.prompts import (
    CHAT_SYSTEM_PROMPT,
    CHAT_USER_PROMPT_TEMPLATE,
    FALLBACK_FEEDBACK,
    TEMPORAL_KEYWORDS,
)
from app.services.ai.session_context import get_or_create_session
from app.services.ai.tool_factory import ToolFn, specs_for_names
from app.services.ai.utils import extract_token_usage, merge_token_info
from app.shared.llm import LLMClient, message_text
from app.shared.pipeline_trace import trace_span
from app.shared.tool_protocol import (
    build_tool_hint,
    extract_native_tool_calls,
    parse_text_tag_calls,
    strip_tool_tags,
    supports_native_tools,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

#: Maximum loop iterations (1 initial + up to 2 tool rounds).
MAX_LOOP_ITERATIONS = 3

#: Beijing timezone (UTC+8) — the diary corpus and users are China-based.
_BEIJING_TZ = timezone(timedelta(hours=8))


def _current_date_context() -> str:
    """Return a date context string for the system prompt (Beijing time).

    Computed **per call** (not cached) so that long-lived sessions always see
    the correct "today".  Without this, the LLM has no date in the prompt and
    infers "today" from the latest diary date in context — which may be days
    old, causing "昨天" to resolve to the wrong day.
    """
    now = datetime.now(_BEIJING_TZ)
    weekday_cn = "星期" + "一二三四五六日"[now.weekday()]
    return f'\n\n## 当前日期\n今天是 {now.strftime("%Y-%m-%d")} {weekday_cn}。用户说「昨天」「明天」等相对日期时，请以此日期为基准计算。'


@dataclass(frozen=True, slots=True)
class Citation:
    """Source citation for result integration — tracks where information came from.

    Used to append a "参考来源" section to the final response so the user
    can see which tools, diaries, or memories informed the AI's reply.
    """

    source_type: str  # "tool" | "diary" | "memory" | "skill"
    source_name: str  # tool name, diary date, memory label, skill name
    content_summary: str  # first 100 chars of the source content


@dataclass(frozen=True, slots=True)
class LoopResult:
    """Output of the Agentic Loop — the 5th stage (output aggregation)."""

    reply_text: str
    token_info: dict[str, int]
    stop_reason: str  # "completed" | "tool_called" | "max_iterations" | "error" | "no_llm"
    tool_calls_made: list[str] = field(default_factory=list)
    is_crisis: bool = False
    citations: list[Citation] = field(default_factory=list)


def _format_citations(citations: list[Citation]) -> str:
    """Format citations as a '参考来源' section appended to the reply.

    Only appends if there are citations — empty list means no annotation.
    """
    if not citations:
        return ""

    lines = ["\n\n---\n📋 **参考来源**"]
    type_labels = {
        "tool": "工具",
        "diary": "日记",
        "memory": "记忆",
        "skill": "技能",
    }
    for cite in citations:
        label = type_labels.get(cite.source_type, cite.source_type)
        summary = cite.content_summary[:80]
        if len(cite.content_summary) > 80:
            summary += "…"
        lines.append(f"- [{label}] {cite.source_name}：{summary}")

    return "\n".join(lines)


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


def _run_via_graph(
    *,
    db: Session,
    container: ServiceContainer,
    conversation_id: str,
    content: str,
    pinned_diaries_text: str,
    retrieved_diaries_text: str,
    episodic_text: str,
    tools: dict[str, ToolFn] | None,
    intent_result: ChatIntentResult | None,
    user_id: str,
) -> LoopResult | None:
    """Execute conversation via LangGraph StateGraph.

    Returns LoopResult on success, None if graph is unavailable.
    Raises on execution error (caught by caller for fallback).
    """
    from app.services.ai.conversation_graph import (
        LANGGRAPH_AVAILABLE,
        build_conversation_graph,
        run_conversation_graph,
    )
    from app.services.ai.session_context import get_or_create_session

    if not LANGGRAPH_AVAILABLE:
        return None

    # Get or create session for context
    session = get_or_create_session(conversation_id, container=container, user_id=user_id)

    # Get LLM
    tier = intent_result.tier if intent_result else "medium"
    llm = container._llm_for_tier(db, tier, agent_name="conversation_graph")
    if llm is None:
        return None

    # Build tool specs
    from app.services.ai.tool_factory import specs_for_names

    tool_names = list((tools or {}).keys())
    tool_specs = specs_for_names(tool_names) if tool_names else []

    # Build system prompt (simplified for graph)
    from app.services.ai.prompts import CHAT_SYSTEM_PROMPT

    system_prompt = CHAT_SYSTEM_PROMPT + _current_date_context()
    chat_history = session.get_history()
    if chat_history:
        system_prompt += f"\n\n## 对话历史\n{chat_history}"

    # Get or build graph (cached in container)
    # Note: use container.__dict__ to avoid auto-creating attributes on
    # MagicMock containers (getattr never returns None for MagicMock).
    graph = container.__dict__.get("_conversation_graph") if hasattr(container, "__dict__") else None
    if graph is None:
        graph = build_conversation_graph()
        if graph is None:
            return None
        # Cache for reuse
        with contextlib.suppress(Exception):
            container._conversation_graph = graph

    # Run graph
    brief_context = session.compressed_history[:300] if session.compressed_history else ""
    final_state = run_conversation_graph(
        graph,
        content=content,
        intent_result=intent_result,
        tools=tools,
        tool_specs=tool_specs,
        llm=llm,
        system_prompt=system_prompt,
        pinned_diaries_text=pinned_diaries_text,
        retrieved_diaries_text=retrieved_diaries_text,
        episodic_text=episodic_text,
        brief_context=brief_context,
        conversation_id=conversation_id,
    )

    # Convert graph output to LoopResult
    final_response = final_state.get("final_response", FALLBACK_FEEDBACK)
    total_usage = final_state.get("total_usage", {})
    stop_reason = final_state.get("stop_reason", "completed")
    tool_calls_made = final_state.get("tool_calls_made", [])
    citations = final_state.get("citations", [])

    # Update session
    session.accumulate_usage(total_usage)
    session.add_turn(content, final_response)

    return LoopResult(
        reply_text=final_response,
        token_info=total_usage,
        stop_reason=stop_reason,
        tool_calls_made=tool_calls_made,
        citations=citations,
    )


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
    user_id: str = "default",
    intent_result: ChatIntentResult | None = None,
    use_graph: bool = True,
) -> LoopResult:
    """Execute the Agentic Loop for a single conversation turn.

    When ``use_graph=True`` (default) and LangGraph is available, the loop
    runs via the StateGraph pipeline with checkpointing. On any failure,
    it falls back to the legacy synchronous loop.

    Args:
        use_graph: If True, try LangGraph StateGraph first (with fallback).
                   If False, always use the legacy synchronous loop.

    This function is called by :func:`generate_reply` after context assembly
    (crisis check, profile loading, RAG retrieval) is complete. It handles the
    loop portion: model call → tool check → tool execution → re-call.
    """
    # ── Graph-based execution (P3: LangGraph StateGraph) ──
    if use_graph:
        try:
            graph_result = _run_via_graph(
                db=db,
                container=container,
                conversation_id=conversation_id,
                content=content,
                pinned_diaries_text=pinned_diaries_text,
                retrieved_diaries_text=retrieved_diaries_text,
                episodic_text=episodic_text,
                tools=tools,
                intent_result=intent_result,
                user_id=user_id,
            )
            if graph_result is not None:
                return graph_result
            # graph_result is None → graph unavailable, fall through to legacy
        except Exception as exc:
            logger.warning(
                "Graph execution failed, falling back to legacy loop: %s",
                exc,
            )

    # ── Legacy synchronous loop (fallback) ──
    with trace_span("S8_loop_legacy", "Legacy Loop") as span:
        # Get or create session context (task 8)
        session = get_or_create_session(conversation_id, container=container, user_id=user_id)

        # Intent-driven routing (replaces _needs_tool_call heuristic when available)
        if intent_result is not None:
            enable_tools = tools is not None and len(tools) > 0 and len(intent_result.need_tools) > 0
            tier = intent_result.tier
            max_iterations = intent_result.max_iterations
        else:
            # Fallback: legacy heuristic (backward compat for uncalled paths)
            enable_tools = tools is not None and len(tools) > 0 and _needs_tool_call(content)
            tier = "medium"
            max_iterations = MAX_LOOP_ITERATIONS

        # Build the base prompt
        system_prompt = CHAT_SYSTEM_PROMPT + _current_date_context()

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
        llm: LLMClient | None = container._llm_for_tier(db, tier, agent_name="chat")
        if llm is None:
            logger.warning("ConversationLoop: LLM unavailable")
            return LoopResult(
                reply_text=FALLBACK_FEEDBACK,
                token_info={},
                stop_reason="no_llm",
            )

        # Detect tool protocol path and build tool specs (after LLM is available)
        tool_specs = specs_for_names(list((tools or {}).keys())) if tools else []
        use_native = supports_native_tools(llm) and bool(tool_specs)
        bound_llm = None
        if use_native:
            try:
                bound_llm = llm.bind_tools(tool_specs)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.warning("bind_tools failed, falling back to text-tag: %s", exc)
                use_native = False

        if enable_tools and not use_native:
            system_prompt += build_tool_hint(tool_specs)

        # ── Agentic Loop (stage 4) ──
        total_usage: dict[str, int] = {}
        tool_calls_made: list[str] = []
        tool_results_text = ""
        current_prompt = f"{system_prompt}\n\n{base_user_prompt}"
        citations: list[Citation] = []

        # Track context sources as citations (pinned diaries, retrieved diaries, episodic)
        if pinned_diaries_text and pinned_diaries_text.strip():
            citations.append(
                Citation(
                    source_type="diary",
                    source_name="用户置顶日记",
                    content_summary=pinned_diaries_text[:100],
                )
            )
        if retrieved_diaries_text and retrieved_diaries_text.strip():
            citations.append(
                Citation(
                    source_type="diary",
                    source_name="检索日记",
                    content_summary=retrieved_diaries_text[:100],
                )
            )
        if episodic_text and episodic_text.strip():
            citations.append(
                Citation(
                    source_type="memory",
                    source_name="情景记忆",
                    content_summary=episodic_text[:100],
                )
            )

        for iteration in range(max_iterations):
            # 4.1 Context governance: check token budget
            # (SessionContext already manages history compression)

            # 4.2 Call model (native or fallback path)
            try:
                if use_native and bound_llm is not None:
                    response = bound_llm.invoke(current_prompt)
                else:
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
            if not enable_tools or iteration == max_iterations - 1:
                # No tools enabled, or max iterations reached
                stop_reason = "max_iterations" if (enable_tools and iteration > 0) else "completed"
                break

            # Parse tool calls (native or fallback path)
            if use_native:
                tool_call_results = extract_native_tool_calls(response)
            else:
                tool_call_results = parse_text_tag_calls(result_text)

            if not tool_call_results:
                # No tool calls in response — we're done
                stop_reason = "completed"
                break

            # 4.4 Execute tools and backfill results
            tool_results: list[str] = []
            for tc in tool_call_results:
                tool_calls_made.append(tc.name)
                result = _execute_tool(tc.name, tc.args, tools or {})
                tool_results.append(result)
                # Track tool result as citation
                citations.append(
                    Citation(
                        source_type="tool",
                        source_name=tc.name,
                        content_summary=result[:100],
                    )
                )

            tool_results_text = "\n".join(tool_results)
            stop_reason = "tool_called"
            # Loop continues to 4.1 for the next iteration

        # Clean up tool-call tags from final response (fallback path only)
        final_text = result_text if use_native else strip_tool_tags(result_text)
        if not final_text:
            final_text = FALLBACK_FEEDBACK

        # Append citations section (result integration enhancement)
        citations_section = _format_citations(citations)
        if citations_section:
            final_text += citations_section

        # Stage 5: Output aggregation — accumulate usage in session
        session.accumulate_usage(total_usage)
        session.add_turn(content, final_text)

        logger.info(
            "ConversationLoop completed: conversation=%s iterations=%d tools=%s tokens=%d stop=%s citations=%d",
            conversation_id,
            iteration + 1,
            tool_calls_made,
            total_usage.get("total_tokens_used", 0),
            stop_reason,
            len(citations),
        )

        if span:
            span.metadata["iterations"] = iteration + 1
            span.metadata["stop_reason"] = stop_reason

        return LoopResult(
            reply_text=final_text,
            token_info=total_usage,
            stop_reason=stop_reason,
            tool_calls_made=tool_calls_made,
            citations=citations,
        )


__all__ = [
    "MAX_LOOP_ITERATIONS",
    "Citation",
    "LoopResult",
    "run_conversation_loop",
]
