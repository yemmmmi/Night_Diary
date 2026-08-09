"""LLMClient wrapper that records each call to an :class:`LLMCallTracer`."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from app.domain.agents.state import extract_token_usage
from app.shared.llm import LLMClient, message_text
from app.shared.pipeline_trace import get_trace
from app.shared.tracing import LLMCallRecord, LLMCallTracer, NoOpLLMCallTracer

logger = logging.getLogger(__name__)


class TracingLLMClient:
    """Structural wrapper: delegates to ``inner`` and persists ``LLMCallRecord`` rows."""

    def __init__(
        self,
        inner: LLMClient,
        *,
        model: str,
        tier: str = "",
        tracer: LLMCallTracer | None = None,
        agent_name: str = "execution_planner",
        call_type: str = "generate",
        decision_id: str = "",
    ) -> None:
        self._inner = inner
        self.model = model
        self.tier = tier
        self._tracer = tracer or NoOpLLMCallTracer()
        self._agent_name = agent_name
        self._call_type = call_type
        self._decision_id = decision_id

    def invoke(self, prompt: str) -> Any:
        started = time.perf_counter()
        error: str | None = None
        response: Any = None
        try:
            response = self._inner.invoke(prompt)
            return response
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            if response is not None or error is not None:
                self._record(prompt, response, started, error)

    async def ainvoke(self, prompt: str) -> Any:
        started = time.perf_counter()
        error: str | None = None
        response: Any = None
        try:
            response = await self._inner.ainvoke(prompt)
            return response
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            if response is not None or error is not None:
                # Run tracing in a thread to avoid blocking the event loop
                # with synchronous SQLite writes. Swallow tracing errors so
                # they never mask the original LLM result/exception.
                try:
                    await asyncio.to_thread(self._record, prompt, response, started, error)
                except Exception as trace_exc:
                    logger.warning("Tracing record failed (non-fatal): %s", trace_exc)

    async def astream(self, prompt: str) -> AsyncGenerator[str, None]:
        """Stream ``prompt`` completion, yielding text tokens.

        Delegates to ``inner.astream()`` if the inner model supports it.
        Tracing records the full response after streaming completes (the
        aggregated text), not per-token.
        """
        started = time.perf_counter()
        chunks: list[str] = []
        error: str | None = None
        try:
            async for chunk in self._inner.astream(prompt):
                chunks.append(chunk)
                yield chunk
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            if chunks or error is not None:
                full_text = "".join(chunks)
                try:
                    await asyncio.to_thread(
                        self._record_streaming, prompt, full_text, started, error
                    )
                except Exception as trace_exc:
                    logger.warning("Streaming tracing record failed (non-fatal): %s", trace_exc)

    def _record(self, prompt: str, response: Any, started: float, error: str | None) -> None:
        usage = extract_token_usage(response) if response is not None else {}
        text = message_text(response) if response is not None else ""
        trace = get_trace()
        trace_id = trace.trace_id if trace else ""
        self._tracer.record(
            LLMCallRecord(
                id=uuid.uuid4().hex,
                decision_id=self._decision_id,
                trace_id=trace_id,
                agent_name=self._agent_name,
                call_type=self._call_type,
                model=self.model,
                tier=self.tier,
                prompt=prompt[:2000],
                response=text[:2000],
                latency_ms=(time.perf_counter() - started) * 1000,
                tokens_in=usage.get("cache_miss_tokens", 0) + usage.get("cache_hit_tokens", 0),
                tokens_out=usage.get("output_tokens", 0),
                error=error,
            )
        )

    def _record_streaming(
        self, prompt: str, full_text: str, started: float, error: str | None
    ) -> None:
        """Record a streaming LLM call with estimated token usage."""

        class _Msg:
            def __init__(self, content: str) -> None:
                self.content = content
                # Estimate tokens (rough: ~3 chars/token for mixed CJK+Latin).
                # Better than zeros — usage stats have a reference value.
                est_prompt = max(1, len(prompt) // 3)
                est_completion = max(1, len(content) // 3)
                self.response_metadata = {
                    "token_usage": {
                        "prompt_tokens": est_prompt,
                        "completion_tokens": est_completion,
                        "total_tokens": est_prompt + est_completion,
                    }
                }

        self._record(prompt, _Msg(full_text), started, error)

    def bind_tools(self, tools: list[Any]) -> TracingLLMClient:
        """Delegate bind_tools to inner if supported, else raise.

        Returns a *new* TracingLLMClient wrapping the bound inner, so
        tracing continues to work on tool-calling invocations.
        """
        if not hasattr(self._inner, "bind_tools"):
            raise AttributeError(
                f"Inner LLM {type(self._inner).__name__} does not support bind_tools"
            )
        bound = self._inner.bind_tools(tools)
        return TracingLLMClient(
            bound,
            model=self.model,
            tier=self.tier,
            tracer=self._tracer,
            agent_name=self._agent_name,
            call_type=self._call_type + "+tools",
            decision_id=self._decision_id,
        )
