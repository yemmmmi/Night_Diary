"""Insight skill — restrained, rational psychological self-understanding.

Contract (PR8): decompose the user's input, surface the emotional essence
behind it, and help them see who they are. Theory entries from the offline
psychology knowledge base ground the analysis; they are reference angles,
never diagnostic labels. Returns None when no LLM is available — the normal
chat path takes over.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.domain.knowledge.psychology import PsychologyEntry, retrieve_psychology
from app.domain.skills.record_skill import SkillRunOutcome
from app.shared.llm import LLMClient, message_text

logger = logging.getLogger(__name__)

_INSIGHT_PROMPT = """你是「洞悉」技能，帮用户看清自己此刻的情感本质。基于用户输入做一次克制、理性的心理分析。

可参考的心理学视角（只在真正相关时使用，不堆砌术语，不贴标签）：
{knowledge}

要求：
1. 先用一两句客观复述用户输入的核心内容，让用户确认你听懂了。
2. 拆解三个层面：表面在说什么、情绪信号是什么、背后可能的心理需求。
3. 全程克制理性：不下诊断、不给病理标签、不替用户下结论；推测一律用「可能」「也许」。
4. 结尾给一个具体的自我观察问题，帮用户向内多看一步，而不是给出行动指令。
5. 总长控制在 300 字以内，直接输出分析正文，不要开场白。

用户输入：
{content}
"""


def _format_knowledge(entries: list[PsychologyEntry]) -> str:
    if not entries:
        return "（无匹配视角，凭常识分析）"
    return "\n".join(
        f"- {e.theory}：{e.summary}（观察角度：{e.observation}）" for e in entries
    )


def run(
    db: Session,
    *,
    llm: LLMClient | None,
    content: str,
    user_id: str,
    conversation_id: str = "",
) -> SkillRunOutcome | None:
    """Analyze the user's inner state; None → fall back to normal chat."""
    if llm is None:
        return None

    entries = retrieve_psychology(content, top=3)
    prompt = _INSIGHT_PROMPT.format(
        knowledge=_format_knowledge(entries),
        content=content[:2000],
    )
    response = llm.invoke(prompt)
    analysis = message_text(response).strip()
    if not analysis:
        logger.warning("insight skill produced empty analysis, falling back to chat")
        return None

    logger.info(
        "insight skill: theories=%s user=%s conversation=%s",
        [e.theory for e in entries],
        user_id,
        conversation_id,
    )
    return SkillRunOutcome(
        skill="insight",
        reply_text=analysis,
        skill_result={
            "skill": "insight",
            "matched_theories": [e.theory for e in entries],
            "observations": [e.observation for e in entries],
        },
    )
