"""Shared HTTP LLM client for offline eval suites.

Extracted from ``generation/conftest.py`` so that tool_call / skill_call /
intent eval suites can reuse the same OpenAI-compatible httpx adapter without
duplicating ~120 lines of retry / auth / env-loading logic.

Usage::

    from tests.eval._http_llm import HttpLLM, REAL_MODE, MODEL_NAME

    llm = HttpLLM(temperature=0.0) if REAL_MODE else SomeStub()
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_RETRY_BASE_DELAY_S = 2.0

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def load_local_dotenv() -> None:
    """Load ``server/.env`` for offline eval (gitignored); does not override existing env."""
    if not _ENV_FILE.is_file():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


load_local_dotenv()

API_KEY = os.getenv("LLM_API_KEY", "")
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
REAL_MODE = bool(API_KEY)

_AUTH_ERROR_STATUSES = frozenset({401, 403})


def is_auth_error(exc: BaseException) -> bool:
    """Check if an exception is an auth/authorization failure (non-retryable)."""
    import httpx

    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in _AUTH_ERROR_STATUSES
    )


@dataclass
class Message:
    """Minimal LLM response wrapper (compatible with generation/conftest._Message)."""

    content: str
    response_metadata: dict[str, Any] = field(default_factory=dict)
    # Support tool_calls for native function calling responses
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def usage_block(prompt_tokens: int, completion_tokens: int) -> dict[str, Any]:
    """Build a standard usage block for response_metadata."""
    return {
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_cache_miss_tokens": prompt_tokens,
        }
    }


class HttpLLM:
    """Minimal OpenAI-compatible chat client (sync + async) over httpx.

    Supports both plain text responses and native function calling
    (when ``tools`` parameter is provided to invoke/ainvoke).
    """

    def __init__(
        self,
        *,
        temperature: float = 0.7,
        max_tokens: int = 600,
        json_mode: bool = False,
        max_retries: int = 5,
    ) -> None:
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._json_mode = json_mode
        self._max_retries = max_retries

    def _payload(
        self,
        prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if self._json_mode:
            body["response_format"] = {"type": "json_object"}
        if tools:
            body["tools"] = tools
        return body

    @staticmethod
    def _headers() -> dict[str, str]:
        return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> Message:
        msg = data["choices"][0]["message"]
        content = (msg.get("content") or msg.get("reasoning_content") or "").strip()
        usage = data.get("usage", {})
        # Extract tool_calls if present (native function calling)
        tool_calls_raw = msg.get("tool_calls") or []
        tool_calls: list[dict[str, Any]] = []
        for tc in tool_calls_raw:
            import json as _json

            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                args = _json.loads(args_str) if isinstance(args_str, str) else args_str
            except (ValueError, TypeError):
                args = {"raw": args_str}
            tool_calls.append({
                "name": tc.get("function", {}).get("name", ""),
                "args": args,
            })
        return Message(
            content=content,
            response_metadata=usage_block(
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
            ),
            tool_calls=tool_calls,
        )

    def _post_sync(
        self,
        prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> Message:
        import httpx

        url = f"{BASE_URL.rstrip('/')}/chat/completions"
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                with httpx.Client(timeout=120.0, trust_env=False) as client:
                    resp = client.post(
                        url, headers=self._headers(), json=self._payload(prompt, tools=tools)
                    )
                    resp.raise_for_status()
                    return self._parse_response(resp.json())
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                last_exc = exc
                if is_auth_error(exc) or attempt + 1 >= self._max_retries:
                    break
                time.sleep(_RETRY_BASE_DELAY_S * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def _post_async(
        self,
        prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> Message:
        import httpx

        url = f"{BASE_URL.rstrip('/')}/chat/completions"
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                    resp = await client.post(
                        url, headers=self._headers(), json=self._payload(prompt, tools=tools)
                    )
                    resp.raise_for_status()
                    return self._parse_response(resp.json())
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                last_exc = exc
                if is_auth_error(exc) or attempt + 1 >= self._max_retries:
                    break
                await asyncio.sleep(_RETRY_BASE_DELAY_S * (2**attempt))
        assert last_exc is not None
        raise last_exc

    def invoke(self, prompt: str, *, tools: list[dict[str, Any]] | None = None) -> Message:
        return self._post_sync(prompt, tools=tools)

    async def ainvoke(self, prompt: str, *, tools: list[dict[str, Any]] | None = None) -> Message:
        return await self._post_async(prompt, tools=tools)

    # Support bind_tools protocol for native function calling detection
    def bind_tools(self, tool_specs: list[Any]) -> "BoundToolLLM":
        """Return a wrapper that injects tool schemas into every invoke call."""
        return BoundToolLLM(self, tool_specs)


class BoundToolLLM:
    """Wrapper that injects tool schemas into every invoke/ainvoke call.

    Implements the same interface as LangChain's ``bind_tools`` return value,
    so ``supports_native_tools`` and ``extract_native_tool_calls`` from
    ``tool_protocol.py`` work transparently.
    """

    def __init__(self, inner: HttpLLM, tool_specs: list[Any]) -> None:
        self._inner = inner
        self._tool_specs = tool_specs

    def _to_openai_tools(self) -> list[dict[str, Any]]:
        """Convert ToolSpec objects to OpenAI function-calling tool format."""
        tools: list[dict[str, Any]] = []
        for spec in self._tool_specs:
            tools.append({
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            })
        return tools

    def invoke(self, prompt: str) -> Message:
        return self._inner.invoke(prompt, tools=self._to_openai_tools())

    async def ainvoke(self, prompt: str) -> Message:
        return await self._inner.ainvoke(prompt, tools=self._to_openai_tools())
