"""LLMFactory — creates tier-aware LLM clients from ModelProvider rows."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, cast

from pydantic import SecretStr

from app.config import Settings, get_settings
from app.infrastructure.models.model_provider import ModelProviderRow
from app.infrastructure.security import decrypt_api_key
from app.shared.errors import AIServiceUnavailableError
from app.shared.llm import LLMClient
from app.shared.llm_resilience import FallbackLLMClient

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: Upper bound on the number of attempts in a provider fallback chain. Bounds
#: worst-case retry latency when several providers/keys are configured.
MAX_FALLBACK_ATTEMPTS = 4


def _provider_label(provider: ModelProviderRow) -> str:
    """Human-readable attempt label for fallback logging."""
    return f"{provider.model_name}@tier={provider.tier or 'default'}#id={provider.id}"


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

    async def astream(self, prompt: str) -> AsyncGenerator[str, None]:
        """Yield the stub reply as a single token (Protocol compliance)."""
        self.prompts.append(prompt)
        yield self._reply


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
        """Return an LLM client for ``tier``.

        Builds a provider-level fallback chain (D5): the tier's active provider
        first, then the ``default`` tier's provider as a backup, then the env
        default. A provider with a credential pool contributes one attempt per
        key, so key rotation shares the same mechanism.

        When ``user_id`` is provided, providers are scoped to that user; when it
        is omitted the backup provider must still belong to the primary
        provider's owner so tenants never leak into each other.
        """
        from app.services import model_service

        chain: list[ModelProviderRow] = []
        primary = model_service.get_active_provider_for_tier(db, tier, user_id=user_id)
        if primary is not None:
            chain.append(primary)
        if tier != "default":
            backup = model_service.get_active_provider_for_tier(db, "default", user_id=user_id)
            if (
                backup is not None
                and backup.id != (primary.id if primary else None)
                and (user_id is not None or primary is None or backup.user_id == primary.user_id)
            ):
                chain.append(backup)
        if chain:
            attempts, labels = self._attempts_for_providers(chain)
            if len(attempts) == 1:
                return attempts[0]
            if attempts:
                return FallbackLLMClient(attempts, labels=labels)
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

        Each tier's client is a :class:`FallbackLLMClient` spanning that tier's
        providers plus the ``default`` tier's providers of the *same owner*, so a
        primary-model outage degrades to a backup instead of an error (D5).

        When ``user_id`` is provided, only that user's providers are resolved.
        """
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

        by_tier: dict[str, list[ModelProviderRow]] = {}
        for provider in providers:
            by_tier.setdefault(provider.tier or "default", []).append(provider)

        clients: dict[str, LLMClient] = {}
        for tier, rows in by_tier.items():
            owner = rows[0].user_id
            ordered = [row for row in rows if row.user_id == owner]
            if tier != "default":
                ordered.extend(
                    row for row in by_tier.get("default", []) if row.user_id == owner
                )
            attempts, labels = self._attempts_for_providers(ordered, tracer=tracer)
            if not attempts:
                continue
            clients[tier] = (
                attempts[0] if len(attempts) == 1 else FallbackLLMClient(attempts, labels=labels)
            )
        return clients

    def _attempts_for_providers(
        self,
        providers: list[ModelProviderRow],
        *,
        tracer: Any | None = None,
    ) -> tuple[list[LLMClient], list[str]]:
        """Expand providers into an ordered attempt list (one client per key)."""
        attempts: list[LLMClient] = []
        labels: list[str] = []
        for provider in providers:
            if len(attempts) >= MAX_FALLBACK_ATTEMPTS:
                break
            try:
                provider_clients = self._attempts_from_provider(provider, tracer=tracer)
            except Exception as exc:
                logger.warning(
                    "Skip provider id=%s tier=%s: %s", provider.id, provider.tier, exc
                )
                continue
            provider_clients = provider_clients[: MAX_FALLBACK_ATTEMPTS - len(attempts)]
            attempts.extend(provider_clients)
            labels.extend([_provider_label(provider)] * len(provider_clients))
        return attempts, labels

    def _attempts_from_provider(
        self,
        provider: ModelProviderRow,
        *,
        tracer: Any | None = None,
    ) -> list[LLMClient]:
        """One client per API key in the provider's credential pool (D5)."""
        from app.services import model_service

        keys = model_service.provider_api_keys(provider, self._settings)
        if not keys:
            raise AIServiceUnavailableError("模型未配置 API Key")
        base_url = provider.base_url or self._settings.llm_base_url
        clients: list[LLMClient] = []
        for key in keys:
            inner = self._build_client(
                api_key=key, base_url=base_url, model_name=provider.model_name
            )
            if tracer is not None:
                from app.shared.tracing_llm import TracingLLMClient

                clients.append(
                    TracingLLMClient(
                        inner,
                        model=provider.model_name,
                        tier=provider.tier or "default",
                        tracer=tracer,
                    )
                )
            else:
                clients.append(inner)
        return clients

    def _build_client(self, *, api_key: str, base_url: str, model_name: str) -> LLMClient:
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
                # 300 would truncate structured JSON outputs (e.g. plan-skill
                # milestone nodes need ~700 tokens), silently breaking skills.
                max_completion_tokens=2048,
            ),
        )
