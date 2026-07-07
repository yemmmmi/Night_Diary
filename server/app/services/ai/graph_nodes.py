"""Graph nodes for LangGraph StateGraph — scene-2 conversation orchestration.

Each node function takes a ``ConversationState`` and returns a partial state
update. The nodes are designed to be composable and testable independently.

Nodes:
- preprocess: input cleaning + normalization
- understand: intent classification + slot extraction + query rewriting
- plan: routing decision (tool execution vs direct generation)
- execute_tools: tool call execution (conditional)
- generate: LLM response generation
- postprocess: citation formatting + session update
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.domain.agents.slot_extractor import SlotExtractor
from app.services.ai.conversation_loop import (
    Citation,
    _execute_tool,
    _format_citations,
)
from app.services.ai.input_preprocessor import InputPreprocessor
from app.services.ai.prompts import FALLBACK_FEEDBACK
from app.services.ai.utils import extract_token_usage
from app.shared.llm import message_text
from app.shared.pipeline_trace import trace_span
from app.shared.tool_protocol import (
    build_tool_hint,
    extract_native_tool_calls,
    parse_text_tag_calls,
    strip_tool_tags,
    supports_native_tools,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def preprocess_node(state: dict[str, Any]) -> dict[str, Any]:
    """Node 1: Input preprocessing — text cleaning + security + omission."""
    with trace_span("S8.1_preprocess", "预处理节点", input_snapshot={"raw_text": state.get("content", "")}) as span:
        preprocessor = InputPreprocessor()
        content = state.get("content", "")
        context = state.get("brief_context", "")
        result = preprocessor.process(content, context=context)
        if span:
            span.metadata["safety_flag"] = result.security_flags.has_injection
        return {
            "content": result.clean_text,
            "preprocess_result": result,
        }


def understand_node(state: dict[str, Any]) -> dict[str, Any]:
    """Node 2: Semantic understanding — intent + slots + query rewrite.

    This node is a placeholder for the full understanding pipeline. In the
    graph version, the intent and slots are passed in from the caller (who
    already ran ChatIntentClassifier), so this node mainly handles slot
    extraction and query understanding.
    """
    with trace_span("S8.2_understand", "理解节点") as _span:
        content = state.get("content", "")
        intent_result = state.get("intent_result")
        intent_category = intent_result.intent_category if intent_result else ""

        # Slot extraction
        slot_extractor = SlotExtractor()
        slot_result = slot_extractor.extract(content, intent=intent_category)

        return {
            "slot_result": slot_result,
            "retrieval_query": content,  # Simplified: use content as retrieval query
        }


def plan_node(state: dict[str, Any]) -> dict[str, Any]:
    """Node 3: Planning — decide whether to execute tools or generate directly."""
    with trace_span("S8.3_plan", "计划节点") as span:
        intent_result = state.get("intent_result")
        tools = state.get("tools", {})

        if intent_result is not None:
            enable_tools = bool(tools) and len(intent_result.need_tools) > 0
            tier = intent_result.tier
            max_iterations = intent_result.max_iterations
        else:
            enable_tools = bool(tools)
            tier = "medium"
            max_iterations = 3

        if span:
            span.metadata["enable_tools"] = enable_tools
            span.metadata["tier"] = tier

        return {
            "enable_tools": enable_tools,
            "tier": tier,
            "max_iterations": max_iterations,
            "should_execute_tools": enable_tools,
        }


def should_execute_tools(state: dict[str, Any]) -> str:
    """Conditional edge: route to execute_tools or generate."""
    return "yes" if state.get("should_execute_tools") else "no"


def execute_tools_node(state: dict[str, Any]) -> dict[str, Any]:
    """Node 4: Tool execution — run tools and collect results.

    This is a simplified single-pass tool execution. The full Agentic Loop
    (multi-iteration) is handled by the legacy conversation_loop when
    use_graph=False.
    """
    with trace_span("S8.4_execute_tools", "工具执行节点") as span:
        tools = state.get("tools", {})
        content = state.get("content", "")
        llm = state.get("llm")
        tool_specs = state.get("tool_specs", [])

        if not llm or not tools:
            return {"tool_results_text": "", "tool_citations": []}

        # Build prompt with tool hint
        use_native = supports_native_tools(llm) and bool(tool_specs)
        bound_llm = None
        if use_native:
            try:
                bound_llm = llm.bind_tools(tool_specs)
            except Exception:
                use_native = False

        system_prompt = state.get("system_prompt", "")
        prompt = f"{system_prompt}\n\n{content}"
        if not use_native:
            prompt += build_tool_hint(tool_specs)

        try:
            if use_native and bound_llm is not None:
                response = bound_llm.invoke(prompt)
                tool_calls = extract_native_tool_calls(response)
            else:
                response = llm.invoke(prompt)
                result_text = message_text(response).strip()
                tool_calls = parse_text_tag_calls(result_text)
        except Exception as exc:
            logger.warning("execute_tools_node LLM invoke failed: %s", exc)
            return {"tool_results_text": "", "tool_citations": []}

        # Execute tool calls
        tool_results: list[str] = []
        tool_citations: list[Citation] = []
        tool_calls_made: list[str] = []

        for tc in tool_calls:
            tool_calls_made.append(tc.name)
            result = _execute_tool(tc.name, tc.args, tools)
            tool_results.append(result)
            tool_citations.append(
                Citation(
                    source_type="tool",
                    source_name=tc.name,
                    content_summary=result[:100],
                )
            )

        if span:
            span.metadata["tool_calls"] = tool_calls_made

        return {
            "tool_results_text": "\n".join(tool_results),
            "tool_citations": tool_citations,
            "tool_calls_made": tool_calls_made,
            "_tool_response": response,  # Pass through for generate node
        }


def generate_node(state: dict[str, Any]) -> dict[str, Any]:
    """Node 5: Response generation — LLM call with context."""
    with trace_span("S8.5_generate", "生成节点") as span:
        llm = state.get("llm")
        if llm is None:
            return {
                "final_response": FALLBACK_FEEDBACK,
                "stop_reason": "no_llm",
                "total_usage": {},
            }

        content = state.get("content", "")
        system_prompt = state.get("system_prompt", "")
        tool_results_text = state.get("tool_results_text", "")

        # Build final prompt
        prompt = f"{system_prompt}\n\n用户消息：{content}"
        if tool_results_text:
            prompt += f"\n\n## 工具结果\n{tool_results_text}"

        try:
            response = llm.invoke(prompt)
        except Exception as exc:
            logger.warning("generate_node LLM invoke failed: %s", exc)
            return {
                "final_response": FALLBACK_FEEDBACK,
                "stop_reason": "error",
                "total_usage": {},
            }

        usage = extract_token_usage(response)
        result_text = message_text(response).strip()

        # Clean up tool tags (fallback path)
        final_text = strip_tool_tags(result_text)
        if not final_text:
            final_text = FALLBACK_FEEDBACK

        stop_reason = "completed"
        if span:
            span.metadata["stop_reason"] = stop_reason

        return {
            "final_response": final_text,
            "stop_reason": stop_reason,
            "total_usage": usage,
        }


def postprocess_node(state: dict[str, Any]) -> dict[str, Any]:
    """Node 6: Post-processing — citations + session update."""
    with trace_span("S8.6_postprocess", "后处理节点") as span:
        final_response = state.get("final_response", FALLBACK_FEEDBACK)

        # Collect all citations
        citations: list[Citation] = []

        # Context source citations
        pinned_diaries_text = state.get("pinned_diaries_text", "")
        retrieved_diaries_text = state.get("retrieved_diaries_text", "")
        episodic_text = state.get("episodic_text", "")

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

        # Tool citations
        tool_citations = state.get("tool_citations", [])
        citations.extend(tool_citations)

        # Append citations section
        citations_section = _format_citations(citations)
        if citations_section:
            final_response += citations_section

        if span:
            span.metadata["citation_count"] = len(citations)

        return {
            "final_response": final_response,
            "citations": citations,
        }


__all__ = [
    "execute_tools_node",
    "generate_node",
    "plan_node",
    "postprocess_node",
    "preprocess_node",
    "should_execute_tools",
    "understand_node",
]
