"""Application configuration.

All sensitive secrets MUST be provided via environment variables or a ``.env``
file. The application fails fast at startup if a required secret is missing.

Since this is a single-user local desktop app, there is no Redis, no JWT, and
no multi-tenant infrastructure.  The database is SQLite stored under
``DATA_DIR``.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> str:
    if sys.platform == "win32":
        base = os.getenv("APPDATA", os.path.expanduser("~"))
    else:
        base = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return str(Path(base) / "night-diary")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "night-diary-v2"

    # ---- Paths ----
    data_dir: str = Field(default_factory=_default_data_dir)
    port: int = Field(default=8000, description="TCP port to listen on (--port)")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir}/night_diary.db"

    @property
    def chroma_persist_dir(self) -> str:
        return str(Path(self.data_dir) / "chroma_data")

    @property
    def models_dir(self) -> str:
        return str(Path(self.data_dir) / "models")

    @property
    def backups_dir(self) -> str:
        return str(Path(self.data_dir) / "backups")

    @property
    def logs_dir(self) -> str:
        return str(Path(self.data_dir) / "logs")

    # ---- Security ----
    model_key_secret: str = Field(
        default="",
        min_length=0,
        description="Fernet key for encrypting LLM API keys at rest",
    )

    # ---- LLM defaults (can be overridden per provider via ModelProvider table) ----
    llm_api_key: str = Field(default="", description="Default LLM API key")
    llm_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        description="Default LLM base URL",
    )
    llm_model: str = Field(default="deepseek-chat", description="Default LLM model name")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
