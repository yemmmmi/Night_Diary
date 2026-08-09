"""Streaming reply event types and publishing helpers.

Defines the 8 SSE event types used by V3 P0 streaming, plus convenience
functions that publish events to the existing ``TraceEventBus`` keyed
by ``trace_id``.

Event flow:
    REPLY_START -> TEXT_DELTA* -> TEXT_END -> REPLY_END
                    |
            (PROTOCOL_BLOCK / STATE_UPDATED interleaved)

Safety override:
    RETRACT - replaces all prior TEXT_DELTA content with a safe template
"""

from __future__ import annotations

import logging
from typing import Any

from app.shared.trace_event_bus import get_event_bus

logger = logging.getLogger(__name__)


class StreamingEventType:
    """SSE event type names for streaming replies.

    These are string constants (not an enum) so they can be used directly
    as ``EventSource.addEventListener(name, ...)`` on the frontend without
    conversion.
    """

    REPLY_START = "reply_start"
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"
    REPLY_END = "reply_end"
    RETRACT = "retract"
    PROTOCOL_BLOCK = "protocol_block"
    STATE_UPDATED = "state_updated"
    TRACE_SPAN = "span_complete"  # backward-compatible with existing trace events


async def publish_reply_start(trace_id: str, *, intent: str = "", reply_id: str = "") -> None:
    """Publish a REPLY_START event marking the beginning of a streaming reply."""
    bus = get_event_bus()
    await bus.publish(
        trace_id,
        {
            "type": StreamingEventType.REPLY_START,
            "trace_id": trace_id,
            "intent": intent,
            "reply_id": reply_id,
        },
    )


async def publish_text_delta(trace_id: str, text: str) -> None:
    """Publish a TEXT_DELTA event carrying an incremental text chunk."""
    if not text:
        return
    bus = get_event_bus()
    await bus.publish(
        trace_id,
        {"type": StreamingEventType.TEXT_DELTA, "trace_id": trace_id, "text": text},
    )


async def publish_text_end(trace_id: str) -> None:
    """Publish a TEXT_END event marking the end of the current text block."""
    bus = get_event_bus()
    await bus.publish(trace_id, {"type": StreamingEventType.TEXT_END, "trace_id": trace_id})


async def publish_reply_end(
    trace_id: str,
    *,
    citations: list[dict[str, Any]] | None = None,
    usage: dict[str, int] | None = None,
    error: str | None = None,
) -> None:
    """Publish a REPLY_END event - the terminal event of a streaming reply.

    Frontend MUST always receive this event (even on error) so it can exit
    the ``streaming`` state. P1 will harden this with a terminating reply
    guarantee.
    """
    bus = get_event_bus()
    await bus.publish(
        trace_id,
        {
            "type": StreamingEventType.REPLY_END,
            "trace_id": trace_id,
            "citations": citations or [],
            "usage": usage or {},
            "error": error,
        },
    )


async def publish_retract(trace_id: str, *, reason: str, replacement: str) -> None:
    """Publish a RETRACT event - crisis safety override.

    Frontend replaces ALL accumulated reply text with ``replacement``
    (not append).
    """
    bus = get_event_bus()
    await bus.publish(
        trace_id,
        {
            "type": StreamingEventType.RETRACT,
            "trace_id": trace_id,
            "reason": reason,
            "replacement": replacement,
        },
    )


async def publish_protocol_block(
    trace_id: str,
    *,
    block_type: str,
    block_id: str,
    data: dict[str, Any],
) -> None:
    """Publish a PROTOCOL_BLOCK event carrying structured content.

    Protocol blocks are produced by skills (e.g. PlannerAgent's
    ``plan_proposal``). The frontend renders them as interactive cards
    within the streaming reply — distinct from plain TEXT_DELTA content.

    The ``block`` field nests block_type / block_id / data so the SSE
    event envelope stays flat (type / trace_id at top level, structured
    payload under ``block``).
    """
    bus = get_event_bus()
    await bus.publish(
        trace_id,
        {
            "type": StreamingEventType.PROTOCOL_BLOCK,
            "trace_id": trace_id,
            "block": {
                "block_type": block_type,
                "block_id": block_id,
                "data": data,
            },
        },
    )
