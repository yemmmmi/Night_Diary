"""Skill prompt injection strategies.

Two strategies for injecting :class:`SkillDoc` content into LLM prompts:

- :class:`FullInjectionStrategy` — inject every skill's ``full_text`` in one
  shot.  Simple but token-expensive; best when the skill set is small.

- :class:`ProgressiveDisclosureStrategy` — inject only the compact ``summary``
  of each skill, then let the LLM request a skill's full ``body`` on demand via
  ``<use_skill>name</use_skill>`` declarations.  Saves tokens when only a subset
  of skills is actually needed.

Both strategies expose :meth:`estimate_tokens` so the caller can budget before
sending the prompt to the LLM.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.shared.token_utils import estimate_tokens

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.skills.skill_loader import SkillDoc

__all__ = [
    "FullInjectionStrategy",
    "ProgressiveDisclosureStrategy",
    "SkillInjector",
]


class SkillInjector(ABC):
    """Abstract base for prompt-injection strategies."""

    @abstractmethod
    def inject_prompt(self, skills: Sequence[SkillDoc], base_prompt: str) -> str:
        """Return ``base_prompt`` augmented with skill documentation."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate the token cost of *text* (delegates to shared token_utils)."""
        return estimate_tokens(text)

    def estimate_injection_cost(self, skills: Sequence[SkillDoc]) -> int:
        """Estimate the token cost of injecting *skills* (excludes base prompt)."""
        prompt = self.inject_prompt(skills, base_prompt="")
        return self.estimate_tokens(prompt)


# ---------------------------------------------------------------------------
# FullInjectionStrategy
# ---------------------------------------------------------------------------

class FullInjectionStrategy(SkillInjector):
    """Inject all skills' ``full_text`` in a single prompt block.

    Suitable for small skill sets where the overhead of progressive disclosure
    outweighs the token savings.
    """

    HEADER = "--- 可用技能文档（完整版） ---"
    FOOTER = "--- 技能文档结束 ---"

    def inject_prompt(self, skills: Sequence[SkillDoc], base_prompt: str) -> str:
        if not skills:
            return base_prompt

        blocks: list[str] = [self.HEADER]
        for skill in skills:
            blocks.append(f"\n[{skill.name}]\n{skill.full_text}")
        blocks.append(self.FOOTER)

        skill_block = "\n\n".join(blocks)
        if base_prompt:
            return f"{base_prompt}\n\n{skill_block}"
        return skill_block


# ---------------------------------------------------------------------------
# ProgressiveDisclosureStrategy
# ---------------------------------------------------------------------------

class ProgressiveDisclosureStrategy(SkillInjector):
    """Inject only compact summaries; LLM loads full body on demand.

    The LLM is instructed to declare which skill it wants to use via::

        <use_skill>skill_name</use_skill>

    The host system then resolves the declaration and appends the full ``body``
    in a subsequent turn.  This keeps the initial prompt lean.
    """

    HEADER = "--- 可用技能摘要（按需加载） ---"
    FOOTER = "--- 技能摘要结束 ---"
    INSTRUCTION = (
        "当你需要使用某个技能时，请在回复中声明 <use_skill>技能名</use_skill>，"
        "系统会按需加载该技能的完整文档（触发条件、能力详述、调用方式、输出示例）。"
    )

    def inject_prompt(self, skills: Sequence[SkillDoc], base_prompt: str) -> str:
        if not skills:
            return base_prompt

        blocks: list[str] = [self.HEADER, self.INSTRUCTION, ""]
        for skill in skills:
            blocks.append(f"【{skill.name}】\n{skill.summary}")
        blocks.append(self.FOOTER)

        skill_block = "\n\n".join(blocks)
        if base_prompt:
            return f"{base_prompt}\n\n{skill_block}"
        return skill_block
