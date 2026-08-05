"""三层记忆系统的领域类型。"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict

from pydantic import BaseModel, Field, model_validator


class EpisodicEntry(BaseModel):
    """从一次日记分析轮次中派生出的单条情景记忆项。

    扩展了结构化字段（tags、mood_score、emotions、event_date），
    以便长期记忆提升器能用它们进行重复主题检测，而非使用原始文本匹配。

    向后兼容：旧载荷存储的是 ``event`` 而非 ``event_summary``，且省略了
    ``reply_insight``。一个 ``model_validator`` 会映射遗留键名，
    以便对旧数据的反序列化永不失败。
    """

    event_summary: str
    emotion: str
    reply_insight: str
    source: str = "diary"
    timestamp: float
    diary_ids: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    entry_id: str = ""
    # ── 结构化字段（P2-2 UnifiedMemoryAtom） ──
    tags: list[str] = Field(default_factory=list)
    mood_score: float = Field(default=0.5, ge=0.0, le=1.0)
    emotions: list[str] = Field(default_factory=list)
    event_date: str | None = None  # ISO 日期字符串（YYYY-MM-DD）

    @model_validator(mode="before")
    @classmethod
    def _compat_legacy_fields(cls, data: Any) -> Any:
        """映射遗留字段名，以便旧 JSON 载荷仍能反序列化。

        - ``event`` → ``event_summary``（在 P2-2 中重命名）
        - ``reply_insight`` 缺失时默认为 ``""``（在 Phase 2 中新增）
        - ``insight`` → ``reply_insight``（非常旧的名字）
        """
        if isinstance(data, dict):
            # event → event_summary
            if "event_summary" not in data and "event" in data:
                data["event_summary"] = data.pop("event")
            # reply_insight 默认值
            if "reply_insight" not in data:
                data["reply_insight"] = data.get("insight", "")
        return data


class EmotionBaseline(BaseModel):
    average_sentiment: float = 0.0
    volatility: float = 0.0
    dominant_emotion: str = "neutral"


class ImportantPerson(BaseModel):
    name: str
    relation: str
    sentiment: float = 0.0


class UserProfile(BaseModel):
    """以 JSON 持久化的长期用户画像。"""

    personality_tags: list[str] = Field(default_factory=list)
    emotion_baseline: EmotionBaseline = Field(default_factory=EmotionBaseline)
    important_people: list[ImportantPerson] = Field(default_factory=list)
    recurring_topics: list[str] = Field(default_factory=list)
    preferred_response_style: str = "empathetic"


class WorkingContext(TypedDict, total=False):
    """单次日记分析的会话级工作记忆状态。"""

    diary_id: str
    diary_content: str
    user_profile: dict[str, Any]
    episodic_context: list[dict[str, Any]]
    long_term_profile: dict[str, Any]
    retrieval_context: str
    empathy_response: str
    insight_response: str
    compressed_history: str
    final_response: str
    turn: int
    total_tokens_used: int


class EpisodicMemoryStore(Protocol):
    """情景记忆条目的持久化端口。"""

    def load_entries(self, user_id: str) -> list[EpisodicEntry]: ...

    def upsert_entry(self, user_id: str, entry: EpisodicEntry) -> None: ...

    def delete_entries(self, user_id: str, entry_ids: list[str]) -> None: ...


class LongTermProfileStore(Protocol):
    """长期用户画像的持久化端口。"""

    def get_profile(self, user_id: str) -> UserProfile | None: ...

    def save_profile(self, user_id: str, profile: UserProfile) -> None: ...
