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

from app.domain.skills.disclosure import get_skill_disclosure
from app.domain.skills.intent import IntentDecision, classify_user_intent
from app.domain.skills.record_skill import SkillRunOutcome
from app.domain.skills.user_skill_registry import get_user_skill_registry

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

#: Shown when the router leaned toward a skill but was not confident enough
#: to act — a lightweight disambiguation card instead of a guessed proposal.
_CLARIFY_QUESTION = (
    "我还不确定你想让我做什么。"
    "是想把这段整理成日记、帮你分析一下状态，还是一起理个计划？"
)

#: ``prefill`` is dropped into the composer so one tap gives the router an
#: unambiguous instruction on the next turn.
_CLARIFY_OPTIONS: tuple[dict[str, str], ...] = (
    {"skill": "record", "label": "整理成日记", "prefill": "帮我记一篇日记："},
    {"skill": "insight", "label": "分析我的状态", "prefill": "帮我分析一下我最近的状态"},
    {"skill": "plan", "label": "一起理个计划", "prefill": "帮我做个计划："},
    {"skill": "chat", "label": "就聊聊", "prefill": "先不着急，就聊聊"},
)


def build_clarification_outcome() -> SkillRunOutcome:
    """Build the disambiguation reply — writes nothing, only asks."""
    return SkillRunOutcome(
        skill="clarify",
        reply_text=_CLARIFY_QUESTION,
        skill_result={
            "skill": "clarify",
            "options": [dict(option) for option in _CLARIFY_OPTIONS],
        },
        token_info=None,
    )


def route_intent(
    container: ServiceContainer, content: str
) -> IntentDecision:
    """Classify intent; the light LLM is the fallback inside the router.

    The Level-0 skill catalog (id / label / description / token cost) is
    injected into the fallback prompt so the router sees the registered
    skills rather than a fixed list.
    """
    light_llm = container._llm_for_tier("light", agent_name="user_skill_intent")
    catalog = get_skill_disclosure().level0_catalog()
    return classify_user_intent(content, llm=light_llm, skill_catalog=catalog)


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

    Level-1 progressive disclosure: once a skill is hit, its SKILL.md body is
    loaded on demand and injected into the skill's generation prompt.
    """
    try:
        registry = get_user_skill_registry()
        if skill is not None and registry.has(skill):
            decision = IntentDecision(intent=skill, source="manual")
        else:
            decision = route_intent(container, content)

        if decision.should_clarify:
            logger.info(
                "user_skill ambiguous, asking to clarify: conversation=%s "
                "intent=%s confidence=%.2f",
                conversation_id,
                decision.intent,
                decision.confidence,
            )
            return build_clarification_outcome()

        if decision.intent == "chat" or not registry.has(decision.intent):
            return None
        logger.info(
            "user_skill routed: conversation=%s intent=%s source=%s",
            conversation_id,
            decision.intent,
            decision.source,
        )

        skill_doc = get_skill_disclosure().level1_body(decision.intent)
        llm = container._llm_for_tier("medium", agent_name=f"user_skill_{decision.intent}")
        return registry.run(
            db,
            container,
            llm,
            skill_id=decision.intent,
            content=content,
            user_id=user_id,
            conversation_id=conversation_id,
            skill_doc=skill_doc,
        )
    except Exception as exc:
        logger.warning(
            "user skill dispatch failed (falling back to chat): %s", exc
        )
        return None
