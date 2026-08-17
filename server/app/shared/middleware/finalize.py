"""FinalizeMiddleware — unified fire-and-forget episodic memory write-back.

P0-P6 review found near-duplicate write-back logic inlined in both scenes:

- Scene 1: ``analysis_service._sync_diary_to_memory`` (always writes).
- Scene 2: ``conversation_ai_service._maybe_persist_episodic`` (emotion gate
  + severe-signal audit trail).

Both are the same pattern — content → ``ContentNormalizer`` →
``UnifiedMemoryAtom`` → ``enqueue_task(persist_atom)`` — differing only in
the source label and the normalization entry point. This middleware
consolidates the pattern into one implementation; the legacy functions remain
for the non-streaming paths until those migrate.
"""

from __future__ import annotations

import logging
from typing import Any

from app.shared.middleware.base import MiddlewareBase, MiddlewareContext

logger = logging.getLogger(__name__)

#: Minimum emotion intensity (abs score) to trigger episodic write-back
#: (matches conversation_ai_service._EPISODIC_WRITE_THRESHOLD).
_EPISODIC_WRITE_THRESHOLD = 0.3


class FinalizeMiddleware(MiddlewareBase):
    """Persist an episodic entry after a reply completes (best-effort).

    Gate semantics (kept identical to the legacy implementations):

    - ``always_persist=True`` (diary scenario): always write.
    - Otherwise: write when ``abs(emotion score) >= 0.3`` **or** a severe
      signal is detected (crisis-level — always written for the safety audit
      trail).

    The actual write is dispatched fire-and-forget via ``enqueue_task``; the
    middleware never raises into the reply flow.
    """

    name = "finalize"

    def on_reply(self, ctx: MiddlewareContext) -> None:
        container = ctx.container
        if container is None or not ctx.reply_text:
            return
        try:
            from app.services.memory_gateway import MemoryGateway

            gw = MemoryGateway.from_container(container)
            if gw._episodic is None:  # memory degraded — skip silently
                return

            from app.shared.emotion_estimator import get_emotion_estimator

            estimator = get_emotion_estimator()
            score = estimator.score(ctx.content)
            if (
                not ctx.always_persist
                and abs(score) < _EPISODIC_WRITE_THRESHOLD
                and not estimator.has_severe_signal(ctx.content)
            ):
                return

            atom = self._build_atom(ctx, estimator, score)
            if atom is None:
                return

            from app.infrastructure.task_queue import enqueue_task

            enqueue_task(gw.persist_atom, atom)
            logger.info(
                "FinalizeMiddleware write-back dispatched: scenario=%s user_id=%s",
                ctx.scenario,
                ctx.user_id,
            )
        except Exception as exc:
            logger.warning("FinalizeMiddleware write-back failed (best-effort): %s", exc)

    def _build_atom(self, ctx: MiddlewareContext, estimator: Any, score: float) -> Any:
        """Build the ``UnifiedMemoryAtom`` for this run's scenario."""
        from app.services.normalizer import ContentNormalizer

        if ctx.scenario == "diary_reply":
            entry = ctx.extra.get("entry")
            if entry is None:
                logger.warning(
                    "FinalizeMiddleware diary write skipped: no entry in ctx.extra"
                )
                return None
            return ContentNormalizer.from_diary(
                entry, reply=ctx.reply_text, user_id=ctx.user_id
            )

        emotion_label = estimator.estimate(ctx.content).label
        return ContentNormalizer.from_conversation(
            ctx.content,
            reply_text=ctx.reply_text,
            conversation_id=ctx.conversation_id or "",
            user_id=ctx.user_id,
            emotion_label=emotion_label,
            emotion_score=score,
        )
