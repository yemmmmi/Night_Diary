"""AI-powered chat replies with pinned diary context and RAG retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.services import conversation_service, diary_service
from app.services.ai.prompts import CHAT_SYSTEM_PROMPT, CHAT_USER_PROMPT_TEMPLATE, FALLBACK_FEEDBACK
from app.services.ai.utils import extract_token_usage
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
) -> ChatReplyResult:
    """Build chat context and generate an assistant reply."""
    pinned_ids = _normalize_diary_ids(diary_ids)
    container.ensure_ai_stack()

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

    llm: LLMClient | None = container._llm_for_tier(db, "medium", agent_name="chat")
    if llm is None:
        logger.warning("Chat LLM unavailable; returning fallback")
        return ChatReplyResult(
            reply_text=FALLBACK_FEEDBACK,
            retrieved_diary_ids=all_context_ids,
            retrieved_memory_ids=memory_ids,
        )

    try:
        response = llm.invoke(prompt)
        reply_text = message_text(response).strip() or FALLBACK_FEEDBACK
        token_info = extract_token_usage(response)
        logger.info(
            "Chat reply generated: conversation=%s tokens=%s pinned=%s retrieved=%s",
            conversation_id,
            token_info.get("total_tokens_used"),
            pinned_ids,
            retrieved_ids,
        )
    except Exception as exc:
        logger.warning("Chat LLM invoke failed: %s", exc)
        reply_text = FALLBACK_FEEDBACK

    return ChatReplyResult(
        reply_text=reply_text,
        retrieved_diary_ids=all_context_ids,
        retrieved_memory_ids=memory_ids,
    )
