"""PlannerAgent — multi-turn plan exploration skill (V3 P2, extended in V3.2).

Triggered by the ``plan_exploration`` intent in ConversationLoop. Handles:

1. Crisis short-circuit (defense line: never plan around crisis content)
2. Information completeness assessment (what / how)
3. Multi-turn clarification (emit clarification_request protocol block)
4. Plan proposal generation (emit plan_proposal protocol block with source refs)
5. **Existing-plan modification proposal** (V3.2): when the user asks to adjust /
   archive / clean an *existing* plan or task, emit a ``plan_modify`` protocol
   block describing the proposed change (instead of a brand-new plan proposal).

The agent has ZERO write permissions — it never creates/modifies/archives/closes
tasks or plans directly. All writes happen via the user accepting a proposal in the
frontend, which calls the REST API (proposal-confirm path, unchanged).
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
    publish_text_end,
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

# V3.2: 对"既有计划/任务提修改"的信号词。命中这些即优先产出
# ``plan_modify`` 提案（adjust/archive/clean），而不是新建 plan_proposal。
_PLAN_MODIFY_KEYWORDS = (
    "改一下",
    "调整",
    "改成",
    "修改",
    "去掉",
    "删掉",
    "删除",
    "清掉",
    "清理",
    "不做了",
    "放弃",
    "暂停",
    "归档",
    "收起来",
    "这个计划",
    "这个任务",
    "这条",
    "现有计划",
    "之前的计划",
    "上周那个",
    "简化",
    "精简",
    "换一种",
)


def _looks_like_modify(user_input: str) -> bool:
    """Heuristic: does the user refer to an existing plan/task to change it?"""
    return any(kw in user_input for kw in _PLAN_MODIFY_KEYWORDS)


_PLAN_MODIFY_PROMPT = """你是用户的并列生活助手，协助记录、规划与复盘。用户希望对**已有的某个计划或任务**进行调整，而不是新建。请基于提供的当前计划/任务清单，生成一个「修改提案」。

操作类型（operation）：
- "adjust"：调整某个计划或任务的字段（如标题、备注、截止日期）。
- "archive"：归档/收起的某个计划或任务（使其不再活跃）。
- "clean"：清理/删掉某个已不需要的计划或任务。

约束：
1. 只能针对"当前计划清单"里真实存在的计划/任务（target 必须引用其 id 与 title）。
2. 每次最多改动 1 个目标，明确给出 changes（要改成什么新值，如 title/new_due_date）。
3. 禁止使用"必须""应该""一定要"等施压措辞；用温和建议的口吻。
4. 只是提案，实际改动由用户在前端确认后落库（你零写权限）。
5. 输出严格 JSON，格式：{{"operation": str, "target": {{"type": "plan"|"task", "id": str, "title": str}}, "changes": {{}}, "reason": str}}

当前计划清单（来自用户账户，只读参考）：
{current_plans}

用户原话：{user_input}

如果用户其实是想**新建**一个从未有过的计划，请不要进入此模板，返回 {{"operation": "none"}}。请生成 JSON："""


@dataclass
class PlannerInput:
    """Input to PlannerAgent.run."""

    user_input: str
    prior_context: str  # 上一轮的累积上下文（多轮累积）
    trace_id: str
    user_id: str
    conversation_id: str
    source_refs: list[dict[str, Any]] | None = None  # RAG 检索的相关日记/记忆
    current_plans_text: str = ""  # 只读的当前计划/任务清单文本（V3.2 modify 用）


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
        - complete (has what) AND user refers to an existing plan/task:
          plan_modify PROTOCOL_BLOCK (adjust/archive/clean)
        - complete (has what) and building new: plan_proposal PROTOCOL_BLOCK
        Always publishes REPLY_START and REPLY_END.
        """
        await publish_reply_start(inp.trace_id, intent="plan_exploration")

        # Defense: crisis short-circuit
        if self._crisis.detect(inp.user_input) or self._crisis.detect(inp.prior_context):
            await publish_text_delta(inp.trace_id, self._crisis.safe_response)
            await publish_reply_end(inp.trace_id)
            return

        # V3.2: 只有提供了"当前计划清单"且用户话语指向修改既有计划时才走 modify 分支。
        # 否则退回新建提案流程（保持向后兼容）。
        if inp.current_plans_text.strip() and _looks_like_modify(inp.user_input):
            await self._emit_plan_modify(inp)
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
        # P3: 先流式发过渡语，降低用户等待感
        transition = self._build_transition_text(completeness)
        if transition:
            await publish_text_delta(inp.trace_id, transition)
            await publish_text_end(inp.trace_id)

        # 然后调 ainvoke 生成 JSON（协议块原子性，保持一次性渲染）
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

    async def _emit_plan_modify(self, inp: PlannerInput) -> None:
        """Generate an existing-plan modification proposal (V3.2).

        Prompts the LLM for a ``plan_modify`` JSON (operation / target /
        changes / reason), validates the target is within the supplied
        ``current_plans_text`` (defensive), and publishes it as a
        ``plan_modify`` PROTOCOL_BLOCK with ``status=awaiting_confirmation``.
        The Agent never writes anything — the user confirms in the frontend,
        which calls the REST API.
        """
        prompt = _PLAN_MODIFY_PROMPT.format(
            current_plans=inp.current_plans_text[:2000],
            user_input=inp.user_input[:500],
        )

        try:
            response = await self._llm.ainvoke(prompt)
            raw = message_text(response).strip()
            cleaned = self._strip_code_fence(raw)
            data = json.loads(cleaned)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Plan modify LLM/parse failed: %s", exc)
            data = {}

        operation = data.get("operation")
        if not operation or operation == "none":
            # LLM 判断这不属于"修改既有计划" → 回退到常规对话/新建提案流程。
            completeness = assess_plan_completeness(inp.user_input, inp.prior_context)
            if completeness.is_complete:
                await self._emit_plan_proposal(inp, completeness)
            else:
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

        target = data.get("target") or {}
        # 防御：target 必须落在提供的清单里（防止幻觉出不存在的 id/title）。
        target_desc = f"{target.get('title', '')}".strip()
        if not target_desc or (target_desc and target_desc not in inp.current_plans_text):
            logger.warning(
                "Plan modify target not found in current plans; falling back. target=%s",
                target,
            )
            completeness = assess_plan_completeness(inp.user_input, inp.prior_context)
            if completeness.is_complete:
                await self._emit_plan_proposal(inp, completeness)
            else:
                await publish_text_delta(
                    inp.trace_id, "我没找到你说的那条计划，可以再说具体一点吗？"
                )
                await publish_reply_end(inp.trace_id)
            return

        modify_data = {
            "operation": operation,
            "target": {
                "type": target.get("type", "plan"),
                "id": target.get("id", ""),
                "title": target.get("title", ""),
            },
            "changes": data.get("changes", {}),
            "reason": data.get("reason", ""),
            "status": "awaiting_confirmation",
        }

        await publish_protocol_block(
            inp.trace_id,
            block_type="plan_modify",
            block_id=f"modify-{inp.trace_id}",
            data=modify_data,
        )
        await publish_reply_end(inp.trace_id)

    def _build_transition_text(self, completeness: Any) -> str:
        """Generate natural transition text to reduce perceived wait.

        Published as TEXT_DELTA *before* the (atomic) JSON ainvoke call so
        the user gets immediate feedback that the agent is working on a
        proposal, rather than staring at a blank buffer while the LLM
        latency accrues.
        """
        what = getattr(completeness, "what", None) or "你的目标"
        return f"基于你提到的「{what}」, 结合你的历史记录, 我整理了一个建议:\n\n"

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """Remove markdown ```json ... ``` fence if present."""
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            return "\n".join(lines).strip()
        return text
