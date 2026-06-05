"""LLMFactory — creates tier-aware LLM clients from ModelProvider rows.

Full Fernet + user Settings integration lands in Phase C-3; this module provides
the service-layer wiring contract used by :class:`ExecutionPlanner`.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from app.config import Settings, get_settings
from app.infrastructure.models.model_provider import ModelProviderRow
from app.infrastructure.security import decrypt_api_key
from app.shared.errors import AIServiceUnavailableError
from app.shared.llm import LLMClient

logger = logging.getLogger(__name__)


class StubLLMClient:
    """Test/dev stub implementing :class:`LLMClient`."""

    def __init__(self, *, model: str = "stub", reply: str = "测试回应") -> None:
        self.model = model
        self._reply = reply
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> Any:
        self.prompts.append(prompt)

        class _Msg:
            content = self._reply
            response_metadata = {"token_usage": {"total_tokens": 10, "completion_tokens": 5}}

        return _Msg()

    async def ainvoke(self, prompt: str) -> Any:
        return self.invoke(prompt)


class LLMFactory:
    """Resolve LLM clients per tier from DB providers or environment defaults."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._chat_model_cls: Any | None = None

    def create_from_provider(self, provider: ModelProviderRow) -> LLMClient:
        if not provider.api_key_encrypted:
            raise AIServiceUnavailableError("模型未配置 API Key")
        api_key = decrypt_api_key(provider.api_key_encrypted, self._settings)
        return self._build_client(
            api_key=api_key,
            base_url=provider.base_url or self._settings.llm_base_url,
            model_name=provider.model_name,
        )

    def create_default(self) -> LLMClient:
        if not self._settings.llm_api_key:
            raise AIServiceUnavailableError(
                "AI 服务未配置：请在设置中添加模型，或设置环境变量 LLM_API_KEY"
            )
        return self._build_client(
            api_key=self._settings.llm_api_key,
            base_url=self._settings.llm_base_url,
            model_name=self._settings.llm_model,
        )

    def _build_client(self, *, api_key: str, base_url: str, model_name: str) -> LLMClient:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            logger.warning("langchain-openai unavailable; using StubLLMClient")
            return StubLLMClient(model=model_name)

        return cast(LLMClient, ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.7,
            max_tokens=300,
        ))
