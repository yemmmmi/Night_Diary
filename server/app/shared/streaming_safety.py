"""StreamingSafetyGuard - three-layer crisis safety net for streaming replies.

Solves the fundamental tension between token-level streaming and post-hoc
crisis detection: if crisis content streams to the frontend token-by-token,
it cannot be "taken back."

Three layers, applied per-intent:

1. **Crisis intent -> non-streaming (hard block)**
   ``crisis_signal`` intent OR ``CrisisGuard.detect(user_input) == True``
   -> caller must use the non-streaming path entirely.

2. **First-segment buffering (emotional_vent / advice_seeking)**
   The first ``buffer_size`` characters are buffered server-side. After a
   fast rule-based check (zero LLM cost, reuses ``CrisisGuard`` keywords),
   the buffer is flushed to the frontend in one chunk, then subsequent
   tokens stream directly.

3. **Sliding-window review (all streaming paths, fallback)**
   During streaming, a sliding window of the last ``window_size`` characters
   is continuously checked. If crisis content appears mid-stream, a
   ``RETRACT`` event replaces the entire accumulated reply with a safe
   template.

Low-risk intents (``casual_chat``, ``retrospective_query``) bypass
buffering entirely - they stream token-by-token with zero safety overhead.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.shared.crisis_guard import CrisisGuard

logger = logging.getLogger(__name__)

#: Low-risk intents that stream directly without buffering.
_LOW_RISK_INTENTS = frozenset({"casual_chat", "retrospective_query"})


class StreamingSafetyGuard:
    """Three-layer crisis safety guard for streaming replies.

    Parameters
    ----------
    crisis_guard : CrisisGuard
        The shared crisis detector (reuses V2 keyword heuristic + emotion score).
    buffer_size : int
        Number of characters to buffer before first flush (defense line 2).
    window_size : int
        Sliding window size for mid-stream review (defense line 3).
    """

    def __init__(
        self,
        crisis_guard: CrisisGuard,
        buffer_size: int = 100,
        window_size: int = 120,
    ) -> None:
        self._crisis = crisis_guard
        self._buffer_size = buffer_size
        self._window_size = window_size

    def should_stream_directly(self, intent: str, user_input: str) -> bool:
        """Defense line 1: determine if pure streaming is safe.

        Returns ``True`` if the conversation may proceed with streaming,
        ``False`` if the caller MUST fall back to the non-streaming path.
        """
        if intent == "crisis_signal":
            return False
        return not self._crisis.detect(user_input)

    async def filter_stream(
        self,
        token_stream: AsyncGenerator[str, None],
        intent: str,
    ) -> AsyncGenerator[str | dict[str, Any], None]:
        """Defense lines 2 + 3: wrap a token stream with safety filtering.

        Yields:
            ``str`` - safe text tokens to forward to the frontend.
            ``{"retract": True, "replacement": str}`` - crisis detected,
                caller must emit RETRACT and stop.
        """
        # Low-risk intents: pass through directly
        if intent in _LOW_RISK_INTENTS:
            async for token in token_stream:
                yield token
            return

        # Emotional-sensitive intents: buffer + sliding window
        buffer = ""
        flushed = False
        window = ""

        async for token in token_stream:
            if not flushed:
                buffer += token
                if len(buffer) >= self._buffer_size:
                    if self._crisis.detect(buffer):
                        yield {
                            "retract": True,
                            "replacement": self._crisis.safe_response,
                        }
                        return
                    flushed = True
                    window = buffer
                    yield buffer
            else:
                window = (window + token)[-self._window_size :]
                if self._crisis.detect(window):
                    yield {
                        "retract": True,
                        "replacement": self._crisis.safe_response,
                    }
                    return
                yield token

        # Short reply (never reached buffer_size): final check
        if not flushed and buffer:
            if self._crisis.detect(buffer):
                yield {
                    "retract": True,
                    "replacement": self._crisis.safe_response,
                }
                return
            yield buffer
