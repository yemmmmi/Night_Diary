"""CardPromptService — generate contextual guided questions for memory cards.

Uses a lightweight LLM call to produce 3 personalised questions based
on recent card/diary history.  Follows the same pattern as the existing
agent LLM calls but packaged as a standalone service function.
"""

from __future__ import annotations

import json
import logging
import time

from app.shared.llm import LLMClient, message_text

logger = logging.getLogger(__name__)

CARD_PROMPT_TEMPLATE = """你是一个温和的生活助手，正在帮助用户做每日复盘。

请根据以下背景信息，生成 3 个引导性的问题，帮助用户回忆和表达今天的感受。
问题应该：
- 温和开放，不咄咄逼人
- 覆盖情绪、事件、反思三个维度
- 每个问题不超过 30 个字
- 用日常口语化的中文

背景信息：
{context}

请只返回一个 JSON 数组，格式如下，不要包含其他内容：
["问题1", "问题2", "问题3"]
"""


def build_card_prompt_context(
    recent_cards_summary: str = "",
    recent_diary_summary: str = "",
    today_entries: str = "",
) -> str:
    """Build a compact context string for the prompt LLM."""
    parts: list[str] = []
    if today_entries:
        parts.append(f"今天的已有记录：{today_entries}")
    if recent_cards_summary:
        parts.append(f"最近的记忆卡片：{recent_cards_summary}")
    if recent_diary_summary:
        parts.append(f"最近的日记摘要：{recent_diary_summary}")
    if not parts:
        parts.append("用户是第一次使用，没有历史记录。请提通用的问题引导用户开始。")
    return "\n".join(parts)


def generate_card_questions(
    llm: LLMClient,
    *,
    recent_cards_summary: str = "",
    recent_diary_summary: str = "",
    today_entries: str = "",
    model: str = "",
) -> list[str]:
    """Generate 3 personalised guiding questions via LLM.

    Returns a list of 3 question strings, or a fallback list on failure.
    """
    context = build_card_prompt_context(
        recent_cards_summary=recent_cards_summary,
        recent_diary_summary=recent_diary_summary,
        today_entries=today_entries,
    )
    prompt = CARD_PROMPT_TEMPLATE.format(context=context)

    started = time.perf_counter()
    error: str | None = None
    text = ""

    try:
        response = llm.invoke(prompt)
        text = message_text(response).strip()
        questions = _parse_questions(text)
        logger.info(
            "CardPrompt generated %d questions (%.0f ms)",
            len(questions),
            (time.perf_counter() - started) * 1000,
        )
        return questions
    except Exception as exc:
        error = str(exc)
        logger.warning("CardPrompt LLM call failed: %s", exc)
    finally:
        logger.debug(
            "CardPrompt call: latency=%.0fms error=%s",
            (time.perf_counter() - started) * 1000,
            error,
        )

    return _fallback_questions()


def _parse_questions(text: str) -> list[str]:
    """Parse JSON array from LLM output, tolerating markdown fences."""
    text = text.strip()
    # Remove markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(q) for q in parsed[:3] if q]
    except json.JSONDecodeError:
        pass

    # Brute-force: extract quoted strings
    import re

    matches = re.findall(r'"([^"]+)"', text)
    if matches:
        return matches[:3]

    return _fallback_questions()


def _fallback_questions() -> list[str]:
    return [
        "今天让你印象最深的一件事是什么？",
        "这件事给你带来了什么感受？",
        "如果可以重来，你会怎么做？",
    ]
