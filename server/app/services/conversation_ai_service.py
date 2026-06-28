"""AI-powered chat replies with pinned diary context and RAG retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.services import conversation_service, diary_service
from app.services.ai.prompts import CHAT_SYSTEM_PROMPT, CHAT_USER_PROMPT_TEMPLATE, FALLBACK_FEEDBACK
from app.services.ai.utils import extract_token_usage
from app.services.memory_gateway import MemoryGateway
from app.shared.crisis_guard import CrisisGuard, get_crisis_guard
from app.shared.emotion_estimator import get_emotion_estimator
from app.shared.errors import ValidationError
from app.shared.llm import LLMClient, message_text

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

MAX_PINNED_DIARIES = 3
MAX_HISTORY_MESSAGES = 10
MAX_RETRIEVAL_RESULTS = 3
MAX_EPISODIC_RESULTS = 3


@dataclass(frozen=True, slots=True)
class ChatReplyResult:
    reply_text: str
    retrieved_diary_ids: list[int]
    retrieved_memory_ids: list[str]
    is_crisis: bool = False
    profile_style: str = ""


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


def _format_chat_history(db: Session, conversation_id: str) -> str:
    rows = conversation_service.list_messages(db, conversation_id)
    if not rows:
        return "（暂无历史）"
    recent = rows[-MAX_HISTORY_MESSAGES:]
    lines: list[str] = []
    for row in recent:
        role = "用户" if row.role == "user" else "回信者"
        content = (row.content or "").strip().replace("\n", " ")
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"{role}：{content}")
    return "\n".join(lines)


def _retrieve_related_diary_ids(
    container: ServiceContainer,
    query: str,
    *,
    exclude_ids: set[int],
) -> list[int]:
    if not query.strip() or container.retriever is None:
        return []
    try:
        results = container.retriever.retrieve(query, top_k=MAX_RETRIEVAL_RESULTS + len(exclude_ids))
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


def _format_retrieved_diaries(db: Session, diary_ids: list[int]) -> str:
    if not diary_ids:
        return "（无）"
    entries = diary_service.get_entries_by_ids(db, diary_ids)
    if not entries:
        return "（无）"
    return "\n\n".join(diary_service.format_diary_excerpt(entry) for entry in entries)


def _format_episodic_memories(container: ServiceContainer, query: str) -> tuple[str, list[str]]:
    if container.episodic_memory is None:
        return "（无）", []
    try:
        entries = container.episodic_memory.retrieve_relevant(query, top_k=MAX_EPISODIC_RESULTS)
    except Exception as exc:
        logger.warning("Chat episodic retrieve failed: %s", exc)
        return "（无）", []

    if not entries:
        return "（无）", []

    lines: list[str] = []
    memory_ids: list[str] = []
    for entry in entries:
        memory_ids.append(entry.entry_id or "")
        emotion = entry.emotion or "未知"
        event = (entry.event or "").strip()
        lines.append(f"- [{emotion}] {event}")
    return "\n".join(lines), [mid for mid in memory_ids if mid]


def generate_reply(
    db: Session,
    container: ServiceContainer,
    *,
    conversation_id: str,
    content: str,
    diary_ids: list[int],
    auto_retrieve: bool = True,
    crisis_guard: CrisisGuard | None = None,
) -> ChatReplyResult:
    """Build chat context and generate an assistant reply.

    Includes crisis detection (short-circuits to safety resources) and
    long-term profile loading (preferred_style, recurring_topics) that were
    previously missing from the conversation scene.
    """
    pinned_ids = _normalize_diary_ids(diary_ids)
    container.ensure_ai_stack()

    # ── Crisis guard: P0 safety, checked before any LLM call ──
    guard = crisis_guard or get_crisis_guard()
    if guard.detect(content):
        logger.warning("Crisis detected in conversation=%s, returning safety resources", conversation_id)
        return ChatReplyResult(
            reply_text=guard.safe_response,
            retrieved_diary_ids=pinned_ids,
            retrieved_memory_ids=[],
            is_crisis=True,
        )

    # ── Load long-term profile (was missing from scene 2) ──
    profile_style = ""
    profile_topics: list[str] = []
    if container.long_term_memory is not None:
        try:
            profile = container.long_term_memory.get_profile("default")
            profile_style = profile.preferred_response_style or ""
            profile_topics = list(profile.recurring_topics or [])
        except Exception as exc:
            logger.warning("Long-term profile load failed: %s", exc)

    pinned_entries = diary_service.get_entries_by_ids(db, pinned_ids)
    if len(pinned_entries) != len(pinned_ids):
        raise ValidationError("引用的日记不存在或已被删除")

    exclude_ids = set(pinned_ids)
    retrieved_ids: list[int] = []
    if auto_retrieve:
        retrieved_ids = _retrieve_related_diary_ids(container, content, exclude_ids=exclude_ids)

    all_context_ids = pinned_ids + [did for did in retrieved_ids if did not in pinned_ids]

    episodic_text, memory_ids = _format_episodic_memories(container, content)
    chat_history = _format_chat_history(db, conversation_id)

    # Include recurring topics in the prompt when available
    topics_text = "、".join(profile_topics) if profile_topics else "（暂无）"

    prompt = (
        f"{CHAT_SYSTEM_PROMPT}\n\n"
        + CHAT_USER_PROMPT_TEMPLATE.format(
            pinned_diaries=_format_retrieved_diaries(db, pinned_ids),
            retrieved_diaries=_format_retrieved_diaries(db, retrieved_ids),
            episodic_memories=episodic_text,
            chat_history=chat_history,
            user_message=content.strip(),
        )
    )
    if profile_style or profile_topics:
        prompt += f"\n\n【用户画像】偏好风格：{profile_style or '自然'}；近期关注：{topics_text}"

    llm: LLMClient | None = container._llm_for_tier(db, "medium", agent_name="chat")
    if llm is None:
        logger.warning("Chat LLM unavailable; returning fallback")
        return ChatReplyResult(
            reply_text=FALLBACK_FEEDBACK,
            retrieved_diary_ids=all_context_ids,
            retrieved_memory_ids=memory_ids,
            profile_style=profile_style,
        )

    try:
        response = llm.invoke(prompt)
        reply_text = message_text(response).strip() or FALLBACK_FEEDBACK
        token_info = extract_token_usage(response)
        logger.info(
            "Chat reply generated: conversation=%s tokens=%s pinned=%s retrieved=%s style=%s",
            conversation_id,
            token_info.get("total_tokens_used"),
            pinned_ids,
            retrieved_ids,
            profile_style or "default",
        )
    except Exception as exc:
        logger.warning("Chat LLM invoke failed: %s", exc)
        reply_text = FALLBACK_FEEDBACK

    # ── Conditional episodic write-back (best-effort) ──
    _maybe_persist_episodic(container, content=content, reply_text=reply_text)

    return ChatReplyResult(
        reply_text=reply_text,
        retrieved_diary_ids=all_context_ids,
        retrieved_memory_ids=memory_ids,
        profile_style=profile_style,
    )


#: Minimum emotion intensity (abs score) to trigger episodic write-back.
_EPISODIC_WRITE_THRESHOLD = 0.3


def _maybe_persist_episodic(
    container: ServiceContainer,
    *,
    content: str,
    reply_text: str,
) -> None:
    """Persist an episodic entry when the turn carries strong emotion.

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

        gw = MemoryGateway.from_container(container)
        emotion_label = estimator.estimate(content).label
        # Use first 50 chars of user message as event label (heuristic).
        event_label = content.strip()[:50]

        stored = gw.persist_episodic(
            event=event_label,
            emotion=emotion_label,
            ai_suggestion=reply_text[:200],
            importance=min(abs(score) + 0.3, 1.0),
        )
        if stored:
            logger.info("Episodic write-back: event=%s emotion=%s score=%.2f", event_label[:20], emotion_label, score)
    except Exception as exc:
        logger.warning("Episodic write-back failed (best-effort): %s", exc)


# ── Card generation from conversation ─────────────────────────────────


CARD_GEN_PROMPT_TEMPLATE = """你是一个温暖的心理陪伴助手。请根据以下对话内容，生成一张记忆卡片的摘要。

对话内容：
{conversation_text}

请返回一个 JSON 对象，格式如下，不要包含其他内容：
{{"event_summary": "用一句话概括对话中的核心事件或主题（不超过30字）", "tags": ["标签1", "标签2"]}}

要求：
- event_summary 应聚焦于用户提到的具体事件或情感主题
- tags 应包含 1-3 个关键词标签
- 用日常口语化的中文
"""

CARD_GEN_FALLBACK = {"event_summary": "对话摘要生成失败", "tags": ["对话"]}


def generate_card_from_conversation(
    db: Session,
    container: ServiceContainer,
    *,
    conversation_id: str,
) -> dict[str, Any]:
    """Generate a memory card summary (emotion + event + tags) from conversation history."""
    from app.shared.emotion_estimator import EmotionEstimator

    messages = conversation_service.list_messages(db, conversation_id)
    if not messages:
        return {"emotion": "平静", "event_summary": "暂无对话内容", "tags": ["对话"]}

    # Build conversation text for LLM and emotion estimation
    conv_lines: list[str] = []
    for msg in messages:
        role = "用户" if msg.role == "user" else "回信者"
        conv_lines.append(f"{role}：{(msg.content or '').strip()}")
    conv_text = "\n".join(conv_lines)

    # Estimate emotion from user messages only (more accurate)
    user_text = " ".join(
        (msg.content or "").strip() for msg in messages if msg.role == "user"
    )
    estimator = EmotionEstimator()
    estimate = estimator.estimate(user_text)
    emotion_label = estimate.label if estimate.label != "crisis" else "negative"

    # Map score to emotion word
    emotion_word_map = {
        "positive": "积极",
        "negative": "低落",
        "neutral": "平静",
    }
    emotion = emotion_word_map.get(emotion_label, "平静")

    # Generate event summary and tags via LLM
    container.ensure_ai_stack()
    llm: LLMClient | None = container._llm_for_tier(db, "light", agent_name="card-gen")
    if llm is None:
        logger.warning("Card-gen LLM unavailable; returning emotion-only result")
        return {"emotion": emotion, "event_summary": conv_lines[0][:30] if conv_lines else "对话", "tags": ["对话"]}

    prompt = CARD_GEN_PROMPT_TEMPLATE.format(conversation_text=conv_text[:2000])
    try:
        response = llm.invoke(prompt)
        text = message_text(response).strip()
        result = _parse_card_json(text)
        result["emotion"] = emotion
        logger.info("Card-gen generated for conversation=%s emotion=%s", conversation_id, emotion)
        return result
    except Exception as exc:
        logger.warning("Card-gen LLM invoke failed: %s", exc)
        return {"emotion": emotion, "event_summary": CARD_GEN_FALLBACK["event_summary"], "tags": CARD_GEN_FALLBACK["tags"]}


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
