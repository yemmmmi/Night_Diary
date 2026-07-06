"""AI-powered chat replies with pinned diary context and RAG retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.services import conversation_service, diary_service
from app.services.ai.conversation_loop import run_conversation_loop
from app.services.ai.input_preprocessor import InputPreprocessor
from app.services.ai.session_context import get_or_create_session
from app.services.ai.tool_factory import ToolFn, build_tool_map
from app.services.memory_gateway import MemoryGateway
from app.shared.crisis_guard import CrisisGuard, get_crisis_guard
from app.shared.emotion_estimator import get_emotion_estimator
from app.shared.errors import ValidationError
from app.shared.llm import LLMClient, message_text

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

MAX_PINNED_DIARIES = 3
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


def _format_retrieved_diaries(db: Session, diary_ids: list[int], *, user_id: str) -> str:
    if not diary_ids:
        return "（无）"
    entries = diary_service.get_entries_by_ids(db, diary_ids, user_id=user_id)
    if not entries:
        return "（无）"
    return "\n\n".join(diary_service.format_diary_excerpt(entry) for entry in entries)


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


def _build_tools(
    db: Session, container: ServiceContainer, *, user_id: str = "default"
) -> dict[str, ToolFn] | None:
    """Build the tool map for the Agentic Loop, or None if unavailable."""
    try:
        llm = container._llm_for_tier(db, "light", agent_name="tool")
        if llm is None or container.retriever is None:
            return None
        return build_tool_map(db, retriever=container.retriever, llm=llm, user_id=user_id)
    except Exception as exc:
        logger.warning("Tool map build failed: %s", exc)
        return None


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
) -> ChatReplyResult:
    """Build chat context and generate an assistant reply via the Agentic Loop.

    Flow (5-stage framework):
    1. Session routing: SessionContext maintains history/usage/profile across turns
    2. Input processing: normalize, crisis detection
    3. Context assembly: pinned diaries + RAG retrieval + episodic + profile
    4. Agentic Loop: model call → tool check → execute → backfill → repeat
    5. Output: reply + token_info + stop_reason + episodic write-back
    """
    pinned_ids = _normalize_diary_ids(diary_ids)
    container.ensure_ai_stack(user_id=user_id)

    # ── Stage 2: Crisis guard (P0 safety) ──
    guard = crisis_guard or get_crisis_guard()
    if guard.detect(content):
        logger.warning(
            "Crisis detected in conversation=%s, returning safety resources", conversation_id
        )
        return ChatReplyResult(
            reply_text=guard.safe_response,
            retrieved_diary_ids=pinned_ids,
            retrieved_memory_ids=[],
            is_crisis=True,
        )

    # ── Validate pinned diaries ──
    pinned_entries = diary_service.get_entries_by_ids(db, pinned_ids, user_id=user_id)
    if len(pinned_entries) != len(pinned_ids):
        raise ValidationError("引用的日记不存在或已被删除")

    # ── Stage 2.1: Input preprocessing (text cleaning + security + omission) ──
    session_ctx = get_or_create_session(conversation_id, container=container, user_id=user_id)
    brief_context = session_ctx.compressed_history[:300] if session_ctx.compressed_history else ""

    preprocessor = InputPreprocessor()
    preprocess_result = preprocessor.process(content, context=brief_context)
    content = preprocess_result.clean_text  # Use cleaned text for all downstream

    if preprocess_result.security_flags.has_injection:
        logger.warning(
            "input.injection_detected conversation=%s patterns=%s",
            conversation_id,
            preprocess_result.security_flags.injection_patterns,
        )
    if preprocess_result.negation_detected:
        logger.info("input.negation_detected conversation=%s", conversation_id)

    # ── Stage 2.5: Chat intent classification (drives routing) ──
    intent_classifier = container.get_chat_intent_classifier(db, user_id=user_id)
    intent_result = intent_classifier.classify_sync(content, context=brief_context)

    # Crisis signal from intent classifier as a secondary safety net
    if intent_result.intent_category == "crisis_signal" and not guard.detect(content):
        logger.warning(
            "Intent classifier detected crisis missed by guard: conversation=%s",
            conversation_id,
        )
        return ChatReplyResult(
            reply_text=guard.safe_response,
            retrieved_diary_ids=pinned_ids,
            retrieved_memory_ids=[],
            is_crisis=True,
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

    slot_extractor = SlotExtractor()
    slot_result = slot_extractor.extract(content, intent=intent_result.intent_category)

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
    selected_skills = skill_registry.select_skills(
        content,
        skill_profile,
        token_budget=4000,
        decision_id=conversation_id,
    )

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

        query_llm = container._llm_for_tier(db, "light", agent_name="query_understander")
        understander = QueryUnderstander(
            llm=query_llm,
            tracer=container.llm_tracer,
            model=getattr(query_llm, "model", "") if query_llm else "",
        )
        understanding = understander.understand(content, context=brief_context)
        retrieval_query = understanding.rewritten
        logger.debug(
            "query.understood original=%s rewritten=%s terms=%s confidence=%.2f",
            content[:50],
            understanding.rewritten[:50],
            understanding.key_terms,
            understanding.confidence,
        )

        retrieved_ids = _retrieve_related_diary_ids(
            container, retrieval_query, exclude_ids=exclude_ids
        )
    elif auto_retrieve:
        # No retrieval needed — still run query understanding for episodic search
        logger.debug(
            "Intent skips diary RAG, using raw content for episodic: %s",
            intent_result.intent_category,
        )

    all_context_ids = pinned_ids + [did for did in retrieved_ids if did not in pinned_ids]

    episodic_text, memory_ids = _format_episodic_memories(container, retrieval_query)
    if skill_context_text:
        episodic_text = f"{episodic_text}\n\n## 技能分析\n{skill_context_text}"
    pinned_text = _format_retrieved_diaries(db, pinned_ids, user_id=user_id)
    retrieved_text = _format_retrieved_diaries(db, retrieved_ids, user_id=user_id)

    # ── Build tools (intent-filtered subset) ──
    all_tools = _build_tools(db, container, user_id=user_id)
    tools: dict[str, ToolFn] | None = None
    if all_tools and intent_result.need_tools:
        tools = {name: fn for name, fn in all_tools.items() if name in intent_result.need_tools}
        if not tools:
            tools = None

    # ── Stage 4: Agentic Loop ──
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

    # ── Stage 5: Output + episodic write-back ──
    _maybe_persist_episodic(
        container,
        content=content,
        reply_text=loop_result.reply_text,
        conversation_id=conversation_id,
        user_id=user_id,
    )

    # Get profile style from session (cached, loaded once)
    session = get_or_create_session(conversation_id, container=container, user_id=user_id)

    logger.info(
        "Chat reply generated: conversation=%s tokens=%s tools=%s stop=%s",
        conversation_id,
        loop_result.token_info.get("total_tokens_used", 0),
        loop_result.tool_calls_made,
        loop_result.stop_reason,
    )

    # ── Implicit style feedback (P2-6) ──
    # Extract style signals from user input and feed to Thompson Sampling
    try:
        from app.domain.feedback.implicit_style import (
            apply_implicit_signals,
            extract_implicit_style_signals,
        )

        current_style = session.profile_style or "empathetic"
        signals = extract_implicit_style_signals(content, current_style=current_style)
        if signals:
            thompson = getattr(container, "style_preference_store", None)
            if thompson is not None:
                from app.domain.feedback.thompson_sampling import ThompsonSampling

                sampler = ThompsonSampling(store=thompson)
                applied = apply_implicit_signals(sampler, signals, user_id=user_id)
                if applied:
                    logger.debug(
                        "Implicit style signals: conversation=%s applied=%d/%d",
                        conversation_id,
                        applied,
                        len(signals),
                    )
    except Exception as exc:
        logger.debug("Implicit style signal extraction failed (best-effort): %s", exc)

    # ── Entity extraction sidecar (P2-7) ──
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

    return ChatReplyResult(
        reply_text=loop_result.reply_text,
        retrieved_diary_ids=all_context_ids,
        retrieved_memory_ids=memory_ids,
        profile_style=session.profile_style,
        token_info=loop_result.token_info,
        stop_reason=loop_result.stop_reason,
        tool_calls_made=loop_result.tool_calls_made,
    )


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
    ``UnifiedMemoryAtom`` and then :meth:`MemoryGateway.persist_atom`
    for the unified write path.

    Conditions (either triggers):
    - Emotion score abs value ≥ 0.3 (meaningful positive or negative shift).
    - Severe signal detected (crisis-level — always write for safety audit trail).

    The write is best-effort: failures are logged and never propagate.
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

        stored = gw.persist_atom(atom)
        if stored:
            logger.info(
                "Episodic write-back: event=%s emotion=%s score=%.2f",
                atom.event_summary[:20],
                emotion_label,
                score,
            )
    except Exception as exc:
        logger.warning("Episodic write-back failed (best-effort): %s", exc)


# ── Night Talk generation from conversation ─────────────────────────


NIGHT_TALK_DRAFT_PROMPT = """你是一个温暖的心理陪伴助手。请从以下对话中提取「值得沉淀为夜话的片段」。

夜话是用户与夜记共构的关系记忆，区别于事件卡片。抽取重心是：
- 情感共鸣信号（用户感到被理解、被看见的瞬间）
- 关系进展信号（用户对陪伴关系的表达）
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


def generate_night_talk(
    db: Session,
    container: ServiceContainer,
    *,
    user_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Generate a night talk (关系记忆) from conversation history.

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
    llm: LLMClient | None = container._llm_for_tier(db, "light", agent_name="night-talk")
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


# Backward-compatible alias
def generate_card_from_conversation(
    db: Session,
    container: ServiceContainer,
    *,
    user_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Deprecated alias for :func:`generate_night_talk`."""
    return generate_night_talk(db, container, user_id=user_id, conversation_id=conversation_id)


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
