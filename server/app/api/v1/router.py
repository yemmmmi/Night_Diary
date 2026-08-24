"""Aggregate API v1 router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    analysis,
    auth,
    card,
    conversation,
    dev,
    diary,
    export,
    feedback,
    memory,
    mode,
    model_download,
    models,
    plan,
    stats,
    tags,
    weekly,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(diary.router)
api_router.include_router(card.router)
api_router.include_router(conversation.router)
api_router.include_router(analysis.router)
api_router.include_router(feedback.router)
api_router.include_router(models.router)
api_router.include_router(model_download.router)
api_router.include_router(stats.router)
api_router.include_router(tags.router)
api_router.include_router(weekly.router)
api_router.include_router(memory.router)
api_router.include_router(export.router)
api_router.include_router(dev.router)
api_router.include_router(plan.router)
api_router.include_router(plan.tasks_router)
api_router.include_router(mode.router)
