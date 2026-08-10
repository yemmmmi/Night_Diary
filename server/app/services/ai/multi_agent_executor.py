"""Multi-Agent executor — wires Phase B graph + WorkingMemory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from app.domain.agents.graph import MultiAgentGraph
from app.domain.agents.state import MultiAgentState
from app.domain.memory.episodic import EpisodicMemory
from app.domain.memory.long_term import LongTermMemory
from app.domain.memory.working import WorkingMemory
from app.services.ai.prompts import FALLBACK_FEEDBACK

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MultiAgentRunResult:
    text: str
    tokens: dict[str, int]
    log: str
    tier: str
    intent: str = ""
    activated_agents: list[str] = field(default_factory=list)
    activated_skills: list[str] = field(default_factory=list)
    referenced_memory_count: int = 0


def _load_episodic_context(
    episodic: EpisodicMemory | None,
    query: str = "",
) -> list[dict[str, Any]]:
    if episodic is None:
        return []
    try:
        entries = episodic.retrieve_relevant(query=query, top_k=5)
        return [
            {
                "event_summary": entry.event_summary,
                "emotion": entry.emotion,
                "reply_insight": entry.reply_insight,
                "timestamp": entry.timestamp,
            }
            for entry in entries
        ]
    except Exception as exc:
        logger.warning("Episodic memory load failed: %s", exc)
        return []


async def _invoke_graph(graph: MultiAgentGraph, initial_state: MultiAgentState) -> MultiAgentState:
    return await graph.invoke(initial_state)


def run_multi_agent(
    graph: MultiAgentGraph,
    *,
    diary_id: int,
    diary_content: str,
    episodic: EpisodicMemory | None = None,
    long_term: LongTermMemory | None = None,
    working_memory: WorkingMemory | None = None,
    style_fragment: str | None = None,
) -> MultiAgentRunResult:
    """Execute the multi-agent pipeline."""
    episodic_context = _load_episodic_context(episodic, query=diary_content)
    long_term_profile: dict[str, Any] = {}
    if long_term is not None:
        try:
            long_term_profile = long_term.get_profile("default").model_dump()
        except Exception as exc:
            logger.warning("Long-term memory load failed: %s", exc)

    if working_memory is not None:
        from app.domain.memory.types import UserProfile

        working_memory.load_context(
            str(diary_id),
            UserProfile.model_validate(long_term_profile) if long_term_profile else UserProfile(),
        )
        # Seed working memory with session data (without episodic_context to
        # avoid premature compression — the graph handles that in
        # prepare_compressed_history).
        ctx = working_memory.context
        if ctx is not None:
            working_memory.update_context(
                ctx,
                {"diary_content": diary_content, "long_term_profile": long_term_profile},
            )

    initial_state: MultiAgentState = {
        "diary_id": str(diary_id),
        "diary_content": diary_content,
        "style_fragment": style_fragment or "",
        "intent": "",
        "tier": "",
        "token_budget": 0,
        "activated_agents": [],
        "activated_skills": [],
        "episodic_context": episodic_context,
        "long_term_profile": long_term_profile,
        "compressed_history": "",
        "retrieval_context": "",
        "empathy_response": "",
        "insight_response": "",
        "final_response": "",
        "total_tokens_used": 0,
        "agent_mode": "multi_agent",
        "cache_hit_tokens": 0,
        "cache_miss_tokens": 0,
        "output_tokens": 0,
        "errors": [],
    }

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                final_state = pool.submit(asyncio.run, _invoke_graph(graph, initial_state)).result()
        else:
            final_state = loop.run_until_complete(_invoke_graph(graph, initial_state))
    except RuntimeError:
        final_state = asyncio.run(_invoke_graph(graph, initial_state))

    final_response = final_state.get("final_response", "")
    if not final_response or not str(final_response).strip():
        final_response = FALLBACK_FEEDBACK

    # Sync final state back to working memory — enforces token limits on
    # generated context fields and persists the session context.
    if working_memory is not None and working_memory.is_active:
        ctx = working_memory.context
        if ctx is not None:
            working_memory.update_context(
                ctx,
                {
                    "retrieval_context": final_state.get("retrieval_context", ""),
                    "empathy_response": final_state.get("empathy_response", ""),
                    "insight_response": final_state.get("insight_response", ""),
                    "compressed_history": final_state.get("compressed_history", ""),
                    "final_response": final_response,
                },
            )
            wm_tokens = working_memory.get_context_tokens_used()
            if wm_tokens > 0:
                logger.info(
                    "WorkingMemory final tokens=%d/%d diary_id=%s",
                    wm_tokens,
                    WorkingMemory.MAX_CONTEXT_TOKENS,
                    diary_id,
                )

    tier = str(final_state.get("tier", "medium"))
    activated_agents = list(final_state.get("activated_agents", []))
    activated_skills = list(final_state.get("activated_skills", []))
    intent = str(final_state.get("intent", "unknown"))
    errors = final_state.get("errors", [])

    thk_log_parts = [f"[Multi-Agent] intent={intent}, tier={tier}, agents={activated_agents}"]
    if errors:
        thk_log_parts.append(f"[Errors] {'; '.join(errors)}")
    thk_log = "\n".join(thk_log_parts)

    token_info = {
        "total_tokens_used": int(final_state.get("total_tokens_used", 0)),
        "cache_hit_tokens": int(final_state.get("cache_hit_tokens", 0)),
        "cache_miss_tokens": int(final_state.get("cache_miss_tokens", 0)),
        "output_tokens": int(final_state.get("output_tokens", 0)),
    }
    return MultiAgentRunResult(
        text=str(final_response),
        tokens=token_info,
        log=thk_log,
        tier=tier,
        intent=intent,
        activated_agents=activated_agents,
        activated_skills=activated_skills,
        referenced_memory_count=len(episodic_context),
    )


async def run_multi_agent_streaming(
    *,
    graph: MultiAgentGraph,
    state: MultiAgentState,
    workers: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    """Native async streaming of the multi-agent reply — no thread-pool wrapper.

    Unlike :func:`run_multi_agent`, which wraps ``graph.invoke`` in a
    ``ThreadPoolExecutor`` + ``asyncio.run`` (and therefore blows up with
    "asyncio.run() cannot be called from a running event loop" when invoked from
    inside an existing loop), this is a plain ``async`` generator: it can be
    ``async for``-driven directly from a FastAPI request handler or any other
    already-running loop.

    The ``graph`` and ``state`` are supplied by the caller — this helper stays
    single-responsibility and only bridges :meth:`MultiAgentGraph.invoke_streaming`
    to a token-only stream. ``workers`` is forwarded unchanged so the caller can
    inject streaming-capable agent instances (exposing ``run_streaming``) that
    :meth:`SupervisorAgent.synthesize_streaming` needs to stream straight from a
    worker.

    Yields:
        Reply tokens (``str``) produced by the graph's synthesis phase, in order.
    """
    _, token_stream = await graph.invoke_streaming(state, workers=workers)
    async for token in token_stream:
        yield token
