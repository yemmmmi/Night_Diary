"""Unit tests for error_handlers.py — PR-3: security hardening."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.v1.error_handlers import register_error_handlers
from app.shared.errors import AppError


class _Item(BaseModel):
    name: str
    value: int


def _create_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/raise-app-error")
    async def _raise_app_error() -> dict:
        raise AppError(message="自定义业务错误", http_status=404)

    @app.get("/raise-runtime-error")
    async def _raise_runtime_error() -> dict:
        raise RuntimeError("unexpected internal error")

    @app.post("/validate")
    async def _validate(item: _Item) -> dict:
        return {"name": item.name, "value": item.value}

    return app


def test_app_error_preserved() -> None:
    """AppError must return its own http_status and message."""
    client = TestClient(_create_app(), raise_server_exceptions=False)
    resp = client.get("/raise-app-error")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "自定义业务错误"}


def test_unhandled_exception_returns_500() -> None:
    """Non-AppError exceptions must return 500 with generic message (no stack trace)."""
    client = TestClient(_create_app(), raise_server_exceptions=False)
    resp = client.get("/raise-runtime-error")
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "内部错误, 请稍后重试"
    # Must not leak the original exception message
    assert "unexpected internal error" not in body["detail"]


def test_request_validation_error_format() -> None:
    """FastAPI 422 validation errors must be unified to ErrorResponse format."""
    client = TestClient(_create_app(), raise_server_exceptions=False)
    resp = client.post("/validate", json={"name": "test"})  # missing 'value'
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body
    assert "value" in body["detail"] or "missing" in body["detail"].lower()
