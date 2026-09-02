"""Record skill — transcribe user dictation into an objective diary entry.

Design contract (PR8):
- The diary uses「你」as the subject referring to the user.
- No fabrication, no embellishment, no added commentary — only what the
  user actually said.
- Without an LLM the skill degrades to storing the raw input verbatim
  (still satisfies "no fabrication") instead of failing the turn.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.services import diary_service
from app.shared.llm import LLMClient, message_text

logger = logging.getLogger(__name__)

_MAX_DIARY_CHARS = 2000

_RECORD_PROMPT = """你是「记录」技能，把用户的口述转写为一篇客观的日记。

转写规则：
1. 主语用「你」指代用户，以第三人称视角记录。
2. 严格基于用户口述的内容，不虚构任何细节，不补充未提及的信息，不添加感想、评价或情绪渲染。
3. 保留用户提到的时间、地点、人物、事件经过。
4. 语言克制、完整、通顺，按时间或逻辑顺序组织成连贯的日记正文。
5. 只输出日记正文，不要标题、不要日期抬头、不要任何解释或开场白。

用户口述：
{content}
"""


@dataclass(frozen=True, slots=True)
class SkillRunOutcome:
    """Uniform result shape returned by the three user skills."""

    skill: str
    reply_text: str
    skill_result: dict[str, Any]
    token_info: dict[str, int] | None = None


def run(
    db: Session,
    *,
    llm: LLMClient | None,
    content: str,
    user_id: str,
    conversation_id: str = "",
    collection_manager: Any = None,
) -> SkillRunOutcome:
    """Transcribe *content* into a diary entry and persist it."""
    diary_text = ""
    if llm is not None:
        try:
            response = llm.invoke(_RECORD_PROMPT.format(content=content[:2000]))
            diary_text = message_text(response).strip()
        except Exception as exc:
            logger.warning("record skill LLM failed, storing raw input: %s", exc)
    if not diary_text:
        diary_text = content.strip()
    diary_text = diary_text[:_MAX_DIARY_CHARS]

    entry = diary_service.create_entry(
        db,
        user_id=user_id,
        content=diary_text,
        collection_manager=collection_manager,
    )
    logger.info(
        "record skill: diary_id=%s user=%s conversation=%s",
        entry.id,
        user_id,
        conversation_id,
    )

    date_str = entry.date.isoformat() if entry.date else ""
    return SkillRunOutcome(
        skill="record",
        reply_text=f"已为你记下这篇日记（{date_str}），未作任何添改。",
        skill_result={
            "skill": "record",
            "diary_id": entry.id,
            "date": date_str,
            "content": diary_text,
        },
    )
