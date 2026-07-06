"""LangGraph StateGraph for scene-2 conversation orchestration.

Replaces the synchronous for-loop in conversation_loop.py with a
checkpointed conditional graph. Provides:
- Checkpointing: conversation state can be persisted and resumed
- Conditional routing: tool execution vs direct generation
- Observability: LangSmith integration (when configured)

Falls back to legacy conversation_loop when use_graph=False or when
LangGraph is not installed.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

# Try to import LangGraph — graceful degradation if not installed
try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None  # type: ignore[assignment, misc]
    END = None  # type: ignore[assignment]


class ConversationState(TypedDict, total=False):
    """State passed between graph nodes.

    Fields are populated incrementally as the graph executes:
    - preprocess_node: adds preprocess_result, updates content
    - understand_node: adds slot_result, retrieval_query
    - plan_node: adds enable_tools, tier, max_iterations, should_execute_tools
    - execute_tools_node: adds tool_results_text, tool_citations, tool_calls_made
    - generate_node: adds final_response, stop_reason, total_usage
    - postprocess_node: updates final_response, adds citations
    """

    # Input
    content: str
    brief_context: str
    intent_result: Any  # ChatIntentResult
    tools: dict[str, Any]  # ToolFn map
    tool_specs: list[Any]  # ToolSpec list
    llm: Any  # LLMClient
    system_prompt: str

    # Context sources
    pinned_diaries_text: str
    retrieved_diaries_text: str
    episodic_text: str

    # Preprocess output
    preprocess_result: Any  # PreprocessResult

    # Understand output
    slot_result: Any  # SlotResult
    retrieval_query: str

    # Plan output
    enable_tools: bool
    tier: str
    max_iterations: int
    should_execute_tools: bool

    # Execute tools output
    tool_results_text: str
    tool_citations: list[Any]  # list[Citation]
    tool_calls_made: list[str]

    # Generate output
    final_response: str
    stop_reason: str
    total_usage: dict[str, int]

    # Postprocess output
    citations: list[Any]  # list[Citation]

    # Metadata
    conversation_id: str


def build_conversation_graph(checkpointer: Any | None = None):
    """Build and compile the conversation StateGraph.

    Graph structure::

        preprocess → understand → plan → (conditional)
            ├─ yes → execute_tools → generate → postprocess → END
            └─ no  → generate → postprocess → END

    Args:
        checkpointer: LangGraph checkpointer (e.g., MemorySaver, SQLiteSaver).
                      If None, no checkpointing.

    Returns:
        Compiled graph, or None if LangGraph is not installed.
    """
    if not LANGGRAPH_AVAILABLE:
        logger.warning("LangGraph not installed; conversation graph unavailable")
        return None

    from app.services.ai.graph_nodes import (
        execute_tools_node,
        generate_node,
        plan_node,
        postprocess_node,
        preprocess_node,
        should_execute_tools,
        understand_node,
    )

    graph = StateGraph(ConversationState)

    # Add nodes
    graph.add_node("preprocess", preprocess_node)
    graph.add_node("understand", understand_node)
    graph.add_node("plan", plan_node)
    graph.add_node("execute_tools", execute_tools_node)
    graph.add_node("generate", generate_node)
    graph.add_node("postprocess", postprocess_node)

    # Set entry point
    graph.set_entry_point("preprocess")

    # Linear edges
    graph.add_edge("preprocess", "understand")
    graph.add_edge("understand", "plan")

    # Conditional edge: plan → execute_tools or generate
    graph.add_conditional_edges(
        "plan",
        should_execute_tools,
        {
            "yes": "execute_tools",
            "no": "generate",
        },
    )

    # execute_tools → generate → postprocess → END
    graph.add_edge("execute_tools", "generate")
    graph.add_edge("generate", "postprocess")
    graph.add_edge("postprocess", END)

    # Compile with optional checkpointer
    compile_kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    compiled = graph.compile(**compile_kwargs)
    logger.info("Conversation StateGraph compiled with checkpointer=%s", type(checkpointer).__name__)
    return compiled


def run_conversation_graph(
    graph,
    *,
    content: str,
    intent_result: Any = None,
    tools: dict[str, Any] | None = None,
    tool_specs: list[Any] | None = None,
    llm: Any = None,
    system_prompt: str = "",
    pinned_diaries_text: str = "",
    retrieved_diaries_text: str = "",
    episodic_text: str = "",
    brief_context: str = "",
    conversation_id: str = "",
) -> dict[str, Any]:
    """Run the compiled conversation graph.

    Args:
        graph: Compiled graph from build_conversation_graph().
        All other args: initial state for the graph.

    Returns:
        Final state dict with final_response, citations, total_usage, etc.
    """
    initial_state: ConversationState = {
        "content": content,
        "brief_context": brief_context,
        "intent_result": intent_result,
        "tools": tools or {},
        "tool_specs": tool_specs or [],
        "llm": llm,
        "system_prompt": system_prompt,
        "pinned_diaries_text": pinned_diaries_text,
        "retrieved_diaries_text": retrieved_diaries_text,
        "episodic_text": episodic_text,
        "conversation_id": conversation_id,
    }

    try:
        final_state = graph.invoke(initial_state)
        return final_state
    except Exception as exc:
        logger.error("Conversation graph execution failed: %s", exc)
        # Return a minimal state with fallback
        return {
            "final_response": "抱歉，我现在无法回复，请稍后再试。",
            "stop_reason": "error",
            "total_usage": {},
            "citations": [],
            "tool_calls_made": [],
        }


__all__ = [
    "LANGGRAPH_AVAILABLE",
    "ConversationState",
    "build_conversation_graph",
    "run_conversation_graph",
]
