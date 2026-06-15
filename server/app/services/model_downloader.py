"""Download embedding / reranker weights into ``{data_dir}/models/`` on first run."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

ModelDownloadPhase = Literal["pending", "downloading", "ready", "error", "skipped"]

REQUIRED_MODELS: tuple[tuple[str, str], ...] = (
    ("embedding", "BAAI/bge-small-zh-v1.5"),
    ("reranker", "BAAI/bge-reranker-base"),
)


@dataclass(frozen=True)
class ModelTarget:
    key: str
    repo_id: str


@dataclass
class ModelDownloadItem:
    key: str
    repo_id: str
    status: ModelDownloadPhase = "pending"
    progress: float = 0.0
    error: str | None = None


@dataclass
class ModelDownloadSnapshot:
    items: list[ModelDownloadItem] = field(default_factory=list)
    overall_progress: float = 0.0
    all_ready: bool = False
    downloading: bool = False


def configure_hf_environment(settings: Settings) -> None:
    """Point HuggingFace caches at the app data directory (idempotent)."""
    models_dir = str(Path(settings.models_dir).resolve())
    os.environ.setdefault("HF_HOME", models_dir)
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", models_dir)
    if settings.hf_endpoint:
        os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)


def _ready_marker_path(settings: Settings, repo_id: str) -> Path:
    return Path(settings.models_dir) / ".ready" / repo_id.replace("/", "--")


def _is_ready(repo_id: str, settings: Settings) -> bool:
    if _ready_marker_path(settings, repo_id).is_file():
        return True
    try:
        from huggingface_hub import hf_hub_download

        hf_hub_download(
            repo_id=repo_id,
            filename="config.json",
            cache_dir=settings.models_dir,
            local_files_only=True,
        )
        marker = _ready_marker_path(settings, repo_id)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok", encoding="utf-8")
        return True
    except Exception:
        return False


def _mark_ready(settings: Settings, repo_id: str) -> None:
    marker = _ready_marker_path(settings, repo_id)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("ok", encoding="utf-8")


class ModelDownloadService:
    """Thread-safe coordinator for first-run model downloads."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._items: dict[str, ModelDownloadItem] = {
            key: ModelDownloadItem(key=key, repo_id=repo_id)
            for key, repo_id in REQUIRED_MODELS
        }

    def snapshot(self) -> ModelDownloadSnapshot:
        with self._lock:
            items = [
                ModelDownloadItem(
                    key=item.key,
                    repo_id=item.repo_id,
                    status=item.status,
                    progress=item.progress,
                    error=item.error,
                )
                for item in self._items.values()
            ]
        settings = self._settings
        all_ready = all(_is_ready(item.repo_id, settings) for item in items)
        if all_ready:
            for item in items:
                item.status = "ready"
                item.progress = 100.0

        overall = 0.0
        if items:
            overall = sum(item.progress for item in items) / len(items)

        downloading = any(item.status == "downloading" for item in items)
        return ModelDownloadSnapshot(
            items=items,
            overall_progress=round(overall, 1),
            all_ready=all_ready,
            downloading=downloading,
        )

    def start(self) -> bool:
        """Kick off background download when models are missing. Returns False if already running."""
        snap = self.snapshot()
        if snap.all_ready:
            return False

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            for key, repo_id in REQUIRED_MODELS:
                if _is_ready(repo_id, self._settings):
                    self._items[key].status = "ready"
                    self._items[key].progress = 100.0
                else:
                    self._items[key].status = "pending"
                    self._items[key].progress = 0.0
                    self._items[key].error = None

            self._thread = threading.Thread(target=self._run_downloads, name="model-download", daemon=True)
            self._thread.start()
            return True

    def _run_downloads(self) -> None:
        configure_hf_environment(self._settings)
        settings = self._settings
        Path(settings.models_dir).mkdir(parents=True, exist_ok=True)

        total = len(REQUIRED_MODELS)
        for index, (key, repo_id) in enumerate(REQUIRED_MODELS):
            if _is_ready(repo_id, settings):
                with self._lock:
                    self._items[key].status = "ready"
                    self._items[key].progress = 100.0
                continue

            with self._lock:
                self._items[key].status = "downloading"
                self._items[key].progress = 5.0
                self._items[key].error = None

            try:
                self._download_repo(repo_id, key, index, total)
                with self._lock:
                    self._items[key].status = "ready"
                    self._items[key].progress = 100.0
            except Exception as exc:
                logger.exception("Model download failed for %s", repo_id)
                with self._lock:
                    self._items[key].status = "error"
                    self._items[key].error = str(exc)

    def _download_repo(self, repo_id: str, key: str, model_index: int, model_count: int) -> None:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=repo_id,
            cache_dir=self._settings.models_dir,
            resume_download=True,
        )
        _mark_ready(self._settings, repo_id)
        progress = ((model_index + 1) / model_count) * 100.0
        with self._lock:
            self._items[key].progress = round(progress, 1)

    def apply_env(self) -> None:
        configure_hf_environment(self._settings)


_service: ModelDownloadService | None = None
_service_lock = threading.Lock()


def get_model_download_service(settings: Settings | None = None) -> ModelDownloadService:
    global _service
    with _service_lock:
        if _service is None:
            _service = ModelDownloadService(settings)
        return _service


def reset_model_download_service() -> None:
    """Test helper — drop the process-wide singleton."""
    global _service
    with _service_lock:
        _service = None
