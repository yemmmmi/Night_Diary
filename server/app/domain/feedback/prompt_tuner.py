"""Dynamic prompt tuning based on learned user preferences.

Example::

    from app.domain.feedback.prompt_tuner import PromptTuner
    from app.domain.feedback.thompson_sampling import ThompsonSampling
    from app.infrastructure.feedback_repository import SqliteStylePreferenceStore

    store = SqliteStylePreferenceStore(session_factory)
    tuner = PromptTuner(store=store, thompson=ThompsonSampling(store=store))
    prompt = tuner.build_dynamic_prompt(
        user_id="default",
        agent_type="empathy",
        diary_word_count=120,
        hour=23,
        emotion_intensity=0.8,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.domain.feedback.thompson_sampling import ThompsonSampling
from app.domain.feedback.types import (
    DEFAULT_DIRECTNESS,
    DEFAULT_RESPONSE_LENGTH,
    DEFAULT_STYLE,
    STYLES,
    AgentType,
    ResponseLength,
    StylePreferenceRecord,
    StylePreferenceStore,
    UserPreference,
)

logger = logging.getLogger(__name__)

SUPPORTED_STYLES = list(STYLES)

_EMPATHY_STYLE_PROMPTS = {
    "empathetic": "温暖共情、理解接纳，让用户感受到被理解和支持。用柔和的语言确认用户的情绪。",
    "practical": "务实关怀、在表达理解的同时给出具体可操作的建议。语言简洁有力。",
    "philosophical": "富有哲思、引导用户从更宏观的角度看待当下经历，同时保持温暖和理解。",
    "humorous": "轻松幽默、用温和的方式化解情绪紧张，但绝不轻视用户的感受。",
}

_INSIGHT_STYLE_PROMPTS = {
    "empathetic": "在分析模式和趋势时，先共情再给出洞察。语言温暖，建议具有关怀感。",
    "practical": "直接指出模式和趋势，给出具体可执行的行动建议。数据驱动，结论明确。",
    "philosophical": "从更深层的角度解读行为模式，引导用户思考背后的动机和价值观。",
    "humorous": "用轻松的方式呈现分析结果，让洞察更容易被接受。但保持专业性。",
}

_LENGTH_PROMPTS = {
    ResponseLength.SHORT: "请保持回应简洁精炼，控制在 50-100 字以内。直击要点，不做过多展开。",
    ResponseLength.MEDIUM: "请将回应控制在适中长度（100-200 字），平衡深度和简洁。",
    ResponseLength.LONG: "可以适当展开回应（200-350 字），提供更丰富的分析和建议。",
}

_DIRECTNESS_PROMPTS = {
    "low": "语言风格偏委婉含蓄，多用引导性提问而非直接陈述，给用户留出自我反思的空间。",
    "medium": "语言风格适中，在温和表达和直接建议之间取得平衡。",
    "high": "语言风格偏直接坦率，清晰指出观察到的问题和建议，不绕弯子。",
}


@dataclass(frozen=True, slots=True)
class ResponseLengthContext:
    """Inputs for response-length inference; B-9 agents can pass richer context."""

    diary_word_count: int = 0
    hour: int | None = None
    emotion_intensity: float = 0.5


class PromptTuner:
    """Build dynamic prompt fragments from live style preferences."""

    def __init__(
        self,
        store: StylePreferenceStore | None = None,
        thompson: ThompsonSampling | None = None,
    ) -> None:
        self._store = store
        self._thompson = thompson or ThompsonSampling(store=store)

    def get_user_preference(
        self,
        user_id: str = "default",
        *,
        diary_word_count: int = 0,
        hour: int | None = None,
        emotion_intensity: float = 0.5,
    ) -> UserPreference:
        """Load the current preference vector for one analysis request."""
        try:
            preferences = self._load_preferences(user_id)
            if not preferences:
                return get_default_preference()

            style = self._thompson.sample_style(user_id)
            response_length = infer_response_length(
                preferences=preferences,
                context=ResponseLengthContext(
                    diary_word_count=diary_word_count,
                    hour=hour,
                    emotion_intensity=emotion_intensity,
                ),
            )
            directness = infer_directness(preferences)

            logger.debug(
                "Loaded preference user_id=%s style=%s length=%s directness=%.2f",
                user_id,
                style,
                response_length.value,
                directness,
            )
            return UserPreference(
                response_length=response_length,
                style=style,
                directness=directness,
            )
        except Exception as exc:
            logger.warning(
                "Failed to load preference user_id=%s, using defaults: %s",
                user_id,
                exc,
            )
            return get_default_preference()

    def build_dynamic_prompt(
        self,
        user_id: str = "default",
        agent_type: str = AgentType.EMPATHY.value,
        *,
        diary_word_count: int = 0,
        hour: int | None = None,
        emotion_intensity: float = 0.5,
    ) -> str:
        preference = self.get_user_preference(
            user_id,
            diary_word_count=diary_word_count,
            hour=hour,
            emotion_intensity=emotion_intensity,
        )
        return self._format_prompt_fragment(preference, agent_type)

    def _load_preferences(self, user_id: str) -> list[StylePreferenceRecord]:
        if self._store is None:
            return []
        return self._store.get_preferences(user_id)

    def _format_prompt_fragment(self, preference: UserPreference, agent_type: str) -> str:
        if agent_type == AgentType.INSIGHT.value:
            style_prompts = _INSIGHT_STYLE_PROMPTS
        else:
            style_prompts = _EMPATHY_STYLE_PROMPTS

        style_desc = style_prompts.get(preference.style, style_prompts[DEFAULT_STYLE])
        length_desc = _LENGTH_PROMPTS.get(
            preference.response_length,
            _LENGTH_PROMPTS[DEFAULT_RESPONSE_LENGTH],
        )
        directness_level = self._directness_to_level(preference.directness)
        directness_desc = _DIRECTNESS_PROMPTS.get(
            directness_level,
            _DIRECTNESS_PROMPTS["medium"],
        )

        return "\n".join(
            [
                "\n## 用户偏好适配指令\n",
                f"### 回应风格\n{style_desc}",
                f"\n### 回应长度\n{length_desc}",
                f"\n### 表达直接度\n{directness_desc}",
            ]
        )

    @staticmethod
    def _directness_to_level(directness: float) -> str:
        if directness < 0.35:
            return "low"
        if directness > 0.65:
            return "high"
        return "medium"


def infer_response_length(
    *,
    preferences: list[StylePreferenceRecord] | None = None,
    context: ResponseLengthContext | None = None,
) -> ResponseLength:
    """Infer response length from feedback history and diary context."""
    ctx = context or ResponseLengthContext()

    if preferences:
        total_alpha = sum(pref.alpha for pref in preferences)
        total_beta = sum(pref.beta for pref in preferences)
        total_feedback = total_alpha + total_beta - 2 * len(preferences)
        if total_feedback >= 5:
            return ResponseLength.MEDIUM

    if ctx.diary_word_count >= 400:
        return ResponseLength.LONG
    if ctx.diary_word_count <= 80:
        return ResponseLength.SHORT
    if ctx.emotion_intensity >= 0.8:
        return ResponseLength.SHORT
    if ctx.hour is not None and (ctx.hour >= 23 or ctx.hour < 5):
        return ResponseLength.SHORT
    return ResponseLength.MEDIUM


def infer_directness(preferences: list[StylePreferenceRecord]) -> float:
    """Infer directness from style success rates."""
    if not preferences:
        return DEFAULT_DIRECTNESS

    style_directness = {
        "empathetic": 0.3,
        "practical": 0.8,
        "philosophical": 0.4,
        "humorous": 0.5,
    }

    weighted_sum = 0.0
    weight_total = 0.0
    for pref in preferences:
        if pref.style not in style_directness:
            continue
        success_rate = pref.alpha / (pref.alpha + pref.beta)
        weighted_sum += success_rate * style_directness[pref.style]
        weight_total += success_rate

    if weight_total == 0:
        return DEFAULT_DIRECTNESS

    return round(min(1.0, max(0.0, weighted_sum / weight_total)), 2)


def build_dynamic_prompt_for_agent(
    store: StylePreferenceStore,
    user_id: str,
    agent_type: str,
    *,
    diary_word_count: int = 0,
    hour: int | None = None,
    emotion_intensity: float = 0.5,
) -> str:
    tuner = PromptTuner(store=store)
    return tuner.build_dynamic_prompt(
        user_id,
        agent_type,
        diary_word_count=diary_word_count,
        hour=hour,
        emotion_intensity=emotion_intensity,
    )


def get_default_preference() -> UserPreference:
    return UserPreference(
        response_length=DEFAULT_RESPONSE_LENGTH,
        style=DEFAULT_STYLE,
        directness=DEFAULT_DIRECTNESS,
    )


__all__ = [
    "DEFAULT_DIRECTNESS",
    "DEFAULT_RESPONSE_LENGTH",
    "DEFAULT_STYLE",
    "SUPPORTED_STYLES",
    "AgentType",
    "PromptTuner",
    "ResponseLength",
    "ResponseLengthContext",
    "UserPreference",
    "build_dynamic_prompt_for_agent",
    "get_default_preference",
    "infer_directness",
    "infer_response_length",
]
