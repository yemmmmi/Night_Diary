"""Aggregate API v1 router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import analysis, card, diary, feedback, model_download, models, stats, tags

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(diary.router)
api_router.include_router(card.router)
api_router.include_router(analysis.router)
api_router.include_router(feedback.router)
api_router.include_router(tags.router)
api_router.include_router(models.router)
api_router.include_router(model_download.router)
api_router.include_router(stats.router)
