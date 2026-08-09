"""PlannerAgent — multi-turn plan exploration skill (V3 P2).

Triggered by the ``plan_exploration`` intent in ConversationLoop. Handles:

1. Crisis short-circuit (defense line: never plan around crisis content)
2. Information completeness assessment (what / how)
3. Multi-turn clarification (emit clarification_request protocol block)
4. Plan proposal generation (emit plan_proposal protocol block with source refs)

The agent has ZERO write permissions — it never creates tasks/plans
directly. All writes happen via the user accepting a proposal in the
frontend, which calls the REST API.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.domain.agents.plan_completeness import assess_plan_completeness
from app.shared.crisis_guard import CrisisGuard
from app.shared.llm import LLMClient, message_text
from app.shared.streaming_events import (
    publish_protocol_block,
    publish_reply_end,
    publish_reply_start,
    publish_text_delta,
)

logger = logging.getLogger(__name__)

_PLAN_PROPOSAL_PROMPT = """你是一个温和的生活规划助手。基于用户的对话，生成一个计划提案。

约束：
1. 最多 5 个 task，避免认知过载
2. 禁止使用"必须""应该""一定要"等施压措辞，用"可以""试试""不妨"
3. motivation 字段：如果有相关历史数据（日记/记忆），附引用；否则诚实说明"基于本次对话的建议"
4. 输出严格 JSON，格式：{{"title": str, "motivation": str, "tasks": [{{"title": str, "note": str|null, "due_date": str|null}}]}}

用户目标：{what}
用户方法：{how}
相关历史：{context}

请生成 JSON："""


@dataclass
class PlannerInput:
    """Input to PlannerAgent.run."""

    user_input: str
    prior_context: str  # 上一轮的累积上下文（多轮累积）
    trace_id: str
    user_id: str
    conversation_id: str
    source_refs: list[dict[str, Any]] | None = None  # RAG 检索的相关日记/记忆


class PlannerAgent:
    """Multi-turn plan exploration skill agent.

    Stateless per-invocation — multi-turn state is managed by the caller
    (ConversationLoop passes prior_context accumulated across turns).
    """

    def __init__(self, llm: LLMClient, crisis_guard: CrisisGuard | None = None) -> None:
        self._llm = llm
        self._crisis = crisis_guard or CrisisGuard()

    async def run(self, inp: PlannerInput) -> None:
        """Execute one turn of plan exploration.

        Publishes to TraceEventBus:
        - crisis: TEXT_DELTA(safe_response) only
        - incomplete (missing what): clarification_request PROTOCOL_BLOCK
        - complete (has what): plan_proposal PROTOCOL_BLOCK
        Always publishes REPLY_START and REPLY_END.
        """
        await publish_reply_start(inp.trace_id, intent="plan_exploration")

        # Defense: crisis short-circuit
        if self._crisis.detect(inp.user_input) or self._crisis.detect(inp.prior_context):
            await publish_text_delta(inp.trace_id, self._crisis.safe_response)
            await publish_reply_end(inp.trace_id)
            return

        completeness = assess_plan_completeness(inp.user_input, inp.prior_context)

        if not completeness.is_complete:
            # 缺 what —— 反问目标
            question = "你想达成什么目标呢？可以告诉我你想养成什么习惯，或者想完成什么事。"
            await publish_protocol_block(
                inp.trace_id,
                block_type="clarification_request",
                block_id=f"clarify-{inp.trace_id}",
                data={
                    "question": question,
                    "missing_fields": completeness.missing_fields,
                    "context": completeness.context,
                },
            )
            await publish_reply_end(inp.trace_id)
            return

        # 信息完整（有 what）—— 生成 plan_proposal（how 缺失时 Agent 会提供建议）
        await self._emit_plan_proposal(inp, completeness)

    async def _emit_plan_proposal(self, inp: PlannerInput, completeness: Any) -> None:
        """Generate a plan proposal via LLM and publish it as protocol block."""
        prompt = _PLAN_PROPOSAL_PROMPT.format(
            what=completeness.what or inp.user_input,
            how=completeness.how or "（用户未指定，请提供建议）",
            context=json.dumps(inp.source_refs or [], ensure_ascii=False),
        )

        try:
            response = await self._llm.ainvoke(prompt)
            raw = message_text(response).strip()
            cleaned = self._strip_code_fence(raw)
            proposal_data = json.loads(cleaned)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Plan proposal LLM/parse failed: %s", exc)
            proposal_data = {
                "title": completeness.what or "新计划",
                "motivation": "基于本次对话的建议",
                "tasks": [{"title": completeness.what or "开始第一步", "note": None, "due_date": None}],
            }

        # Pre-publish crisis check on generated content
        proposal_text = proposal_data.get("motivation", "") + " ".join(
            t.get("title", "") for t in proposal_data.get("tasks", [])
        )
        if self._crisis.detect(proposal_text):
            await publish_text_delta(inp.trace_id, self._crisis.safe_response)
            await publish_reply_end(inp.trace_id)
            return

        # Attach source_refs if provided by caller (RAG results)
        if inp.source_refs:
            proposal_data["source_refs"] = inp.source_refs
        else:
            proposal_data["source_refs"] = []

        proposal_data["status"] = "awaiting_confirmation"

        await publish_protocol_block(
            inp.trace_id,
            block_type="plan_proposal",
            block_id=f"proposal-{inp.trace_id}",
            data=proposal_data,
        )
        await publish_reply_end(inp.trace_id)

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """Remove markdown ```json ... ``` fence if present."""
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            return "\n".join(lines).strip()
        return text
