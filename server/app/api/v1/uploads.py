"""Image upload API routes.

``POST /api/v1/uploads/images``  — multipart upload, persists file + row,
                                 triggers async processing (fire-and-forget).
``GET  /api/v1/uploads/images/{asset_id}``     — processing result (user-scoped).
``GET  /api/v1/uploads/images/{asset_id}/file`` — raw file stream (thumbnail echo).

Files are stored under ``uploads_dir/<user_id>/<uuid>.<ext>`` for multi-tenant
isolation; DB rows carry ``user_id`` and every query filters by it.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
from app.api.schemas import ImageAssetResponse
from app.config import get_settings
from app.infrastructure.models.image_asset import ImageAssetRow
from app.services.image_service import schedule_image_processing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["uploads"])

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _user_dir(user_id: str) -> Path:
    cfg = get_settings()
    path = Path(cfg.uploads_dir) / (user_id or "_shared")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ext_for(mime_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(mime_type, ".bin")


@router.post(
    "/images",
    response_model=ImageAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    file: UploadFile,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> ImageAssetResponse:
    """Upload one image, persist it, and trigger async processing."""
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"仅支持 {', '.join(sorted(_ALLOWED_MIME))}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="空文件")
    if len(data) > _MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大（上限 {_MAX_SIZE_BYTES // (1024 * 1024)}MB）",
        )

    user_id = str(user.id)
    ext = _ext_for(file.content_type or "image/jpeg")
    stored_filename = f"{uuid.uuid4().hex}{ext}"
    target = _user_dir(user_id) / stored_filename
    target.write_bytes(data)

    row = ImageAssetRow(
        user_id=user_id,
        stored_filename=stored_filename,
        original_filename=file.filename or stored_filename,
        mime_type=file.content_type or "image/jpeg",
        size_bytes=len(data),
        content_type="unknown",
        processing_path="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Fire-and-forget async processing — never blocks the upload response.
    schedule_image_processing(container, user_id=user_id, asset_id=row.id)

    return ImageAssetResponse.model_validate(row)


@router.get("/images/{asset_id}", response_model=ImageAssetResponse)
def get_image_asset(
    asset_id: int,
    db: DbDep,
    user: CurrentUserDep,
) -> ImageAssetResponse:
    """Return the (possibly still-pending) processing result for an asset."""
    row = db.scalar(
        select(ImageAssetRow).where(
            ImageAssetRow.id == asset_id, ImageAssetRow.user_id == str(user.id)
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图像不存在")
    return ImageAssetResponse.model_validate(row)


@router.get("/images/{asset_id}/file")
def get_image_file(
    asset_id: int,
    db: DbDep,
    user: CurrentUserDep,
) -> FileResponse:
    """Stream the original image file for thumbnail echo in the client."""
    row = db.scalar(
        select(ImageAssetRow).where(
            ImageAssetRow.id == asset_id, ImageAssetRow.user_id == str(user.id)
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图像不存在")

    cfg = get_settings()
    path = Path(cfg.uploads_dir) / (str(user.id) or "_shared") / row.stored_filename
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图像文件丢失")
    return FileResponse(str(path), media_type=row.mime_type)
