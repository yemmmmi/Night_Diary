"""User-skill dispatcher — routes a chat turn to 记录 / 洞悉 / 计划.

Mounted by ``conversation_ai_service`` in both the sync and streaming
paths, right after input preprocessing. When a skill matches, its outcome
short-circuits the normal Agentic Loop; otherwise the turn continues as
plain chat, so the skill layer is strictly additive.

Every failure inside the dispatcher degrades to ``None`` (normal chat) —
a skill must never break the reply it was meant to enhance.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.domain.skills.intent import IntentDecision, classify_user_intent
from app.domain.skills.record_skill import SkillRunOutcome
from app.domain.skills.user_skill_registry import get_user_skill_registry

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)


def route_intent(
    container: ServiceContainer, content: str
) -> IntentDecision:
    """Classify intent; the light LLM is the fallback inside the router."""
    light_llm = container._llm_for_tier("light", agent_name="user_skill_intent")
    return classify_user_intent(content, llm=light_llm)


def run_user_skill(
    db: Session,
    container: ServiceContainer,
    *,
    conversation_id: str,
    content: str,
    user_id: str,
    skill: str | None = None,
) -> SkillRunOutcome | None:
    """Run the matching user skill, or None to continue as normal chat.

    *skill* forces a specific skill (user-side manual selection) and skips
    intent classification entirely; only registered skills are honored.
    """
    try:
        registry = get_user_skill_registry()
        if skill is not None and registry.has(skill):
            decision = IntentDecision(intent=skill, source="manual")
        else:
            decision = route_intent(container, content)
        if decision.intent == "chat" or not registry.has(decision.intent):
            return None
        logger.info(
            "user_skill routed: conversation=%s intent=%s source=%s",
            conversation_id,
            decision.intent,
            decision.source,
        )

        llm = container._llm_for_tier("medium", agent_name=f"user_skill_{decision.intent}")
        return registry.run(
            db,
            container,
            llm,
            skill_id=decision.intent,
            content=content,
            user_id=user_id,
            conversation_id=conversation_id,
        )
    except Exception as exc:
        logger.warning(
            "user skill dispatch failed (falling back to chat): %s", exc
        )
        return None
