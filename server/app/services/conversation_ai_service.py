"""AI-powered chat replies with pinned diary context and RAG retrieval."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.orm import Session

from app.infrastructure.task_queue import enqueue_task
from app.services import (
    card_service,
    conversation_service,
    diary_service,
    plan_service,
    user_skill_service,
)
from app.services.ai.conversation_loop import run_conversation_loop
from app.services.ai.input_preprocessor import InputPreprocessor
from app.services.ai.prompts import FALLBACK_FEEDBACK
from app.services.ai.session_context import get_or_create_session
from app.services.ai.tool_factory import ToolFn, build_tool_map, is_mcp_tool
from app.services.memory_gateway import MemoryGateway
from app.shared.crisis_guard import CrisisGuard, get_crisis_guard
from app.shared.emotion_estimator import get_emotion_estimator
from app.shared.errors import ValidationError
from app.shared.llm import LLMClient, message_text
from app.shared.middleware import (
    MiddlewareContext,
    MiddlewarePipeline,
    build_default_pipeline,
)
from app.shared.pipeline_trace import (
    STATUS_DISPATCHED,
    PipelineTrace,
    reset_trace,
    set_trace,
    trace_span,
)
from app.shared.trace_persistence import persist_trace, publish_trace_complete_sync

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

MAX_PINNED_DIARIES = 3
MAX_ATTACHED_CARDS = 3
MAX_ATTACHED_PLANS = 3
MAX_RETRIEVAL_RESULTS = 3
MAX_EPISODIC_RESULTS = 3


@dataclass(frozen=True, slots=True)
class ChatReplyResult:
    reply_text: str
    retrieved_diary_ids: list[int]
    retrieved_memory_ids: list[str]
    is_crisis: bool = False
    profile_style: str = ""
    token_info: dict[str, int] | None = None
    stop_reason: str = ""
    tool_calls_made: list[str] | None = None
    skill_result: dict[str, Any] | None = None


def _normalize_diary_ids(diary_ids: list[int]) -> list[int]:
    seen: set[int] = set()
    normalized: list[int] = []
    for diary_id in diary_ids:
        if diary_id in seen:
            continue
        seen.add(diary_id)
        normalized.append(diary_id)
    if len(normalized) > MAX_PINNED_DIARIES:
        raise ValidationError(f"最多引用 {MAX_PINNED_DIARIES} 篇日记")
    return normalized


def _normalize_str_ids(ids: list[str], *, limit: int, label: str) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in ids:
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    if len(normalized) > limit:
        raise ValidationError(f"最多附上 {limit} {label}")
    return normalized


def _format_attached_cards(db: Session, card_ids: list[str], *, user_id: str) -> str:
    """Render user-attached memory cards as a context block ("" when none)."""
    if not card_ids:
        return ""
    parts: list[str] = []
    for card_id in card_ids:
        try:
            card = card_service.get_card(db, card_id, user_id=user_id)
        except Exception as exc:
            logger.debug("Attached card %s lookup failed (skipped): %s", card_id, exc)
            continue
        date_str = card.created_at.date().isoformat() if card.created_at else "未知日期"
        summary = (card.event_summary or "").strip() or "（无摘要）"
        tags: list[str] = []
        if card.tags_json:
            try:
                parsed = json.loads(card.tags_json)
                if isinstance(parsed, list):
                    tags = [str(t) for t in parsed][:3]
            except (json.JSONDecodeError, TypeError):
                tags = []
        tags_str = f" · 标签：{'、'.join(tags)}" if tags else ""
        parts.append(f"[卡片 {card_id} · {date_str} · 情绪：{card.emotion}{tags_str}] {summary}")
    if not parts:
        return ""
    return "【用户附上的卡片】\n" + "\n".join(parts)


def _format_attached_plans(db: Session, plan_ids: list[str], *, user_id: str) -> str:
    """Render user-attached plans as a context block ("" when none)."""
    if not plan_ids:
        return ""
    parts: list[str] = []
    for plan_id in plan_ids:
        try:
            plan = plan_service.get_plan(db, plan_id=plan_id, user_id=user_id)
        except Exception as exc:
            logger.debug("Attached plan %s lookup failed (skipped): %s", plan_id, exc)
            continue
        lines = [f"[计划 {plan.id} · {plan.title}] 状态：{plan.status}"]
        if plan.motivation and plan.motivation.strip():
            lines.append(f"动机：{plan.motivation.strip()}")
        if plan.target_value is not None:
            unit = plan.target_unit or ""
            period = plan.target_period or ""
            period_str = f"/{period}" if period else ""
            lines.append(f"目标：{plan.target_value:g}{unit}{period_str}")
        tasks = list(plan.tasks)
        done = sum(1 for t in tasks if t.status == "done")
        lines.append(f"任务进度：{done}/{len(tasks)}")
        parts.append("\n".join(lines))
    if not parts:
        return ""
    return "【用户附上的计划】\n" + "\n\n".join(parts)


def _compose_pinned_context(
    db: Session,
    pinned_ids: list[int],
    *,
    card_ids: list[str],
    plan_ids: list[str],
    user_id: str,
) -> str:
    """Pinned diaries plus user-attached cards/plans, joined into one block."""
    pinned_text = _format_retrieved_diaries(db, pinned_ids, user_id=user_id)
    attached_blocks = [
        block
        for block in (
            _format_attached_cards(db, card_ids, user_id=user_id),
            _format_attached_plans(db, plan_ids, user_id=user_id),
        )
        if block
    ]
    if not attached_blocks:
        return pinned_text
    return pinned_text + "\n\n" + "\n\n".join(attached_blocks)


def _retrieve_related_diary_ids(
    container: ServiceContainer,
    query: str,
    *,
    exclude_ids: set[int],
) -> list[int]:
    if not query.strip() or container.retriever is None:
        return []
    try:
        results = container.retriever.retrieve(
            query, top_k=MAX_RETRIEVAL_RESULTS + len(exclude_ids)
        )
    except Exception as exc:
        logger.warning("Chat RAG retrieve failed: %s", exc)
        return []

    diary_ids: list[int] = []
    for result in results:
        try:
            diary_id = int(result.diary_id)
        except (TypeError, ValueError):
            continue
        if diary_id in exclude_ids or diary_id in diary_ids:
            continue
        diary_ids.append(diary_id)
        if len(diary_ids) >= MAX_RETRIEVAL_RESULTS:
            break
    return diary_ids


def _day_digest_block(db: Session, entry: Any, user_id: str) -> str:
    """Render a diary's day-digest for scene-2 context ("" when no digest).

    V3 tree-hole: scene 2 prefers the structured day digest (emotion /
    topics / summary / temporal refs) over the raw diary excerpt so it can
    understand a referenced day without reading the full content.
    """
    from app.services.digest_service import format_day_digest

    day = None
    if getattr(entry, "date", None) is not None:
        day = entry.date
    elif getattr(entry, "created_at", None) is not None:
        day = entry.created_at.date()
    if day is None:
        return ""
    return format_day_digest(db, user_id=user_id, day=day)


def _format_retrieved_diaries(db: Session, diary_ids: list[int], *, user_id: str) -> str:
    if not diary_ids:
        return "（无）"
    entries = diary_service.get_entries_by_ids(db, diary_ids, user_id=user_id)
    if not entries:
        return "（无）"

    parts: list[str] = []
    for entry in entries:
        date_str = entry.date.isoformat() if entry.date else "未知"
        digest_block = _day_digest_block(db, entry, user_id)
        if digest_block:
            parts.append(f"[日记 #{entry.id} · {date_str}]\n{digest_block}")
        else:
            # Pre-digest data: fall back to the full-text excerpt.
            parts.append(diary_service.format_diary_excerpt(entry))
    return "\n\n".join(parts)


def _format_episodic_memories(container: ServiceContainer, query: str) -> tuple[str, list[str]]:
    """Format episodic memories for context, organized by source type.

    Three-source ordered display (P2-5):
    1. Diary-derived memories (source="diary")
    2. Night talk memories (source="chat") — relationship/resonance signals
    3. Card-derived memories (source="card") — structured emotional events

    Each source is displayed in a separate section with a header.
    """
    if container.episodic_memory is None:
        return "（无）", []
    try:
        entries = container.episodic_memory.retrieve_relevant(query, top_k=MAX_EPISODIC_RESULTS)
    except Exception as exc:
        logger.warning("Chat episodic retrieve failed: %s", exc)
        return "（无）", []

    if not entries:
        return "（无）", []

    # Categorize by source
    diary_entries = [e for e in entries if e.source == "diary"]
    chat_entries = [e for e in entries if e.source == "chat"]
    card_entries = [e for e in entries if e.source not in ("diary", "chat")]

    lines: list[str] = []
    memory_ids: list[str] = []

    def _format_section(title: str, items: list[Any]) -> None:
        if not items:
            return
        lines.append(f"【{title}】")
        for entry in items:
            memory_ids.append(entry.entry_id or "")
            emotion = entry.emotion or "未知"
            event = (entry.event_summary or "").strip()
            tags_str = f" [{', '.join(entry.tags)}]" if entry.tags else ""
            lines.append(f"- [{emotion}] {event}{tags_str}")

    # Ordered: diary → night talk → card
    _format_section("相关日记记忆", diary_entries)
    _format_section("夜话共鸣", chat_entries)
    _format_section("情绪卡片", card_entries)

    if not lines:
        return "（无）", []
    return "\n".join(lines), [mid for mid in memory_ids if mid]


def _try_user_skill(
    db: Session,
    container: ServiceContainer,
    *,
    conversation_id: str,
    content: str,
    user_id: str,
    forced_skill: str | None = None,
) -> Any:
    """Run the 记录/洞悉/计划 skill router; ``None`` → continue as chat.

    *forced_skill* (user manual selection) skips intent classification.
    """
    try:
        with trace_span(
            "S4a_user_skill", "用户技能路由", input_snapshot={"raw_text": content[:60]}
        ) as span:
            outcome = user_skill_service.run_user_skill(
                db,
                container,
                conversation_id=conversation_id,
                content=content,
                user_id=user_id,
                skill=forced_skill,
            )
            if span:
                span.metadata["skill"] = outcome.skill if outcome else "chat"
            return outcome
    except Exception as exc:
        logger.warning("User skill routing failed (continuing as chat): %s", exc)
        return None


def _build_tools(
    container: ServiceContainer, *, user_id: str = "default"
) -> dict[str, ToolFn] | None:
    """Build the tool map for the Agentic Loop, or None if unavailable."""
    try:
        # __dict__.get avoids auto-creating attributes on MagicMock containers
        # (same pattern as conversation_loop's graph lookup).
        registry = (
            container.__dict__.get("tool_registry")
            if hasattr(container, "__dict__")
            else None
        )
        if registry is not None:
            return cast(
                "dict[str, ToolFn] | None", registry.build_tool_map(user_id=user_id)
            )
        llm = container._llm_for_tier("light", agent_name="tool")
        if llm is None or container.retriever is None:
            return None
        return build_tool_map(
            container.session_factory, retriever=container.retriever, llm=llm, user_id=user_id
        )
    except Exception as exc:
        logger.warning("Tool map build failed: %s", exc)
        return None


def _filter_tools(
    all_tools: dict[str, ToolFn] | None,
    need_tools: list[str],
) -> dict[str, ToolFn] | None:
    """Intent-gated local tools + always-available MCP tools."""
    if not all_tools:
        return None
    if need_tools:
        selected = {
            name: fn
            for name, fn in all_tools.items()
            if name in need_tools or is_mcp_tool(name)
        }
    else:
        selected = {name: fn for name, fn in all_tools.items() if is_mcp_tool(name)}
    return selected or None


@dataclass
class ReplyContext:
    """Stage 1-3 output shared by streaming and non-streaming paths.

    Produced by :func:`_prepare_reply_context` (streaming path only).
    The non-streaming :func:`generate_reply` keeps its own inline copy of
    Stage 1-3 (approach B — minimize regression risk).
    """

    conversation_id: str
    content: str
    intent_result: Any  # ChatIntentResult | None
    pinned_diaries_text: str
    retrieved_diaries_text: str
    retrieved_diary_ids: list[int]
    episodic_text: str
    memory_ids: list[str]
    tools: Any  # dict[str, ToolFn] | None
    crisis_guard: Any  # CrisisGuard | None
    is_crisis: bool
    safe_response: str | None
    trace_id: str
    skill_outcome: Any = None  # SkillRunOutcome | None


def _prepare_reply_context(
    db: Session,
    container: ServiceContainer,
    *,
    conversation_id: str,
    content: str,
    diary_ids: list[int],
    user_id: str,
    auto_retrieve: bool,
    crisis_guard: CrisisGuard | None,
    trace_id: str | None,
    card_ids: list[str] | None = None,
    plan_ids: list[str] | None = None,
    forced_skill: str | None = None,
) -> ReplyContext:
    """Extract Stage 1-3 from generate_reply for streaming path reuse.

    Approach B: generate_reply (non-streaming) stays unchanged.
    This function is only called by generate_reply_streaming.

    The Stage 2.1-3 code below is copied verbatim from generate_reply
    (lines 206-423). ``trace_span`` calls are no-ops when no PipelineTrace
    is active (the streaming path does not set one).
    """
    pinned_ids = _normalize_diary_ids(diary_ids)
    attached_cards = _normalize_str_ids(
        card_ids or [], limit=MAX_ATTACHED_CARDS, label="张卡片"
    )
    attached_plans = _normalize_str_ids(
        plan_ids or [], limit=MAX_ATTACHED_PLANS, label="个计划"
    )
    container.ensure_ai_stack(user_id=user_id)

    # ── Stage 2: Crisis guard (P0 safety) ──
    guard = crisis_guard or get_crisis_guard()
    with trace_span("S2_crisis", "危机检测", input_snapshot={"raw_text": content}) as span:
        is_crisis = guard.detect(content)
        if span:
            span.metadata["is_crisis"] = is_crisis
    if is_crisis:
        logger.warning(
            "Crisis detected in conversation=%s, returning safety resources",
            conversation_id,
        )
        return ReplyContext(
            conversation_id=conversation_id,
            content=content,
            intent_result=None,
            pinned_diaries_text="",
            retrieved_diaries_text="",
            retrieved_diary_ids=pinned_ids,
            episodic_text="",
            memory_ids=[],
            tools=None,
            crisis_guard=guard,
            is_crisis=True,
            safe_response=guard.safe_response,
            trace_id=trace_id or "",
        )

    # ── Validate pinned diaries ──
    pinned_entries = diary_service.get_entries_by_ids(db, pinned_ids, user_id=user_id)
    if len(pinned_entries) != len(pinned_ids):
        raise ValidationError("引用的日记不存在或已被删除")

    # ── Stage 2.1: Session routing + Input preprocessing ──
    with trace_span(
        "S1_session", "会话路由", input_snapshot={"conversation_id": conversation_id}
    ) as span:
        session_ctx = get_or_create_session(conversation_id, container=container, user_id=user_id)
        brief_context = (
            session_ctx.compressed_history[:300] if session_ctx.compressed_history else ""
        )

    with trace_span("S3_preprocess", "输入预处理", input_snapshot={"raw_text": content}) as span:
        preprocessor = InputPreprocessor()
        preprocess_result = preprocessor.process(content, context=brief_context)
        content = preprocess_result.clean_text  # Use cleaned text for all downstream
        if span:
            span.metadata["safety_flag"] = preprocess_result.security_flags.has_injection
            span.metadata["omission_flag"] = preprocess_result.negation_detected

    if preprocess_result.security_flags.has_injection:
        logger.warning(
            "input.injection_detected conversation=%s patterns=%s",
            conversation_id,
            preprocess_result.security_flags.injection_patterns,
        )
    if preprocess_result.negation_detected:
        logger.info("input.negation_detected conversation=%s", conversation_id)

    # ── Stage 2.4: User skill routing (record / insight / plan) ──
    skill_outcome = _try_user_skill(
        db,
        container,
        conversation_id=conversation_id,
        content=content,
        user_id=user_id,
        forced_skill=forced_skill,
    )
    if skill_outcome is not None:
        return ReplyContext(
            conversation_id=conversation_id,
            content=content,
            intent_result=None,
            pinned_diaries_text="",
            retrieved_diaries_text="",
            retrieved_diary_ids=pinned_ids,
            episodic_text="",
            memory_ids=[],
            tools=None,
            crisis_guard=guard,
            is_crisis=False,
            safe_response=None,
            trace_id=trace_id or "",
            skill_outcome=skill_outcome,
        )

    # ── Stage 2.5: Chat intent classification (drives routing) ──
    with trace_span("S4_intent", "意图分类", input_snapshot={"raw_text": content}) as span:
        intent_classifier = container.get_chat_intent_classifier(user_id=user_id)
        intent_result = intent_classifier.classify_sync(content, context=brief_context)
        if span:
            span.metadata["intent_category"] = intent_result.intent_category
            span.metadata["tier"] = intent_result.tier

    # Crisis signal from intent classifier as a secondary safety net
    if intent_result.intent_category == "crisis_signal" and not guard.detect(content):
        logger.warning(
            "Intent classifier detected crisis missed by guard: conversation=%s",
            conversation_id,
        )
        return ReplyContext(
            conversation_id=conversation_id,
            content=content,
            intent_result=intent_result,
            pinned_diaries_text="",
            retrieved_diaries_text="",
            retrieved_diary_ids=pinned_ids,
            episodic_text="",
            memory_ids=[],
            tools=None,
            crisis_guard=guard,
            is_crisis=True,
            safe_response=guard.safe_response,
            trace_id=trace_id or "",
        )

    logger.info(
        "chat.intent conversation=%s category=%s tier=%s tools=%s retrieval=%s entity=%s",
        conversation_id,
        intent_result.intent_category,
        intent_result.tier,
        intent_result.need_tools,
        intent_result.need_retrieval,
        intent_result.need_entity_query,
    )

    # ── Stage 2.5b: Slot extraction (task decomposition) ──
    from app.domain.agents.slot_extractor import SlotExtractor

    with trace_span("S5_slot", "槽位抽取", input_snapshot={"raw_text": content}) as span:
        slot_extractor = SlotExtractor()
        slot_result = slot_extractor.extract(content, intent=intent_result.intent_category)
        if span:
            span.metadata["is_multi_task"] = slot_result.is_multi_task

    if slot_result.is_multi_task:
        logger.info(
            "chat.multi_task conversation=%s sub_tasks=%d",
            conversation_id,
            len(slot_result.sub_tasks),
        )
    if slot_result.style_constraints:
        logger.info(
            "chat.style_constraints conversation=%s constraints=%s",
            conversation_id,
            slot_result.style_constraints,
        )

    # ── Stage 2.6: Skill selection (scene-2 SkillRegistry) ──
    skill_registry = container.get_chat_skill_registry()
    from app.domain.skills.types import SkillProfileContext as _SkillProfile

    skill_profile: _SkillProfile = {
        "intent": intent_result.intent_category,
        "user_id": user_id,
        "recurring_topics": session_ctx.profile_topics,
    }
    with trace_span(
        "S6_skills", "技能选择", input_snapshot={"intent": intent_result.intent_category}
    ) as span:
        selected_skills = skill_registry.select_skills(
            content,
            skill_profile,
            token_budget=4000,
            decision_id=conversation_id,
        )
        if span:
            span.metadata["selected_count"] = len(selected_skills)

    # Execute analysis skills (crisis_detector, sentiment_skill) and append
    # their output to context if they produce text
    skill_outputs: list[str] = []
    for skill in selected_skills:
        if skill.metadata.category.value == "analysis":
            try:
                skill_ctx = {
                    "diary_content": content,
                    "user_id": user_id,
                    "intent": intent_result.intent_category,
                }
                output = skill.execute(skill_ctx)
                if output and not output.startswith("["):
                    skill_outputs.append(f"【{skill.metadata.name}】{output}")
            except Exception as exc:
                logger.debug("Skill %s execute failed (best-effort): %s", skill.metadata.name, exc)

    skill_context_text = "\n".join(skill_outputs) if skill_outputs else ""

    # ── Stage 3: Context assembly (intent-driven) ──
    exclude_ids = set(pinned_ids)
    retrieved_ids: list[int] = []

    retrieval_query = content
    # Query understanding + RAG only when intent needs retrieval
    if auto_retrieve and intent_result.need_retrieval:
        from app.domain.agents.query_understander import QueryUnderstander

        query_llm = container._llm_for_tier("light", agent_name="query_understander")
        understander = QueryUnderstander(
            llm=query_llm,
            tracer=container.llm_tracer,
            model=getattr(query_llm, "model", "") if query_llm else "",
        )
        with trace_span(
            "S7a_query_rewrite", "查询改写", input_snapshot={"raw_text": content}
        ) as span:
            understanding = understander.understand(content, context=brief_context)
            retrieval_query = understanding.rewritten
        logger.debug(
            "query.understood original=%s rewritten=%s terms=%s confidence=%.2f",
            content[:50],
            understanding.rewritten[:50],
            understanding.key_terms,
            understanding.confidence,
        )

        with trace_span("S7b_rag", "RAG检索", input_snapshot={"query": retrieval_query}) as span:
            retrieved_ids = _retrieve_related_diary_ids(
                container, retrieval_query, exclude_ids=exclude_ids
            )
            if span:
                span.metadata["retrieved_count"] = len(retrieved_ids)
    elif auto_retrieve:
        # No retrieval needed — still run query understanding for episodic search
        logger.debug(
            "Intent skips diary RAG, using raw content for episodic: %s",
            intent_result.intent_category,
        )

    all_context_ids = pinned_ids + [did for did in retrieved_ids if did not in pinned_ids]

    with trace_span("S7c_episodic", "情景记忆", input_snapshot={"query": retrieval_query}) as span:
        episodic_text, memory_ids = _format_episodic_memories(container, retrieval_query)
        if span:
            span.metadata["memory_count"] = len(memory_ids)
    if skill_context_text:
        episodic_text = f"{episodic_text}\n\n## 技能分析\n{skill_context_text}"
    pinned_text = _compose_pinned_context(
        db,
        pinned_ids,
        card_ids=attached_cards,
        plan_ids=attached_plans,
        user_id=user_id,
    )
    retrieved_text = _format_retrieved_diaries(db, retrieved_ids, user_id=user_id)

    # ── Build tools (intent-filtered subset) ──
    with trace_span("S7d_tools", "工具构建") as span:
        all_tools = _build_tools(container, user_id=user_id)
        if span:
            span.metadata["tool_count"] = len(all_tools) if all_tools else 0
    tools: dict[str, ToolFn] | None = _filter_tools(all_tools, intent_result.need_tools)

    # Release the DB connection before the long-running streaming loop.
    # The session re-acquires a connection when downstream code next
    # queries the DB.
    db.commit()

    return ReplyContext(
        conversation_id=conversation_id,
        content=content,
        intent_result=intent_result,
        pinned_diaries_text=pinned_text,
        retrieved_diaries_text=retrieved_text,
        retrieved_diary_ids=all_context_ids,
        episodic_text=episodic_text,
        memory_ids=memory_ids,
        tools=tools,
        crisis_guard=guard,
        is_crisis=False,
        safe_response=None,
        trace_id=trace_id or "",
    )


def generate_reply(
    db: Session,
    container: ServiceContainer,
    *,
    conversation_id: str,
    content: str,
    diary_ids: list[int],
    user_id: str,
    auto_retrieve: bool = True,
    crisis_guard: CrisisGuard | None = None,
    use_graph: bool = True,
    trace_id: str | None = None,
    card_ids: list[str] | None = None,
    plan_ids: list[str] | None = None,
    forced_skill: str | None = None,
) -> ChatReplyResult:
    """Build chat context and generate an assistant reply via the Agentic Loop.

    Flow (5-stage framework):
    1. Session routing: SessionContext maintains history/usage/profile across turns
    2. Input processing: normalize, crisis detection
    3. Context assembly: pinned diaries + RAG retrieval + episodic + profile
    4. Agentic Loop: model call → tool check → execute → backfill → repeat
    5. Output: reply + token_info + stop_reason + episodic write-back

    When *trace_id* is provided (developer mode), a :class:`PipelineTrace` is
    created and set in the context so that nested ``trace_span`` calls record
    their stages.  The trace is finalized, persisted, and published in the
    ``finally`` block — all best-effort.
    """
    trace: PipelineTrace | None = None
    token = None
    if trace_id:
        trace = PipelineTrace(trace_id=trace_id, scenario="chat_reply", user_id=user_id)
        token = set_trace(trace)
    try:
        pinned_ids = _normalize_diary_ids(diary_ids)
        attached_cards = _normalize_str_ids(
            card_ids or [], limit=MAX_ATTACHED_CARDS, label="张卡片"
        )
        attached_plans = _normalize_str_ids(
            plan_ids or [], limit=MAX_ATTACHED_PLANS, label="个计划"
        )
        container.ensure_ai_stack(user_id=user_id)

        # ── Stage 2: Crisis guard (P0 safety) ──
        guard = crisis_guard or get_crisis_guard()
        with trace_span("S2_crisis", "危机检测", input_snapshot={"raw_text": content}) as span:
            is_crisis = guard.detect(content)
            if span:
                span.metadata["is_crisis"] = is_crisis
        if is_crisis:
            logger.warning(
                "Crisis detected in conversation=%s, returning safety resources",
                conversation_id,
            )
            crisis_result = ChatReplyResult(
                reply_text=guard.safe_response,
                retrieved_diary_ids=pinned_ids,
                retrieved_memory_ids=[],
                is_crisis=True,
            )
            if trace is not None:
                trace.end()
            return crisis_result

        # ── Validate pinned diaries ──
        pinned_entries = diary_service.get_entries_by_ids(db, pinned_ids, user_id=user_id)
        if len(pinned_entries) != len(pinned_ids):
            raise ValidationError("引用的日记不存在或已被删除")

        # ── Stage 2.1: Session routing + Input preprocessing ──
        with trace_span(
            "S1_session", "会话路由", input_snapshot={"conversation_id": conversation_id}
        ) as span:
            session_ctx = get_or_create_session(
                conversation_id, container=container, user_id=user_id
            )
            brief_context = (
                session_ctx.compressed_history[:300] if session_ctx.compressed_history else ""
            )

        with trace_span(
            "S3_preprocess", "输入预处理", input_snapshot={"raw_text": content}
        ) as span:
            preprocessor = InputPreprocessor()
            preprocess_result = preprocessor.process(content, context=brief_context)
            content = preprocess_result.clean_text  # Use cleaned text for all downstream
            if span:
                span.metadata["safety_flag"] = preprocess_result.security_flags.has_injection
                span.metadata["omission_flag"] = preprocess_result.negation_detected

        if preprocess_result.security_flags.has_injection:
            logger.warning(
                "input.injection_detected conversation=%s patterns=%s",
                conversation_id,
                preprocess_result.security_flags.injection_patterns,
            )
        if preprocess_result.negation_detected:
            logger.info("input.negation_detected conversation=%s", conversation_id)

        # ── Stage 2.4: User skill routing (record / insight / plan) ──
        skill_outcome = _try_user_skill(
            db,
            container,
            conversation_id=conversation_id,
            content=content,
            user_id=user_id,
            forced_skill=forced_skill,
        )
        if skill_outcome is not None:
            skill_reply = ChatReplyResult(
                reply_text=skill_outcome.reply_text,
                retrieved_diary_ids=[],
                retrieved_memory_ids=[],
                token_info=skill_outcome.token_info,
                stop_reason="user_skill",
                skill_result=skill_outcome.skill_result,
            )
            if trace is not None:
                trace.end()
            return skill_reply

        # ── Stage 2.5: Chat intent classification (drives routing) ──
        with trace_span("S4_intent", "意图分类", input_snapshot={"raw_text": content}) as span:
            intent_classifier = container.get_chat_intent_classifier(user_id=user_id)
            intent_result = intent_classifier.classify_sync(content, context=brief_context)
            if span:
                span.metadata["intent_category"] = intent_result.intent_category
                span.metadata["tier"] = intent_result.tier

        # Crisis signal from intent classifier as a secondary safety net
        if intent_result.intent_category == "crisis_signal" and not guard.detect(content):
            logger.warning(
                "Intent classifier detected crisis missed by guard: conversation=%s",
                conversation_id,
            )
            crisis_result = ChatReplyResult(
                reply_text=guard.safe_response,
                retrieved_diary_ids=pinned_ids,
                retrieved_memory_ids=[],
                is_crisis=True,
            )
            if trace is not None:
                trace.end()
            return crisis_result

        logger.info(
            "chat.intent conversation=%s category=%s tier=%s tools=%s retrieval=%s entity=%s",
            conversation_id,
            intent_result.intent_category,
            intent_result.tier,
            intent_result.need_tools,
            intent_result.need_retrieval,
            intent_result.need_entity_query,
        )

        # ── Stage 2.5b: Slot extraction (task decomposition) ──
        from app.domain.agents.slot_extractor import SlotExtractor

        with trace_span("S5_slot", "槽位抽取", input_snapshot={"raw_text": content}) as span:
            slot_extractor = SlotExtractor()
            slot_result = slot_extractor.extract(content, intent=intent_result.intent_category)
            if span:
                span.metadata["is_multi_task"] = slot_result.is_multi_task

        if slot_result.is_multi_task:
            logger.info(
                "chat.multi_task conversation=%s sub_tasks=%d",
                conversation_id,
                len(slot_result.sub_tasks),
            )
        if slot_result.style_constraints:
            logger.info(
                "chat.style_constraints conversation=%s constraints=%s",
                conversation_id,
                slot_result.style_constraints,
            )

        # ── Stage 2.6: Skill selection (scene-2 SkillRegistry) ──
        skill_registry = container.get_chat_skill_registry()
        from app.domain.skills.types import SkillProfileContext as _SkillProfile

        skill_profile: _SkillProfile = {
            "intent": intent_result.intent_category,
            "user_id": user_id,
            "recurring_topics": session_ctx.profile_topics,
        }
        with trace_span(
            "S6_skills", "技能选择", input_snapshot={"intent": intent_result.intent_category}
        ) as span:
            selected_skills = skill_registry.select_skills(
                content,
                skill_profile,
                token_budget=4000,
                decision_id=conversation_id,
            )
            if span:
                span.metadata["selected_count"] = len(selected_skills)

        # Execute analysis skills (crisis_detector, sentiment_skill) and append
        # their output to context if they produce text
        skill_outputs: list[str] = []
        for skill in selected_skills:
            if skill.metadata.category.value == "analysis":
                try:
                    skill_ctx = {
                        "diary_content": content,
                        "user_id": user_id,
                        "intent": intent_result.intent_category,
                    }
                    output = skill.execute(skill_ctx)
                    if output and not output.startswith("["):
                        skill_outputs.append(f"【{skill.metadata.name}】{output}")
                except Exception as exc:
                    logger.debug(
                        "Skill %s execute failed (best-effort): %s", skill.metadata.name, exc
                    )

        skill_context_text = "\n".join(skill_outputs) if skill_outputs else ""

        # ── Stage 3: Context assembly (intent-driven) ──
        exclude_ids = set(pinned_ids)
        retrieved_ids: list[int] = []

        retrieval_query = content
        # Query understanding + RAG only when intent needs retrieval
        if auto_retrieve and intent_result.need_retrieval:
            from app.domain.agents.query_understander import QueryUnderstander

            query_llm = container._llm_for_tier("light", agent_name="query_understander")
            understander = QueryUnderstander(
                llm=query_llm,
                tracer=container.llm_tracer,
                model=getattr(query_llm, "model", "") if query_llm else "",
            )
            with trace_span(
                "S7a_query_rewrite", "查询改写", input_snapshot={"raw_text": content}
            ) as span:
                understanding = understander.understand(content, context=brief_context)
                retrieval_query = understanding.rewritten
            logger.debug(
                "query.understood original=%s rewritten=%s terms=%s confidence=%.2f",
                content[:50],
                understanding.rewritten[:50],
                understanding.key_terms,
                understanding.confidence,
            )

            with trace_span(
                "S7b_rag", "RAG检索", input_snapshot={"query": retrieval_query}
            ) as span:
                retrieved_ids = _retrieve_related_diary_ids(
                    container, retrieval_query, exclude_ids=exclude_ids
                )
                if span:
                    span.metadata["retrieved_count"] = len(retrieved_ids)
        elif auto_retrieve:
            # No retrieval needed — still run query understanding for episodic search
            logger.debug(
                "Intent skips diary RAG, using raw content for episodic: %s",
                intent_result.intent_category,
            )

        all_context_ids = pinned_ids + [did for did in retrieved_ids if did not in pinned_ids]

        with trace_span(
            "S7c_episodic", "情景记忆", input_snapshot={"query": retrieval_query}
        ) as span:
            episodic_text, memory_ids = _format_episodic_memories(container, retrieval_query)
            if span:
                span.metadata["memory_count"] = len(memory_ids)
        if skill_context_text:
            episodic_text = f"{episodic_text}\n\n## 技能分析\n{skill_context_text}"
        pinned_text = _compose_pinned_context(
            db,
            pinned_ids,
            card_ids=attached_cards,
            plan_ids=attached_plans,
            user_id=user_id,
        )
        retrieved_text = _format_retrieved_diaries(db, retrieved_ids, user_id=user_id)

        # ── Build tools (intent-filtered subset) ──
        with trace_span("S7d_tools", "工具构建") as span:
            all_tools = _build_tools(container, user_id=user_id)
            if span:
                span.metadata["tool_count"] = len(all_tools) if all_tools else 0
        tools: dict[str, ToolFn] | None = _filter_tools(all_tools, intent_result.need_tools)

        # Release the DB connection before the long-running Agentic Loop
        # (LLM network calls). The session re-acquires a connection when
        # run_conversation_loop / downstream code next queries the DB.
        db.commit()

        # ── Stage 4: Agentic Loop ──
        with trace_span("S8_loop", "Agentic Loop", input_snapshot={"content": content}) as span:
            loop_result = run_conversation_loop(
                db,
                container,
                conversation_id=conversation_id,
                content=content,
                pinned_diaries_text=pinned_text,
                retrieved_diaries_text=retrieved_text,
                episodic_text=episodic_text,
                memory_ids=memory_ids,
                tools=tools,
                crisis_guard=guard,
                user_id=user_id,
                intent_result=intent_result,
                use_graph=use_graph,
            )
            if span:
                span.metadata["stop_reason"] = loop_result.stop_reason
                span.metadata["tool_calls"] = loop_result.tool_calls_made

        # ── Stage 5: Output + episodic write-back ──
        _memory_span = None
        with trace_span("S10_memory", "情景记忆写入") as _memory_span:
            _maybe_persist_episodic(
                container,
                content=content,
                reply_text=loop_result.reply_text,
                conversation_id=conversation_id,
                user_id=user_id,
            )
        # Write is dispatched fire-and-forget via enqueue_task; mark the span
        # dispatched so its short duration is read as scheduling, not full I/O.
        if _memory_span is not None:
            _memory_span.status = STATUS_DISPATCHED

        # Get profile style from session (cached, loaded once)
        session = get_or_create_session(conversation_id, container=container, user_id=user_id)

        logger.info(
            "Chat reply generated: conversation=%s tokens=%s tools=%s stop=%s",
            conversation_id,
            loop_result.token_info.get("total_tokens_used", 0),
            loop_result.tool_calls_made,
            loop_result.stop_reason,
        )

        # ── Entity extraction sidecar (P2-7) ──
        _entity_span = None
        with trace_span("S10b_entity", "实体提取") as _entity_span:
            try:
                from app.domain.agents.entity_extractor import schedule_entity_extraction

                schedule_entity_extraction(
                    container,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    text=content,
                )
            except Exception as exc:
                logger.debug("Entity extraction scheduling failed (best-effort): %s", exc)
        if _entity_span is not None:
            _entity_span.status = STATUS_DISPATCHED

        result = ChatReplyResult(
            reply_text=loop_result.reply_text,
            retrieved_diary_ids=all_context_ids,
            retrieved_memory_ids=memory_ids,
            profile_style=session.profile_style,
            token_info=loop_result.token_info,
            stop_reason=loop_result.stop_reason,
            tool_calls_made=loop_result.tool_calls_made,
        )
        if trace is not None:
            trace.end()
        return result
    except Exception:
        if trace is not None:
            trace.end(status="error")
        raise
    finally:
        if trace is not None:
            try:
                trace_db = container.session()
                try:
                    persist_trace(trace_db, trace, ref_id=conversation_id)
                finally:
                    trace_db.close()
            except Exception as exc:
                logger.warning("Trace persistence failed: %s", exc)
            with contextlib.suppress(Exception):
                publish_trace_complete_sync(trace)
            if token is not None:
                reset_trace(token)


# ── V3 P0: Streaming variants ────────────────────────────────────────


async def generate_reply_streaming(
    db: Session,
    container: ServiceContainer,
    *,
    conversation_id: str,
    content: str,
    diary_ids: list[int],
    user_id: str,
    auto_retrieve: bool = True,
    crisis_guard: CrisisGuard | None = None,
    trace_id: str = "",
    middleware_pipeline: MiddlewarePipeline | None = None,
    card_ids: list[str] | None = None,
    plan_ids: list[str] | None = None,
    forced_skill: str | None = None,
) -> None:
    """Real streaming (P3): _prepare_reply_context -> run_conversation_loop_streaming -> post-write.

    Replaces P0 simulated streaming. The try/finally guarantees a
    ``REPLY_END`` event is always published (P1 terminating_reply).

    V3 P7: *middleware_pipeline* (default: Safety + Finalize) is injected into
    ``run_conversation_loop_streaming`` for ``on_system_prompt`` hooks and run
    on reply completion for ``on_reply`` hooks (fire-and-forget episodic
    write-back, including the crisis audit trail). Pass an empty pipeline to
    opt out entirely.

    For the non-crisis path, ``run_conversation_loop_streaming`` publishes
    all SSE events (REPLY_START, TEXT_DELTA*, TEXT_END, REPLY_END)
    internally — this function does **not** duplicate them. It only
    publishes events for the crisis path and for error/cancel fallbacks.
    """
    from app.services.ai.conversation_loop import run_conversation_loop_streaming
    from app.shared.streaming_events import (
        publish_reply_end,
        publish_reply_start,
        publish_text_delta,
        publish_text_end,
    )

    pipeline = middleware_pipeline if middleware_pipeline is not None else build_default_pipeline()

    reply_started = False
    reply_end_sent = False
    final_reply_text = ""

    try:
        ctx = _prepare_reply_context(
            db,
            container,
            conversation_id=conversation_id,
            content=content,
            diary_ids=diary_ids,
            user_id=user_id,
            auto_retrieve=auto_retrieve,
            crisis_guard=crisis_guard,
            trace_id=trace_id or None,
            card_ids=card_ids,
            plan_ids=plan_ids,
            forced_skill=forced_skill,
        )

        # No trace_id → no SSE subscriber → nothing to publish.
        if not trace_id:
            return

        # ── Crisis path: publish safe template as a single chunk ──
        if ctx.is_crisis:
            await publish_reply_start(trace_id, intent="crisis_signal")
            reply_started = True
            await publish_text_delta(trace_id, ctx.safe_response or "")
            await publish_text_end(trace_id)
            await publish_reply_end(trace_id)
            reply_end_sent = True

            # V3 P7: crisis turns still run the Finalize hook — the severe
            # signal forces an audit write-back (same semantics as the sync
            # path, which persists on crisis via _maybe_persist_episodic).
            with contextlib.suppress(Exception):
                pipeline.run_on_reply(
                    MiddlewareContext(
                        scenario="conversation",
                        user_id=user_id,
                        content=content,
                        intent="crisis_signal",
                        trace_id=trace_id,
                        conversation_id=conversation_id,
                        reply_text=ctx.safe_response or "",
                        container=container,
                    )
                )
            return

        # ── User-skill path: publish the complete outcome as one chunk ──
        if ctx.skill_outcome is not None:
            outcome = ctx.skill_outcome
            await publish_reply_start(trace_id, intent=f"user_skill_{outcome.skill}")
            reply_started = True
            await publish_text_delta(trace_id, outcome.reply_text)
            await publish_text_end(trace_id)
            await publish_reply_end(trace_id)
            reply_end_sent = True

            # The streaming path has no other persister — save the turn here
            # so the frontend's post-reply refetch sees the skill result.
            with contextlib.suppress(Exception):
                conversation_service.add_user_message_and_reply(
                    db,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    content=content,
                    reply_content=outcome.reply_text,
                    skill_result=outcome.skill_result,
                    token_info=outcome.token_info,
                )
            with contextlib.suppress(Exception):
                pipeline.run_on_reply(
                    MiddlewareContext(
                        scenario="conversation",
                        user_id=user_id,
                        content=content,
                        intent="",
                        trace_id=trace_id,
                        conversation_id=conversation_id,
                        reply_text=outcome.reply_text,
                        container=container,
                    )
                )
            return

        # ── Non-crisis path: delegate to run_conversation_loop_streaming ──
        # The loop publishes REPLY_START, TEXT_DELTA*, TEXT_END, and
        # REPLY_END internally via the TraceEventBus. We set reply_started
        # optimistically (the loop publishes REPLY_START very early) so
        # that the cancel/error handlers know to send a fallback REPLY_END.
        reply_started = True

        async for item in run_conversation_loop_streaming(
            db=db,
            container=container,
            conversation_id=conversation_id,
            content=content,
            pinned_diaries_text=ctx.pinned_diaries_text,
            retrieved_diaries_text=ctx.retrieved_diaries_text,
            episodic_text=ctx.episodic_text,
            memory_ids=ctx.memory_ids,
            tools=ctx.tools,
            crisis_guard=ctx.crisis_guard,
            user_id=user_id,
            intent_result=ctx.intent_result,
            trace_id=trace_id,
            middleware_pipeline=pipeline,
        ):
            if isinstance(item, str):
                final_reply_text += item

        # The loop has already published REPLY_END on normal completion.
        reply_end_sent = True

        # ── Stage 5: post-write (best-effort, non-fatal) ──
        # V3 P7: FinalizeMiddleware.on_reply replaces the inline
        # _maybe_persist_episodic call with the unified write-back.
        with contextlib.suppress(Exception):
            pipeline.run_on_reply(
                MiddlewareContext(
                    scenario="conversation",
                    user_id=user_id,
                    content=content,
                    intent=(
                        ctx.intent_result.intent_category
                        if getattr(ctx, "intent_result", None) is not None
                        else ""
                    ),
                    trace_id=trace_id,
                    conversation_id=conversation_id,
                    reply_text=final_reply_text,
                    container=container,
                )
            )

    except asyncio.CancelledError:
        # User-initiated abort — clean shutdown, no fallback text needed.
        if reply_started and not reply_end_sent and trace_id:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="cancelled")
            reply_end_sent = True
        raise  # Propagate CancelledError to the task registry

    except Exception as exc:
        logger.exception("Streaming reply failed: %s", exc)
        if trace_id:
            if not reply_started:
                with contextlib.suppress(Exception):
                    await publish_reply_start(trace_id, intent="error")
                reply_started = True
            with contextlib.suppress(Exception):
                await publish_text_delta(trace_id, FALLBACK_FEEDBACK)
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error=str(exc))
            reply_end_sent = True

    finally:
        # Ultimate fallback: if an exception path itself failed before
        # publishing REPLY_END, ensure it happens here.
        if trace_id and reply_started and not reply_end_sent:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="finalized")


def _split_into_chunks(text: str, chunk_size: int = 20) -> list[str]:
    """Split *text* into sentence-like chunks for a streaming effect.

    Splits on Chinese/English sentence-ending punctuation first (keeping the
    punctuation), then further subdivides any resulting segment that is
    longer than *chunk_size* characters.

    Examples
    --------
    >>> _split_into_chunks("你好。世界！")
    ['你好。', '世界！']
    >>> _split_into_chunks("", 20)
    []
    """
    if not text:
        return []

    import re

    # Split *after* sentence-ending punctuation (Chinese 。！？ + newline +
    # English .!?). The lookbehind keeps the punctuation attached to the
    # preceding segment.
    sentences = re.split(r"(?<=[。！？\n.!?])", text)
    chunks: list[str] = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        while len(sent) > chunk_size:
            chunks.append(sent[:chunk_size])
            sent = sent[chunk_size:]
        if sent:
            chunks.append(sent)
    return chunks


#: Minimum emotion intensity (abs score) to trigger episodic write-back.
_EPISODIC_WRITE_THRESHOLD = 0.3


def _maybe_persist_episodic(
    container: ServiceContainer,
    *,
    content: str,
    reply_text: str,
    conversation_id: str = "",
    user_id: str = "default",
) -> None:
    """Persist an episodic entry when the turn carries strong emotion.

    Uses :class:`ContentNormalizer.from_conversation` to produce a
    ``UnifiedMemoryAtom`` and then schedules
    :meth:`MemoryGateway.persist_atom` via :func:`enqueue_task`
    (fire-and-forget) for the unified write path.

    Conditions (either triggers):
    - Emotion score abs value ≥ 0.3 (meaningful positive or negative shift).
    - Severe signal detected (crisis-level — always write for safety audit trail).

    The emotion gate runs synchronously (cheap), but the actual write is
    dispatched off the request thread. Best-effort: failures are logged and
    never propagate.
    """
    try:
        estimator = get_emotion_estimator()
        score = estimator.score(content)
        if abs(score) < _EPISODIC_WRITE_THRESHOLD and not estimator.has_severe_signal(content):
            return

        from app.services.normalizer import ContentNormalizer

        gw = MemoryGateway.from_container(container)
        emotion_label = estimator.estimate(content).label

        atom = ContentNormalizer.from_conversation(
            content,
            reply_text=reply_text,
            conversation_id=conversation_id,
            user_id=user_id,
            emotion_label=emotion_label,
            emotion_score=score,
        )

        # Fire-and-forget: persist_atom opens its own session via the episodic
        # store's session_factory (thread-safe), so dispatching it off the
        # request thread removes episodic store + DB persist + long-term
        # promotion from the reply tail latency.
        enqueue_task(gw.persist_atom, atom)
        logger.info(
            "Episodic write-back dispatched: event=%s emotion=%s score=%.2f",
            atom.event_summary[:20],
            emotion_label,
            score,
        )
    except Exception as exc:
        logger.warning("Episodic write-back failed (best-effort): %s", exc)


# ── Night Talk generation from conversation ─────────────────────────


NIGHT_TALK_DRAFT_PROMPT = """你是一个温和的生活记录助手。请从以下对话中提取「值得沉淀为夜话的片段」。

夜话是用户与夜记共同营造的长期陪伴式关系记忆，区别于事件卡片。抽取重心是：
- 情感共鸣信号（用户感到被理解的关键瞬间）
- 关系联结信号（用户对这段长期相伴的表达）
- 情绪转折点（从低落到平静、从焦虑到放松等）

剔除寒暄、重复、无信息量内容，只保留有情感共鸣价值或关系进展信号的片段。

对话内容：
{conversation_text}

请返回一个 JSON 对象，格式如下，不要包含其他内容：
{{"event_summary": "用一句话概括这段对话中的情感主题或关系信号（不超过30字）", "tags": ["标签1", "标签2"], "resonance_level": "high/medium/low"}}

要求：
- event_summary 应聚焦于情感共鸣或关系进展，而非具体事件
- tags 应包含 1-3 个情感/关系关键词
- resonance_level 表示这段对话的共鸣强度
- 用温暖、日常的中文
"""

NIGHT_TALK_REFINE_RULES: dict[str, Any] = {
    "min_event_summary_len": 5,
    "valid_emotions": {"积极", "低落", "平静", "焦虑", "感动", "释然"},
    "default_emotion": "平静",
}

NIGHT_TALK_FALLBACK = {"event_summary": "一段温暖的夜话", "tags": ["夜话"], "emotion": "平静"}

CARD_GEN_FALLBACK = {"event_summary": "对话摘要", "tags": ["对话"]}


def generate_card_from_conversation(
    db: Session,
    container: ServiceContainer,
    *,
    user_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Extract a memory-card draft from conversation history.

    Two-stage process:
    1. Draft: light LLM extracts resonance-worthy fragments from the conversation.
    2. Refine: rule-based validation (non-empty summary, valid emotion, etc.)
       before persisting to memory with source="chat".

    Returns a dict with event_summary, emotion, tags, and persisted flag.
    """
    from app.shared.emotion_estimator import EmotionEstimator

    messages = conversation_service.list_messages(
        db, user_id=user_id, conversation_id=conversation_id
    )
    if not messages:
        return {
            "emotion": "平静",
            "event_summary": "暂无对话内容",
            "tags": ["夜话"],
            "persisted": False,
        }

    # Build conversation text for LLM and emotion estimation
    conv_lines: list[str] = []
    for msg in messages:
        role = "用户" if msg.role == "user" else "夜记"
        conv_lines.append(f"{role}：{(msg.content or '').strip()}")
    conv_text = "\n".join(conv_lines)

    # Estimate emotion from user messages only (more accurate)
    user_text = " ".join((msg.content or "").strip() for msg in messages if msg.role == "user")
    estimator = EmotionEstimator()
    estimate = estimator.estimate(user_text)
    emotion_label = estimate.label if estimate.label != "crisis" else "negative"
    score = estimator.score(user_text)

    # Map score to emotion word
    emotion_word_map = {
        "positive": "积极",
        "negative": "低落",
        "neutral": "平静",
    }
    emotion = emotion_word_map.get(emotion_label, "平静")

    # ── Stage 1: Draft — LLM extracts resonance-worthy fragments ──
    container.ensure_ai_stack(user_id=user_id)
    llm: LLMClient | None = container._llm_for_tier("light", agent_name="generate-card")
    if llm is None:
        logger.warning("Night-talk LLM unavailable; returning emotion-only result")
        return {
            "emotion": emotion,
            "event_summary": conv_lines[0][:30] if conv_lines else "夜话",
            "tags": ["夜话"],
            "persisted": False,
        }

    prompt = NIGHT_TALK_DRAFT_PROMPT.format(conversation_text=conv_text[:2000])
    draft_result: dict[str, Any] = NIGHT_TALK_FALLBACK.copy()
    try:
        response = llm.invoke(prompt)
        text = message_text(response).strip()
        draft_result = _parse_card_json(text)
        draft_result.setdefault("emotion", emotion)
        logger.info(
            "Night-talk draft generated for conversation=%s emotion=%s", conversation_id, emotion
        )
    except Exception as exc:
        logger.warning("Night-talk LLM invoke failed: %s", exc)

    # ── Stage 2: Refine — rule-based validation before persisting ──
    event_summary = draft_result.get("event_summary", "").strip()
    if len(event_summary) < NIGHT_TALK_REFINE_RULES["min_event_summary_len"]:
        event_summary = NIGHT_TALK_FALLBACK["event_summary"]
        draft_result["event_summary"] = event_summary

    tags = draft_result.get("tags", ["夜话"])
    if not isinstance(tags, list) or not tags:
        tags = ["夜话"]

    # Validate emotion
    if emotion not in NIGHT_TALK_REFINE_RULES["valid_emotions"]:
        emotion = NIGHT_TALK_REFINE_RULES["default_emotion"]

    # ── Persist to memory via MemoryGateway (source="chat") ──
    persisted = False
    try:
        gw = MemoryGateway.from_container(container)
        importance = min(abs(score) + 0.3, 1.0) if abs(score) > 0.1 else 0.5
        persisted = gw.persist_episodic(
            event_summary=event_summary,
            emotion=emotion,
            reply_insight="",
            source="chat",
            importance=importance,
            user_id=user_id,
            tags=tags,
            mood_score=max(0.0, min(1.0, 0.5 + score * 0.5)),
        )
        if persisted:
            logger.info(
                "Night-talk persisted: conversation=%s emotion=%s tags=%s",
                conversation_id,
                emotion,
                tags,
            )
    except Exception as exc:
        logger.warning("Night-talk persist failed (best-effort): %s", exc)

    return {
        "emotion": emotion,
        "event_summary": event_summary,
        "tags": tags,
        "persisted": persisted,
    }


def _parse_card_json(text: str) -> dict[str, Any]:
    """Parse JSON card output from LLM, tolerating markdown fences."""
    import json
    import re

    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return {
                "event_summary": str(parsed.get("event_summary", ""))[:100] or "对话摘要",
                "tags": [str(t) for t in parsed.get("tags", ["对话"])][:3] or ["对话"],
            }
    except json.JSONDecodeError:
        pass

    # Fallback: extract event_summary from quotes
    matches = re.findall(r'"([^"]+)"', text)
    if matches:
        return {"event_summary": matches[0][:100], "tags": ["对话"]}

    return CARD_GEN_FALLBACK
