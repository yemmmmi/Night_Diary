"""Resilient LLM wrappers — provider fallback and API-key pool rotation (D5).

Hermes routes a request across a primary provider, backup providers and a
rotating credential pool. 夜记 previously resolved a single client per tier
and only fell back when a provider was *missing* — never when it *failed at
call time*.

:class:`FallbackLLMClient` closes that gap: it wraps an ordered list of
attempts and, on any call-time exception, transparently retries the same
prompt against the next attempt.  A key pool is expressed as extra attempts
(one client per API key), so provider failover and credential rotation share
a single mechanism.

Design constraints (kept deliberately narrow):

* Only the *last* exception is re-raised, so existing error handling in the
  conversation loop / agents is unchanged when every attempt fails.
* ``bind_tools`` is exposed only when at least one attempt supports native
  function calling, so :func:`app.shared.tool_protocol.supports_native_tools`
  stays honest for stubbed clients.
* ``astream`` only falls back when nothing has been yielded yet — restarting a
  half-delivered stream on another provider would duplicate visible text.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from app.shared.errors import AIServiceUnavailableError
from app.shared.llm import LLMClient

logger = logging.getLogger(__name__)


def _client_model(client: Any) -> str:
    for attr in ("model", "model_name"):
        value = getattr(client, attr, None)
        if value:
            return str(value)
    return ""


class FallbackLLMClient:
    """Try an ordered list of LLM clients until one call succeeds."""

    def __init__(
        self,
        attempts: list[LLMClient],
        *,
        labels: list[str] | None = None,
    ) -> None:
        if not attempts:
            raise AIServiceUnavailableError("没有可用的模型尝试 (attempts 为空)")
        self._attempts = list(attempts)
        self._labels = list(labels) if labels else [f"attempt-{i}" for i in range(len(attempts))]
        if len(self._labels) != len(self._attempts):
            self._labels = [f"attempt-{i}" for i in range(len(self._attempts))]
        # ``model`` mirrors the primary attempt so callers that read ``.model``
        # (tracing, intent classifier, diagnostics) keep their existing value.
        self.model = _client_model(self._attempts[0])
        # Expose native tool binding only when some attempt supports it, keeping
        # ``supports_native_tools`` accurate for stub/non-tool clients.
        if any(callable(getattr(client, "bind_tools", None)) for client in self._attempts):
            self.bind_tools = self._bind_tools  # type: ignore[method-assign]

    @property
    def attempts(self) -> list[LLMClient]:
        return list(self._attempts)

    def invoke(self, prompt: str) -> Any:
        return self._run(lambda client: client.invoke(prompt), "invoke")

    async def ainvoke(self, prompt: str) -> Any:
        return await self._run_async(lambda client: client.ainvoke(prompt), "ainvoke")

    async def astream(self, prompt: str) -> AsyncGenerator[str, None]:
        last_exc: Exception | None = None
        for index, client in enumerate(self._attempts):
            yielded = False
            try:
                async for token in client.astream(prompt):
                    yielded = True
                    yield token
                return
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "LLM fallback: %s failed during astream (%s)", self._labels[index], exc
                )
                if yielded:
                    # Part of the reply was already streamed to the user; a
                    # restart would duplicate text, so surface the failure.
                    raise
        if last_exc is not None:
            raise last_exc

    def _run(self, call: Callable[[LLMClient], Any], op: str) -> Any:
        last_exc: Exception | None = None
        for index, client in enumerate(self._attempts):
            try:
                return call(client)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "LLM fallback: %s failed during %s (%s)", self._labels[index], op, exc
                )
        assert last_exc is not None
        raise last_exc

    async def _run_async(self, call: Callable[[LLMClient], Any], op: str) -> Any:
        last_exc: Exception | None = None
        for index, client in enumerate(self._attempts):
            try:
                return await call(client)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "LLM fallback: %s failed during %s (%s)", self._labels[index], op, exc
                )
        assert last_exc is not None
        raise last_exc

    def _bind_tools(self, tools: list[Any]) -> FallbackLLMClient:
        """Bind native tools on every attempt that supports it.

        Mirrors :class:`~app.shared.tracing_llm.TracingLLMClient`: raises when no
        attempt can bind, so the caller's ``except`` clause falls back to the
        text-tag protocol instead of silently dropping the tool hint.
        """
        bound: list[LLMClient] = []
        labels: list[str] = []
        for index, client in enumerate(self._attempts):
            binder = getattr(client, "bind_tools", None)
            if not callable(binder):
                continue
            try:
                bound.append(binder(tools))
                labels.append(self._labels[index])
            except Exception as exc:
                logger.warning(
                    "LLM fallback: bind_tools failed for %s (%s)", self._labels[index], exc
                )
        if not bound:
            raise AttributeError("没有可绑定工具的模型尝试")
        return FallbackLLMClient(bound, labels=labels)


__all__ = ["FallbackLLMClient"]