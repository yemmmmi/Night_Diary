"""LLMFactory — creates tier-aware LLM clients from ModelProvider rows."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from pydantic import SecretStr

from app.config import Settings, get_settings
from app.infrastructure.models.model_provider import ModelProviderRow
from app.infrastructure.security import decrypt_api_key
from app.shared.errors import AIServiceUnavailableError
from app.shared.llm import LLMClient, LLMPrompt, VisionCapableLLMClient

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class StubLLMClient:
    """Test/dev stub implementing :class:`LLMClient` and vision methods."""

    def __init__(self, *, model: str = "stub", reply: str = "测试回应") -> None:
        self.model = model
        self._reply = reply
        self.prompts: list[str] = []
        self.image_prompts: list[LLMPrompt] = []

    def invoke(self, prompt: str) -> Any:
        self.prompts.append(prompt)

        class _Msg:
            content = self._reply
            response_metadata = {"token_usage": {"total_tokens": 10, "completion_tokens": 5}}

        return _Msg()

    async def ainvoke(self, prompt: str) -> Any:
        return self.invoke(prompt)

    def invoke_with_images(self, prompt: LLMPrompt) -> Any:
        self.image_prompts.append(prompt)
        return self.invoke(prompt if isinstance(prompt, str) else "[image prompt]")

    async def ainvoke_with_images(self, prompt: LLMPrompt) -> Any:
        return self.invoke_with_images(prompt)


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

    def create_for_tier(self, db: Session, tier: str, *, user_id: str | None = None) -> LLMClient:
        """Return an LLM client for ``tier``, falling back to ``default`` then env.

        When ``user_id`` is provided, providers are scoped to that user.
        """
        from app.services import model_service

        provider = model_service.get_active_provider_for_tier(db, tier, user_id=user_id)
        if provider is None and tier != "default":
            provider = model_service.get_active_provider_for_tier(db, "default", user_id=user_id)
        if provider is not None:
            return self.create_from_provider(provider)
        return self.create_default()

    def resolve_by_tier(
        self,
        db: Session,
        *,
        tracer: Any | None = None,
        prefer_active: bool = True,
        user_id: str | None = None,
    ) -> dict[str, LLMClient]:
        """Build one client per tier from active ``model_providers`` rows.

        When ``user_id`` is provided, only that user's providers are resolved.
        """
        from app.shared.tracing_llm import TracingLLMClient

        query = db.query(ModelProviderRow).filter(ModelProviderRow.api_key_encrypted.isnot(None))
        if prefer_active:
            query = query.filter(ModelProviderRow.is_active.is_(True))
        if user_id is not None:
            query = query.filter(ModelProviderRow.user_id == user_id)
        providers = query.order_by(ModelProviderRow.id.asc()).all()

        if not providers and prefer_active:
            providers = (
                db.query(ModelProviderRow)
                .filter(ModelProviderRow.api_key_encrypted.isnot(None))
                .order_by(ModelProviderRow.id.asc())
                .all()
            )
            if providers:
                logger.warning(
                    "No active model providers; falling back to %d inactive row(s)",
                    len(providers),
                )

        clients: dict[str, LLMClient] = {}
        for provider in providers:
            tier = provider.tier or "default"
            if tier in clients:
                continue
            try:
                inner = self.create_from_provider(provider)
                model_name = provider.model_name
                if tracer is not None:
                    clients[tier] = TracingLLMClient(
                        inner,
                        model=model_name,
                        tier=tier,
                        tracer=tracer,
                    )
                else:
                    clients[tier] = inner
            except Exception as exc:
                logger.warning("Skip provider id=%s tier=%s: %s", provider.id, tier, exc)
        return clients

    def _build_client(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        max_completion_tokens: int = 300,
    ) -> LLMClient:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            logger.warning("langchain-openai unavailable; using StubLLMClient")
            return StubLLMClient(model=model_name)

        return cast(
            LLMClient,
            ChatOpenAI(
                api_key=SecretStr(api_key),
                base_url=base_url,
                model=model_name,
                temperature=0.7,
                max_completion_tokens=max_completion_tokens,
            ),
        )

    def create_vision_client(
        self, *, max_completion_tokens: int = 1024
    ) -> VisionCapableLLMClient:
        """Build a vision-capable client from environment defaults.

        Higher token budget than the default text client: VLM responses
        (description + transcribed text) are longer than 300 tokens.
        """
        if not self._settings.llm_api_key:
            raise AIServiceUnavailableError(
                "AI 服务未配置：请在设置中添加模型，或设置环境变量 LLM_API_KEY"
            )
        client = self._build_client(
            api_key=self._settings.llm_api_key,
            base_url=self._settings.llm_base_url,
            model_name=self._settings.llm_model,
            max_completion_tokens=max_completion_tokens,
        )
        return cast(VisionCapableLLMClient, client)

    def create_vision_from_provider(
        self, provider: ModelProviderRow, *, max_completion_tokens: int = 1024
    ) -> VisionCapableLLMClient:
        """Build a vision-capable client from a stored model provider row."""
        if not provider.api_key_encrypted:
            raise AIServiceUnavailableError("模型未配置 API Key")
        api_key = decrypt_api_key(provider.api_key_encrypted, self._settings)
        client = self._build_client(
            api_key=api_key,
            base_url=provider.base_url or self._settings.llm_base_url,
            model_name=provider.model_name,
            max_completion_tokens=max_completion_tokens,
        )
        return cast(VisionCapableLLMClient, client)
