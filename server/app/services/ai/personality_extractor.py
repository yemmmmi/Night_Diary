"""Periodic LLM personality-tag extraction sidecar (P1-C).

``UserProfile.personality_tags`` had consumers (the insight agent's
「性格特征」 line, the Memory Library page) but no producer — the field
stayed an empty list unless a test set it. This sidecar derives tags from
the recent episodic window with a light-tier LLM call:

- scheduled fire-and-forget after diary/chat memory write-backs (same
  pattern as the entity-extraction sidecar);
- throttled to one extraction per user per ``PERIOD_DAYS`` — the latest
  ``insight_extraction`` row in ``profile_change_log`` doubles as the
  throttle state, so no extra table is needed;
- writes through ``LongTermMemory.update_profile`` so the P1-B audit
  trail records the change together with the memory pairs it was
  derived from;
- best-effort: any failure (no LLM, unreachable endpoint, malformed
  JSON, unchanged tags) is logged-and-swallowed, never re-raised.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from app.infrastructure.task_queue import enqueue_task

logger = logging.getLogger(__name__)

#: One extraction per user per week — personality is stable by definition.
PERIOD_DAYS = 7
#: Below this many entries there is not enough material to judge personality.
MIN_ENTRIES = 5
#: Cap on the episodic window fed to the prompt.
MAX_ENTRIES = 20
#: Cap on stored tags (matches the insight agent's display slice).
MAX_TAGS = 5

_EXTRACTION_PROMPT = """以下是用户最近的多条日记/对话记忆摘要：

{summaries}

用户画像中已有的性格标签：{existing}

请基于以上记忆，推断用户稳定的人格特质（而非短暂情绪状态），输出 2-5 个简短的中文标签。
只输出 JSON，格式：
```json
{{"tags": ["标签1", "标签2"], "reason": "一句话依据"}}
```"""


def build_extraction_prompt(summaries: list[str], existing_tags: list[str]) -> str:
    """Render the extraction prompt from memory summary lines."""
    lines = "\n".join(f"- {summary}" for summary in summaries) or "- （无）"
    existing = "、".join(existing_tags) if existing_tags else "（暂无）"
    return _EXTRACTION_PROMPT.format(summaries=lines, existing=existing)


def parse_tags_response(raw: str) -> list[str] | None:
    """Parse the LLM's JSON reply; ``None`` when unusable or empty."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None

    tags_value = data.get("tags") if isinstance(data, dict) else None
    if not isinstance(tags_value, list):
        return None

    tags: list[str] = []
    seen: set[str] = set()
    for item in tags_value:
        tag = str(item).strip()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags[:MAX_TAGS] or None


def _entry_pair(entry: Any) -> dict[str, Any]:
    """Evidence pair (date + summary + emotion) for the audit trail."""
    date_str = entry.event_date or datetime.fromtimestamp(entry.timestamp).strftime(
        "%Y-%m-%d"
    )
    return {"date": date_str, "summary": entry.event_summary[:80], "emotion": entry.emotion}


def _run_personality_sync(session_factory: Any, user_id: str) -> None:
    """Synchronous body — designed for ``enqueue_task`` / job dispatch."""
    try:
        from sqlalchemy import func as sa_func
        from sqlalchemy import select

        from app.domain.memory.long_term import LongTermMemory
        from app.infrastructure.memory_repository import (
            SqliteEpisodicMemoryStore,
            SqliteLongTermProfileStore,
            SqliteProfileChangeLogStore,
        )
        from app.infrastructure.models.profile_change_log import ProfileChangeLogRow

        # Throttle: the latest insight_extraction audit row doubles as state.
        with session_factory() as db:
            last_run = db.scalar(
                select(sa_func.max(ProfileChangeLogRow.created_at)).where(
                    ProfileChangeLogRow.user_id == user_id,
                    ProfileChangeLogRow.source == "insight_extraction",
                )
            )
        if last_run is not None and (datetime.now() - last_run).days < PERIOD_DAYS:
            return

        entries = SqliteEpisodicMemoryStore(session_factory).load_entries(user_id)
        if len(entries) < MIN_ENTRIES:
            return

        window = sorted(entries, key=lambda e: e.timestamp, reverse=True)[:MAX_ENTRIES]
        pairs = [_entry_pair(entry) for entry in window]

        llm = None
        try:
            from app.config import get_settings
            from app.shared.llm_factory import LLMFactory

            factory = LLMFactory(get_settings())
            with session_factory() as db:
                llm = factory.create_for_tier(db, "light", user_id=user_id)
        except Exception:
            llm = None  # LLM optional — skip silently when unavailable
        if llm is None:
            return

        memory = LongTermMemory(
            store=SqliteLongTermProfileStore(session_factory),
            change_log=SqliteProfileChangeLogStore(session_factory),
        )
        profile = memory.get_profile(user_id)
        existing_tags = list(profile.personality_tags)

        from app.shared.llm import message_text

        prompt = build_extraction_prompt(
            [f"{pair['date']} {pair['summary']}（{pair['emotion']}）" for pair in pairs],
            existing_tags,
        )
        tags = parse_tags_response(message_text(llm.invoke(prompt)))
        if not tags or tags == existing_tags:
            return  # nothing usable, or nothing new

        profile.personality_tags = tags
        memory.update_profile(user_id, profile, source="insight_extraction", evidence=pairs)
        logger.info("Personality tags extracted for user_id=%s: %s", user_id, tags)
    except Exception as exc:
        logger.warning("Personality extraction failed (best-effort): %s", exc)


def schedule_personality_extraction(container: Any, *, user_id: str) -> None:
    """Schedule the extraction sidecar (fire-and-forget, never raises)."""
    session_factory = getattr(container, "session_factory", None)
    if session_factory is None:
        return

    try:
        from app.services.job_service import enqueue_and_dispatch

        job = enqueue_and_dispatch(
            container,
            kind="personality_extraction",
            payload={"user_id": user_id},
            user_id=user_id,
        )
        if job is not None:
            return
    except Exception:
        pass  # fall through to plain dispatch

    enqueue_task(_run_personality_sync, session_factory, user_id)
