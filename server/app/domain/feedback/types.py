"""风格反馈与提示词调优的领域类型。"""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field


class ResponseStyle(StrEnum):
    EMPATHETIC = "empathetic"
    PRACTICAL = "practical"
    PHILOSOPHICAL = "philosophical"
    HUMOROUS = "humorous"


STYLES: tuple[str, ...] = tuple(style.value for style in ResponseStyle)
DEFAULT_STYLE = ResponseStyle.EMPATHETIC.value


class ResponseLength(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


DEFAULT_RESPONSE_LENGTH = ResponseLength.MEDIUM


class AgentType(StrEnum):
    EMPATHY = "empathy"
    INSIGHT = "insight"


DEFAULT_DIRECTNESS = 0.5


class StylePreferenceRecord(BaseModel):
    """单一回应风格的 Beta 分布参数。"""

    style: str
    alpha: float = 1.0
    beta: float = 1.0
    updated_at: float = Field(default_factory=time.time)


class UserPreference(BaseModel):
    response_length: ResponseLength = DEFAULT_RESPONSE_LENGTH
    style: str = DEFAULT_STYLE
    directness: float = DEFAULT_DIRECTNESS


class StylePreferenceStore(Protocol):
    """汤普森采样风格偏好的持久化端口。"""

    def get_preferences(self, user_id: str) -> list[StylePreferenceRecord]: ...

    def ensure_preferences(
        self, user_id: str, styles: list[str]
    ) -> list[StylePreferenceRecord]: ...

    def update_preference(self, user_id: str, style: str, *, alpha: float, beta: float) -> None: ...
