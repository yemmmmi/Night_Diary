"""Pydantic request/response models for API v1."""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TagBrief(BaseModel):
    id: int
    name: str
    color: str

    model_config = {"from_attributes": True}


class DiaryCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    date: datetime.date | None = None
    weather: str | None = None
    tag_ids: list[int] = Field(default_factory=list)


class DiaryUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    weather: str | None = None
    tag_ids: list[int] | None = None


class DiaryResponse(BaseModel):
    id: int
    content: str | None
    date: datetime.date | None
    weather: str | None
    ai_ans: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    tags: list[TagBrief] = Field(default_factory=list)

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
    ai_ans: str | None = None
    model_name: str | None = None
    status_detail: str | None = None

    model_config = {"from_attributes": True}


class FeedbackCreateRequest(BaseModel):
    feedback_type: Literal["positive", "negative"]
    reason: str | None = None
    response_style: str = "empathetic"


class FeedbackResponse(BaseModel):
    id: int
    analysis_id: int
    diary_id: int
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
