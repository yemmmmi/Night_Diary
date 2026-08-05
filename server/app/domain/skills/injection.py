"""技能提示词注入策略。

两种将 :class:`SkillDoc` 内容注入 LLM 提示词的策略：

- :class:`FullInjectionStrategy` — 一次性注入所有技能的 ``full_text``。
  简单但 token 开销大；适合技能集合较小的场景。

- :class:`ProgressiveDisclosureStrategy` — 仅注入每个技能的精简 ``summary``，
  然后让 LLM 通过 ``<use_skill>name</use_skill>`` 声明按需请求技能的完整
  ``body``。当实际只需部分技能时，可节省 token。

两种策略均提供 :meth:`estimate_tokens`，调用方可在将提示词发送给 LLM 之前
进行 token 预算评估。
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
    """提示词注入策略的抽象基类。"""

    @abstractmethod
    def inject_prompt(self, skills: Sequence[SkillDoc], base_prompt: str) -> str:
        """返回附加了技能文档的 ``base_prompt``。"""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """估算 *text* 的 token 开销（委托给共享的 token_utils）。"""
        return estimate_tokens(text)

    def estimate_injection_cost(self, skills: Sequence[SkillDoc]) -> int:
        """估算注入 *skills* 的 token 开销（不含基础提示词）。"""
        prompt = self.inject_prompt(skills, base_prompt="")
        return self.estimate_tokens(prompt)


# ---------------------------------------------------------------------------
# FullInjectionStrategy
# ---------------------------------------------------------------------------

class FullInjectionStrategy(SkillInjector):
    """在单个提示词块中注入所有技能的 ``full_text``。

    适用于小型技能集合，此时渐进式披露的开销超过了其节省的 token。
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
    """仅注入精简摘要；LLM 按需加载完整 body。

    指示 LLM 通过以下方式声明要使用的技能::

        <use_skill>skill_name</use_skill>

    宿主系统随后解析该声明，并在后续轮次中追加完整的 ``body``。
    这样可以保持初始提示词精简。
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
