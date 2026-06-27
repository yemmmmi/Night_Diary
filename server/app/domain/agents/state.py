"""Shared LangGraph state for the multi-agent pipeline.

``MultiAgentState`` is the typed channel that the Supervisor and Worker agents
read from and write to. List/counter fields carry ``Annotated`` reducers so that
agents running in parallel (``asyncio.gather`` fan-out in B-9) merge their
partial updates deterministically instead of clobbering each other.

Migrated from V1 ``agents/state.py`` with two V2 changes:

* ``user_id``/``diary_nid`` (int, multi-user) are dropped in favour of a single
  ``diary_id: str`` — V2 is a single-user local app and the rest of the domain
  layer already keys on ``diary_id``.
* ``activated_skills`` is added so the Skill system (integrated into the
  Supervisor in B-9) can record which skills fired alongside ``activated_agents``.

This module intentionally has **no** ``langgraph`` import: it only declares the
state shape and reducers, so it stays importable in unit tests without the graph
runtime (which arrives in B-9).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_unique(left: list[str], right: list[str]) -> list[str]:
    """Reducer: concatenate two lists, dropping duplicates, preserving order.

    Used for ``activated_agents`` / ``activated_skills`` so concurrent writers
    never produce duplicate entries when the same agent/skill is recorded twice.
    """
    seen = set(left)
    result = list(left)
    for item in right:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def extract_token_usage(response: Any) -> dict[str, int]:
    """Pull token usage out of a LangChain ``AIMessage``'s ``response_metadata``.

    Centralised here so every agent node reports usage the same way. Returns
    zeros when the response carries no usage block (e.g. a fallback reply).

    DeepSeek/OpenAI usage shape::

        {"prompt_tokens", "completion_tokens", "total_tokens",
         "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"}
    """
    usage: dict[str, Any] = {}
    metadata = getattr(response, "response_metadata", None)
    if isinstance(metadata, dict):
        raw = metadata.get("token_usage", {})
        if isinstance(raw, dict):
            usage = raw

    return {
        "total_tokens_used": int(usage.get("total_tokens", 0) or 0),
        "cache_hit_tokens": int(usage.get("prompt_cache_hit_tokens", 0) or 0),
        "cache_miss_tokens": int(usage.get("prompt_cache_miss_tokens", 0) or 0),
        "output_tokens": int(usage.get("completion_tokens", 0) or 0),
    }


class MultiAgentState(TypedDict, total=False):
    """LangGraph shared state passed between Supervisor and Worker nodes.

    ``total=False`` because graph nodes return *partial* updates; the reducers on
    annotated fields define how those partials combine.
    """

    # ---- Input ----
    diary_id: str
    diary_content: str
    style_fragment: str  # per-request replier style override (warm/pragmatic/calm 或自定义人设文本)

    # ---- Supervisor output ----
    intent: str  # pure_record | emotional_support | retrospective_review | habit_tracking
    tier: str  # light | medium | heavy | crisis (derived from intent + crisis signal)
    token_budget: int
    activated_agents: Annotated[list[str], merge_unique]
    activated_skills: Annotated[list[str], merge_unique]

    # ---- Memory context ----
    episodic_context: list[dict[str, Any]]
    long_term_profile: dict[str, Any]
    compressed_history: str

    # ---- Worker output ----
    retrieval_context: str
    empathy_response: str
    insight_response: str

    # ---- Final output ----
    final_response: str
    agent_mode: str
    thk_log: str

    # ---- Token tracking (summed across nodes) ----
    total_tokens_used: Annotated[int, operator.add]
    cache_hit_tokens: Annotated[int, operator.add]
    cache_miss_tokens: Annotated[int, operator.add]
    output_tokens: Annotated[int, operator.add]

    # ---- Error tracking (appended across concurrent workers) ----
    errors: Annotated[list[str], operator.add]


__all__ = ["MultiAgentState", "extract_token_usage", "merge_unique"]
