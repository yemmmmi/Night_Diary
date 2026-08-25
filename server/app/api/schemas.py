"""Pydantic request/response models for API v1."""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TagBrief(BaseModel):
    id: int
    name: str
    color: str

    model_config = {"from_attributes": True}


class DiaryCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    date: datetime.date | None = None
    weather: str | None = None


class DiaryUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    weather: str | None = None


class DiaryResponse(BaseModel):
    id: int
    content: str | None
    date: datetime.date | None
    weather: str | None
    reply: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class AnalysisResponse(BaseModel):
    id: int
    diary_id: int
    created_at: datetime.datetime
    token_cost: int | None
    cache_hit_tokens: int | None
    cache_miss_tokens: int | None
    output_tokens: int | None
    agent_mode: str | None
    execution_tier: str | None
    activated_agents: str | None
    reply: str | None = None
    model_name: str | None = None
    status_detail: str | None = None
    referenced_memory_count: int = 0

    model_config = {"from_attributes": True}


class AnalysisTriggerRequest(BaseModel):
    """Request body for triggering/regenerating an analysis with a replier style.

    ``replier_preset`` 对应前端预设风格 (warm/pragmatic/calm);
    ``replier_persona`` 为用户自定义人设文本 (非空时优先级高于 preset).
    两者都缺省时走后端默认 warm 风格, 保持向后兼容.
    """

    replier_preset: str | None = None
    replier_persona: str | None = None


class FeedbackCreateRequest(BaseModel):
    feedback_type: Literal["positive", "negative"]
    reason: str | None = None
    response_style: str = "empathetic"


class ConversationFeedbackCreateRequest(BaseModel):
    feedback_type: Literal["positive", "negative"]
    reason: str | None = None
    response_style: str = "empathetic"


class FeedbackResponse(BaseModel):
    id: int
    analysis_id: int | None = None
    diary_id: int | None = None
    conversation_id: str | None = None
    feedback_type: str
    response_style: str
    reason: str | None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class TagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    color: str = "#6B7280"


class TagResponse(BaseModel):
    id: int
    name: str
    color: str
    usage_count: int
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class ModelCreateRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=100)
    api_key: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    tier: str = "default"
    is_active: bool = False


class ModelUpdateRequest(BaseModel):
    model_name: str | None = Field(default=None, min_length=1, max_length=100)
    api_key: str | None = Field(default=None, min_length=1)
    base_url: str | None = None
    tier: str | None = None
    is_active: bool | None = None


class ModelTestConnectionRequest(BaseModel):
    model_name: str = Field(default="deepseek-chat", min_length=1, max_length=100)
    api_key: str = Field(min_length=1)
    base_url: str = Field(min_length=1)


class ModelTestConnectionResponse(BaseModel):
    ok: bool
    message: str | None = None


class ModelResponse(BaseModel):
    id: int
    model_name: str
    base_url: str | None
    tier: str
    is_active: bool
    is_default: bool
    has_api_key: bool


class ModelTierStatus(BaseModel):
    tier: str
    configured: bool
    model_name: str | None = None
    base_url: str | None = None
    is_active: bool = False


class ModelStatusResponse(BaseModel):
    tiers: list[ModelTierStatus]
    env_fallback: bool = False
    env_model_name: str | None = None


class StatsResponse(BaseModel):
    diary_count: int
    analysis_count: int
    total_token_cost: int
    llm_call_count: int
    total_tokens_in: int
    total_tokens_out: int


# ── Memory Card ────────────────────────────────────────────────────────


class CardCreateRequest(BaseModel):
    emotion: str = Field(min_length=1, max_length=32)
    emotions: list[str] = Field(default_factory=list)
    event_summary: str | None = Field(default=None)
    mood_score: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    card_type: Literal["quick", "standard", "guided"] = "standard"


class CardUpdateRequest(BaseModel):
    emotion: str | None = Field(default=None, min_length=1, max_length=32)
    emotions: list[str] | None = None
    event_summary: str | None = None
    mood_score: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)


class CardResponse(BaseModel):
    card_id: str
    emotion: str
    emotions: list[str] = Field(default_factory=list)
    event_summary: str | None
    mood_score: float
    tags: list[str]
    importance: float
    card_type: str
    diary_id: int | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class CardExpandRequest(BaseModel):
    """Expand a memory card into a full diary entry."""

    pass


# ── Weekly Report ──────────────────────────────────────────────────────


class SourceRef(BaseModel):
    """A citation backing a plan's motivation (diary/memory/episodic)."""

    type: str = Field(description="diary | episodic | memory")
    id: str | int
    date: str | None = None
    snippet: str | None = None


class PlanExecutionSummary(BaseModel):
    """Snapshot of one plan's execution within a weekly report period."""

    plan_id: str
    title: str
    done: int
    total: int
    source_refs: list[SourceRef] = Field(default_factory=list)


class WeekTaskItem(BaseModel):
    """Snapshot of one standalone task with in-week activity."""

    task_id: str
    title: str
    status: str  # pending | done | skipped
    source: str  # manual | agent
    due_date: datetime.date | None = None


class WeeklyReportResponse(BaseModel):
    id: int
    period_start: datetime.date
    period_end: datetime.date
    content: str
    diary_count: int
    card_count: int
    avg_mood: float | None
    token_cost: int | None
    execution_tier: str | None
    created_at: datetime.datetime
    plan_executions: list[PlanExecutionSummary] = Field(default_factory=list)
    week_tasks: list[WeekTaskItem] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ── Memory Library ─────────────────────────────────────────────────────


class EpisodicEntryResponse(BaseModel):
    entry_id: str
    event_summary: str
    emotion: str
    reply_insight: str
    importance: float
    timestamp: float
    diary_ids: list[str] = Field(default_factory=list)
    source: str = "diary"
    tags: list[str] = Field(default_factory=list)
    mood_score: float = 0.5
    emotions: list[str] = Field(default_factory=list)
    event_date: str | None = None


class EpisodicEntryUpdateRequest(BaseModel):
    event_summary: str | None = Field(default=None, min_length=1)
    emotion: str | None = Field(default=None, min_length=1, max_length=32)
    reply_insight: str | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)


class EmotionBaselineResponse(BaseModel):
    average_sentiment: float
    volatility: float
    dominant_emotion: str


class ImportantPersonResponse(BaseModel):
    name: str
    relation: str
    sentiment: float


class UserProfileResponse(BaseModel):
    personality_tags: list[str] = Field(default_factory=list)
    emotion_baseline: EmotionBaselineResponse
    important_people: list[ImportantPersonResponse] = Field(default_factory=list)
    recurring_topics: list[str] = Field(default_factory=list)
    preferred_response_style: str


class MemoryOverviewResponse(BaseModel):
    episodic_total: int
    episodic_from_cards: int
    episodic_from_diaries: int
    card_total: int
    profile_built: bool


class ModelDownloadItemResponse(BaseModel):
    key: str
    repo_id: str
    status: Literal["pending", "downloading", "ready", "error", "skipped"]
    progress: float = 0.0
    error: str | None = None


class ModelDownloadStatusResponse(BaseModel):
    items: list[ModelDownloadItemResponse]
    overall_progress: float = 0.0
    all_ready: bool = False
    downloading: bool = False


class ErrorResponse(BaseModel):
    detail: str


# ── Conversation (Chat) ──────────────────────────────────────────────


class ConversationResponse(BaseModel):
    id: str
    title: str
    active_replier_id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    retrieved_diary_ids: list[int] | None = None
    retrieved_memory_ids: list[str] | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    diary_ids: list[int] = Field(default_factory=list)
    auto_retrieve: bool = True

    @field_validator("diary_ids")
    @classmethod
    def validate_diary_ids(cls, value: list[int]) -> list[int]:
        if len(value) > 3:
            raise ValueError("最多引用 3 篇日记")
        return value


class SendMessageResponse(BaseModel):
    message: MessageResponse
    reply: MessageResponse


# ── Plan / Task (V3 P2) ──────────────────────────────────────────────


class TaskCreateRequest(BaseModel):
    title: str = Field(max_length=200)
    note: str | None = None
    due_date: str | None = Field(default=None, description="ISO date YYYY-MM-DD")
    plan_id: str | None = None
    source: str = Field(default="manual", pattern="^(manual|agent)$")
    created_from_conversation_id: str | None = None


class TaskResponse(BaseModel):
    id: str
    plan_id: str | None = None
    title: str
    note: str | None = None
    due_date: str | None = None
    status: str
    source: str
    completed_at: str | None = None
    created_at: str


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    note: str | None = None
    due_date: str | None = None
    status: str | None = Field(default=None, pattern="^(pending|done|skipped)$")


class PlanCreateRequest(BaseModel):
    title: str = Field(max_length=200)
    motivation: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    tasks: list[TaskCreateRequest] = Field(default_factory=list)
    source: str = Field(default="manual", pattern="^(manual|agent)$")
    created_from_conversation_id: str | None = None


class PlanResponse(BaseModel):
    id: str
    title: str
    motivation: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    status: str
    source: str
    tasks: list[TaskResponse] = Field(default_factory=list)
    created_at: str


class PlanUpdateRequest(BaseModel):
    title: str | None = None
    motivation: str | None = None
    status: str | None = Field(default=None, pattern="^(active|archived|completed)$")
