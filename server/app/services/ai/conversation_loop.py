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

import asyncio
import concurrent.futures
import contextlib
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
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
from app.shared.crisis_guard import CrisisGuard
from app.shared.llm import LLMClient, message_text
from app.shared.middleware import MiddlewareContext, MiddlewarePipeline
from app.shared.pipeline_trace import trace_span
from app.shared.streaming_events import (
    publish_reply_end,
    publish_reply_start,
    publish_retract,
    publish_text_delta,
    publish_text_end,
)
from app.shared.streaming_safety import StreamingSafetyGuard
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
    llm = container._llm_for_tier(tier, agent_name="conversation_graph")
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


# ── P2: plan_exploration multi-turn context storage ──
# Module-level store keyed by conversation_id so the PlannerAgent can
# accumulate clarifications across turns. SessionContext is a frozen-ish
# dataclass for chat history; the plan context lives here to keep that
# responsibility cleanly separated.
_plan_exploration_contexts: dict[str, str] = {}


def _get_plan_context(session: Any) -> str | None:
    """Return the accumulated plan_exploration context for a session."""
    conv_id = getattr(session, "conversation_id", None) or str(id(session))
    return _plan_exploration_contexts.get(conv_id)


def _set_plan_context(session: Any, context: str) -> None:
    """Store the accumulated plan_exploration context for a session."""
    conv_id = getattr(session, "conversation_id", None) or str(id(session))
    _plan_exploration_contexts[conv_id] = context


def _run_planner_sync(planner: Any, inp: Any) -> None:
    """Bridge async ``PlannerAgent.run`` into the synchronous legacy loop.

    The legacy ``run_conversation_loop`` is synchronous (called from the
    synchronous ``generate_reply``), but ``PlannerAgent.run`` is a
    coroutine.  ``asyncio.run`` is used when no loop is running (the common
    production path); when a loop is already running we offload to a worker
    thread so we never nest event loops.
    """
    coro = planner.run(inp)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — the typical production path.
        asyncio.run(coro)
        return
    # Already inside a running loop (e.g. an async test harness): run the
    # coroutine in a dedicated thread with its own fresh event loop.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, coro).result()


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
        llm: LLMClient | None = container._llm_for_tier(tier, agent_name="chat")
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

        # ── P2: plan_exploration 意图分支 → PlannerAgent ──
        # Route to PlannerAgent before entering the Agentic Loop so the
        # plan skill owns multi-turn clarification / proposal flow.
        if (
            intent_result is not None
            and intent_result.intent_category == "plan_exploration"
        ):
            from app.domain.agents.planner_agent import PlannerAgent, PlannerInput

            prior_context = _get_plan_context(session) or ""
            planner = PlannerAgent(llm=llm)
            planner_inp = PlannerInput(
                user_input=content,
                prior_context=prior_context,
                trace_id="",  # legacy loop has no trace_id (streaming only)
                user_id=user_id,
                conversation_id=conversation_id,
            )
            try:
                _run_planner_sync(planner, planner_inp)
            except Exception as exc:
                logger.warning("PlannerAgent failed in legacy loop: %s", exc)
            # Persist accumulated context for multi-turn clarification.
            _set_plan_context(session, f"{prior_context}\n{content}".strip())
            return LoopResult(
                reply_text=FALLBACK_FEEDBACK,
                token_info={},
                stop_reason="completed",
            )

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


async def run_conversation_loop_streaming(
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
    trace_id: str = "",
    middleware_pipeline: MiddlewarePipeline | None = None,
) -> AsyncGenerator[str | dict[str, Any], None]:
    """Streaming variant of :func:`run_conversation_loop` for V3 P0.

    Tool-call rounds remain non-streaming (``invoke``); only the final reply
    round uses ``astream`` wrapped by :class:`StreamingSafetyGuard`.

    V3 P7: when *middleware_pipeline* is provided (and non-empty), its
    ``on_system_prompt`` hook runs over the assembled system prompt before
    the first LLM call (e.g. :class:`SafetyMiddleware` injects the shared
    crisis-response instruction).

    Yields:
        ``str`` — safe text tokens to forward to the frontend.
        ``{"retract": True, "replacement": str}`` — crisis detected mid-stream;
            caller must stop after emitting the RETRACT event.

    This function does **not** handle crisis short-circuit (Stage 2) — the
    caller (:func:`generate_reply`) is responsible for routing crisis intents
    to the non-streaming path. This function only handles safe intents whose
    final reply should be streamed.
    """
    # ── Stage 1-3: Session + context assembly (mirrors legacy loop) ──
    session = get_or_create_session(conversation_id, container=container, user_id=user_id)

    # Intent-driven routing
    if intent_result is not None:
        enable_tools = tools is not None and len(tools) > 0 and len(intent_result.need_tools) > 0
        tier = intent_result.tier
        max_iterations = intent_result.max_iterations
        intent = intent_result.intent_category
    else:
        enable_tools = tools is not None and len(tools) > 0 and _needs_tool_call(content)
        tier = "medium"
        max_iterations = MAX_LOOP_ITERATIONS
        intent = "casual_chat"

    # Build the base prompt
    system_prompt = CHAT_SYSTEM_PROMPT + _current_date_context()

    # V3 P7: optional middleware pipeline — on_system_prompt hooks (e.g. the
    # SafetyMiddleware crisis instruction) run before any LLM call. An empty
    # pipeline is skipped entirely (zero overhead for simple scenes).
    #
    # V3.x: compute the user-mode once and share it through the context so
    # ModePromptBuilder does not re-read daily_modes, and surface the resulting
    # mode to the frontend as a ``mode_state`` protocol block (badge update +
    # one-time gentle notice).
    current_mode: str | None = None
    if middleware_pipeline is not None and not middleware_pipeline.is_empty:
        system_prompt = middleware_pipeline.apply_system_prompt(
            system_prompt,
            MiddlewareContext(
                scenario="conversation",
                user_id=user_id,
                content=content,
                intent=intent,
                trace_id=trace_id,
                conversation_id=conversation_id,
                # Request-scoped session + precomputed mode for presentation
                # middlewares such as ModePromptBuilder. Kept in ``extra`` so
                # unrelated middlewares never depend on a specific key.
                extra={"db": db, "current_mode": current_mode},
            ),
        )
        # Best-effort mode for the mode_state event.
        try:
            if current_mode is None:
                from app.services.ai.mood_monitor import MoodMonitor

                mode_val = MoodMonitor().effective_mode(
                    db, user_id=user_id, day=date.today()
                )
                current_mode = mode_val
        except Exception:
            current_mode = None
        if current_mode is not None and trace_id:
            from app.shared.streaming_events import publish_protocol_block

            await publish_protocol_block(
                trace_id,
                block_type="mode_state",
                block_id=f"mode-{user_id}-{date.today().isoformat()}",
                data={"mode": current_mode, "light_notice": False},
            )

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
    llm: LLMClient | None = container._llm_for_tier(tier, agent_name="chat")
    if llm is None:
        logger.warning("ConversationLoop streaming: LLM unavailable")
        await publish_reply_start(trace_id, intent=intent, reply_id=conversation_id)
        await publish_text_delta(trace_id, FALLBACK_FEEDBACK)
        await publish_text_end(trace_id)
        session.add_turn(content, FALLBACK_FEEDBACK)
        await publish_reply_end(trace_id, citations=[], usage={})
        yield FALLBACK_FEEDBACK
        return

    # ── P2: plan_exploration 意图分支 → PlannerAgent (streaming) ──
    # PlannerAgent publishes its own REPLY_START / protocol blocks / REPLY_END,
    # so we delegate and return immediately without entering the Agentic Loop.
    if (
        intent_result is not None
        and intent_result.intent_category == "plan_exploration"
    ):
        from app.domain.agents.planner_agent import PlannerAgent, PlannerInput

        planner = PlannerAgent(llm=llm)
        prior_context = _get_plan_context(session) or ""
        planner_inp = PlannerInput(
            user_input=content,
            prior_context=prior_context,
            trace_id=trace_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        await planner.run(planner_inp)
        _set_plan_context(session, f"{prior_context}\n{content}".strip())
        return  # PlannerAgent already emitted all events

    # Detect tool protocol path and build tool specs
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

    # ── Stage 4a: Tool-call rounds (non-streaming, invoke) ──
    # Leave the last iteration for the streaming final reply.
    total_usage: dict[str, int] = {}
    tool_calls_made: list[str] = []
    tool_results_text = ""
    current_prompt = f"{system_prompt}\n\n{base_user_prompt}"
    citations: list[Citation] = []

    # Track context sources as citations
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

    tool_rounds = max(0, max_iterations - 1) if enable_tools else 0
    for iteration in range(tool_rounds):
        # 4.2 Call model (same as legacy loop)
        try:
            if use_native and bound_llm is not None:
                response = bound_llm.invoke(current_prompt)
            else:
                if tool_results_text:
                    current_prompt += f"\n\n## 工具结果\n{tool_results_text}"
                response = llm.invoke(current_prompt)
        except Exception as exc:
            logger.warning(
                "ConversationLoop streaming LLM invoke failed (iter %d): %s",
                iteration,
                exc,
            )
            citation_dicts = [
                {
                    "source_type": c.source_type,
                    "source_name": c.source_name,
                    "content_summary": c.content_summary,
                }
                for c in citations
            ]
            await publish_reply_start(trace_id, intent=intent, reply_id=conversation_id)
            await publish_text_delta(trace_id, FALLBACK_FEEDBACK)
            await publish_text_end(trace_id)
            session.accumulate_usage(total_usage)
            session.add_turn(content, FALLBACK_FEEDBACK)
            await publish_reply_end(
                trace_id, citations=citation_dicts, usage=total_usage
            )
            yield FALLBACK_FEEDBACK
            return

        turn_usage = extract_token_usage(response)
        total_usage = merge_token_info(total_usage, turn_usage)
        result_text = message_text(response).strip()

        # Parse tool calls
        if use_native:
            tool_call_results = extract_native_tool_calls(response)
        else:
            tool_call_results = parse_text_tag_calls(result_text)

        if not tool_call_results:
            # No more tool calls — proceed to final streaming reply
            break

        # Execute tools and backfill results
        tool_results: list[str] = []
        for tc in tool_call_results:
            tool_calls_made.append(tc.name)
            result = _execute_tool(tc.name, tc.args, tools or {})
            tool_results.append(result)
            citations.append(
                Citation(
                    source_type="tool",
                    source_name=tc.name,
                    content_summary=result[:100],
                )
            )
        tool_results_text = "\n".join(tool_results)

    # ── Stage 4b: Final streaming reply round ──
    final_prompt = current_prompt
    if tool_results_text:
        final_prompt += f"\n\n## 工具结果\n{tool_results_text}"

    # Build safety guard
    cg = crisis_guard if crisis_guard is not None else CrisisGuard()
    guard = StreamingSafetyGuard(crisis_guard=cg)

    citation_dicts = [
        {
            "source_type": c.source_type,
            "source_name": c.source_name,
            "content_summary": c.content_summary,
        }
        for c in citations
    ]

    # Defense line 1: should we stream at all?
    # (Should not happen — caller filters crisis in Stage 2 — but safety net.)
    if not guard.should_stream_directly(intent, content):
        safe_text = cg.safe_response
        await publish_reply_start(trace_id, intent=intent, reply_id=conversation_id)
        await publish_text_delta(trace_id, safe_text)
        await publish_text_end(trace_id)
        session.accumulate_usage(total_usage)
        session.add_turn(content, safe_text)
        await publish_reply_end(trace_id, citations=citation_dicts, usage=total_usage)
        yield safe_text
        return

    # Publish REPLY_START
    await publish_reply_start(trace_id, intent=intent, reply_id=conversation_id)

    # Raw token stream with astream -> ainvoke fallback
    async def _raw_stream() -> AsyncGenerator[str, None]:
        try:
            async for token in llm.astream(final_prompt):
                yield token
        except (AttributeError, NotImplementedError):
            # LLM does not support astream — degrade to ainvoke (single chunk)
            response = await llm.ainvoke(final_prompt)
            yield message_text(response)

    # Stream through safety guard (defense lines 2 + 3)
    aggregated_text = ""
    async for item in guard.filter_stream(_raw_stream(), intent):
        if isinstance(item, dict):
            # RETRACT — crisis detected mid-stream
            replacement = str(item.get("replacement", ""))
            await publish_retract(
                trace_id, reason="crisis_in_stream", replacement=replacement
            )
            session.accumulate_usage(total_usage)
            session.add_turn(content, replacement)
            await publish_reply_end(trace_id, citations=citation_dicts, usage=total_usage)
            yield item
            return
        # Safe token — forward to caller and publish TEXT_DELTA
        token = item
        aggregated_text += token
        yield token
        await publish_text_delta(trace_id, token)

    # Normal completion
    await publish_text_end(trace_id)

    # Append citations section
    citations_section = _format_citations(citations)
    if citations_section:
        aggregated_text += citations_section

    # Update session
    session.accumulate_usage(total_usage)
    session.add_turn(content, aggregated_text)

    logger.info(
        "ConversationLoop streaming completed: conversation=%s tools=%s tokens=%d citations=%d",
        conversation_id,
        tool_calls_made,
        total_usage.get("total_tokens_used", 0),
        len(citations),
    )

    # Publish REPLY_END
    await publish_reply_end(trace_id, citations=citation_dicts, usage=total_usage)


__all__ = [
    "MAX_LOOP_ITERATIONS",
    "Citation",
    "LoopResult",
    "run_conversation_loop",
    "run_conversation_loop_streaming",
]
