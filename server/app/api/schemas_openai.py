"""Pydantic models for the OpenAI-compatible facade (A5).

Only the subset of the OpenAI Chat Completions protocol that 夜记 can honor is
declared; unknown fields sent by clients are ignored (Pydantic's default). This
keeps the surface honest — a client can point at the backend and read replies,
but 夜记's own persona/retrieval/safety pipeline stays in charge.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OpenAIChatMessage(BaseModel):
    """One inbound chat message (``content`` may be a string or part list)."""

    role: str = "user"
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None


class OpenAIChatCompletionRequest(BaseModel):
    model: str = "night-diary"
    messages: list[OpenAIChatMessage] = Field(default_factory=list)
    stream: bool = False
    n: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    user: str | None = None
    #: 夜记 extension: route this request into an existing conversation
    #: (ownership verified). Omitted → the caller's dedicated API
    #: conversation is reused, preserving continuity across stateless calls.
    conversation_id: str | None = None


class OpenAIChatMessageOut(BaseModel):
    role: str = "assistant"
    content: str


class OpenAIChatChoice(BaseModel):
    index: int = 0
    message: OpenAIChatMessageOut
    finish_reason: str | None = None


class OpenAIUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OpenAIChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[OpenAIChatChoice]
    usage: OpenAIUsage


class OpenAIModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "night-diary"


class OpenAIModelList(BaseModel):
    object: str = "list"
    data: list[OpenAIModelCard]