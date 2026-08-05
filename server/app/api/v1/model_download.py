"""API routes for first-run embedding / reranker model downloads."""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.schemas import ModelDownloadItemResponse, ModelDownloadStatusResponse
from app.services.model_downloader import get_model_download_service

router = APIRouter(prefix="/models/download", tags=["models"])


@router.get("/status", response_model=ModelDownloadStatusResponse)
def download_status() -> ModelDownloadStatusResponse:
    snap = get_model_download_service().snapshot()
    return ModelDownloadStatusResponse(
        items=[
            ModelDownloadItemResponse(
                key=item.key,
                repo_id=item.repo_id,
                status=item.status,
                progress=item.progress,
                error=item.error,
            )
            for item in snap.items
        ],
        overall_progress=snap.overall_progress,
        all_ready=snap.all_ready,
        downloading=snap.downloading,
    )


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
def start_download() -> JSONResponse:
    service = get_model_download_service()
    snap = service.snapshot()
    if snap.all_ready:
        return JSONResponse({"status": "ready"})
    started = service.start()
    body = {"status": "started" if started else "running"}
    return JSONResponse(body, status_code=status.HTTP_202_ACCEPTED)
