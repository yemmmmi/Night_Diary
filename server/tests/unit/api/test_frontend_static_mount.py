"""Desktop mode: the backend serves the built frontend at / (same-origin SPA)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_serves_index_and_keeps_health(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<!doctype html><title>night-diary</title>", encoding="utf-8"
    )
    settings = Settings(data_dir=str(tmp_path / "data"), frontend_dir=str(frontend))
    client = TestClient(create_app(settings))

    root = client.get("/")
    assert root.status_code == 200
    assert "night-diary" in root.text
    # 显式路由优先于根挂载
    assert client.get("/health").json() == {"status": "ok"}


def test_disabled_when_frontend_dir_empty(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"), frontend_dir="")
    client = TestClient(create_app(settings))
    assert client.get("/").status_code == 404