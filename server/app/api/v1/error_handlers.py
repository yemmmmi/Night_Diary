"""Map :class:`AppError` subclasses to HTTP responses."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorResponse
from app.shared.errors import AppError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=ErrorResponse(detail=exc.message).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Unify FastAPI's 422 validation errors to our ErrorResponse format."""
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = ".".join(str(p) for p in first.get("loc", []))
            detail = f"{loc}: {first.get('msg', '参数校验失败')}" if loc else first.get("msg", "参数校验失败")
        else:
            detail = "参数校验失败"
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(detail=detail).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all for non-AppError exceptions — return 500 without leaking stack traces."""
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(detail="内部错误, 请稍后重试").model_dump(),
        )
