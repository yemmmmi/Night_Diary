"""Image upload API routes (B5).

``POST /api/v1/uploads/images``               — multipart upload, persists the
                                               file plus an ``image_assets`` row.
``GET  /api/v1/uploads/images/{asset_id}``    — asset metadata (user-scoped).
``GET  /api/v1/uploads/images/{asset_id}/file`` — raw file stream for previews.

Files are stored under ``uploads_dir/<user_id>/<uuid>.<ext>`` for multi-tenant
isolation; every DB query filters by ``user_id``.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.api.schemas import ImageAssetResponse
from app.config import get_settings
from app.infrastructure.models.image_asset import ImageAssetRow

router = APIRouter(prefix="/uploads", tags=["uploads"])

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
_EXT_BY_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _user_dir(user_id: str) -> Path:
    path = Path(get_settings().uploads_dir) / (user_id or "_shared")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_owned_asset(db: DbDep, asset_id: int, user_id: str) -> ImageAssetRow:
    row = db.scalar(
        select(ImageAssetRow).where(
            ImageAssetRow.id == asset_id, ImageAssetRow.user_id == user_id
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在")
    return row


@router.post(
    "/images",
    response_model=ImageAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    file: UploadFile,
    db: DbDep,
    user: CurrentUserDep,
) -> ImageAssetResponse:
    """Persist one uploaded image and return its asset metadata."""
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
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"文件过大，上限 {_MAX_SIZE_BYTES // (1024 * 1024)}MB",
        )

    user_id = str(user.id)
    stored_filename = f"{uuid.uuid4().hex}{_EXT_BY_MIME[file.content_type]}"
    (_user_dir(user_id) / stored_filename).write_bytes(data)

    row = ImageAssetRow(
        user_id=user_id,
        stored_filename=stored_filename,
        original_filename=file.filename or stored_filename,
        mime_type=file.content_type,
        size_bytes=len(data),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ImageAssetResponse.model_validate(row)


@router.get("/images/{asset_id}", response_model=ImageAssetResponse)
def get_image_asset(
    asset_id: int,
    db: DbDep,
    user: CurrentUserDep,
) -> ImageAssetResponse:
    """Return metadata for one uploaded image (user-scoped)."""
    row = _get_owned_asset(db, asset_id, str(user.id))
    return ImageAssetResponse.model_validate(row)


@router.get("/images/{asset_id}/file")
def get_image_file(
    asset_id: int,
    db: DbDep,
    user: CurrentUserDep,
) -> FileResponse:
    """Stream the original image file for client-side preview."""
    user_id = str(user.id)
    row = _get_owned_asset(db, asset_id, user_id)
    path = _user_dir(user_id) / row.stored_filename
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片文件丢失")
    return FileResponse(str(path), media_type=row.mime_type)