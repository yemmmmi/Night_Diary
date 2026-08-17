"""Tree-hole analyzer — scene-1 daily path: short reply + structured digest.

The scene-1 "tree-hole" model: users who want an emotional outlet get a
brief acknowledgment (1-3 sentences) instead of a long empathetic reply;
users who want a real conversation are directed to scene 2. The daily
reply is short, and the day's structured digest (see ``app/shared/digest``)
is the primary product — scene 2 consumes it without reading the full
diary.

Pipeline (one LLM call per diary):

1. **classify** — rule-layer intent (4 classes, zero LLM cost).
2. **crisis check** — delegated to the caller via :func:`detect_crisis`;
   crisis diaries never reach the LLM (safe template short-circuit).
3. **route** — rule signals decide ``basic`` vs ``complex`` digest template
   (loss-averse: uncertainty defaults to ``complex`` so semantics are
   harder to miss).
4. **single LLM call** — returns strict JSON with the short reply plus the
   digest fields; deterministic fields (emotion / mood / intent / tags)
   come from the estimator + classifier, not the LLM.
5. **fallback** — on LLM failure / unparseable output, degrade to an
   intent-based short template + rule digest (never raises).
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, cast

from app.domain.agents.intent_classifier import IntentClassifier
from app.domain.agents.types import IntentResult
from app.shared.crisis_guard import CrisisGuard, get_crisis_guard
from app.shared.digest import (
    CardDigest,
    DiaryDigest,
    DiaryDigestPart,
    DigestEntity,
    TemporalRef,
)
from app.shared.emotion_estimator import get_emotion_estimator
from app.shared.llm import LLMClient, message_text
from app.shared.tracing import LLMCallRecord, LLMCallTracer, NoOpLLMCallTracer

logger = logging.getLogger(__name__)

#: Short-reply length cap (Chinese chars) — the tree-hole reply is brief.
MAX_REPLY_CHARS = 40

#: Intents that signal complex emotion → complex digest template.
_COMPLEX_INTENTS = frozenset({"emotional_support", "retrospective_review"})
_COMPLEX_MIN_CHARS = 300
_COMPLEX_MIN_EMOTION_WORDS = 3
_COMPLEX_MIN_PARAGRAPHS = 4

#: Cross-day temporal keywords → complex signal + temporal_refs extraction.
#: Mentions of other days mean the diary is not a simple record of today.
_CROSS_DAY_KEYWORDS = (
    "昨天", "前天", "上周", "上个月", "去年", "前几天", "前段时间",
    "那天", "那时", "那次", "上次", "曾经", "以前",
    "明天", "后天", "下周", "下个月", "明年", "未来几天",
)

#: Intent-based short replies used as LLM-unavailable fallback (and the
#: fallback style mirrors the old EMPATHY_FALLBACKS voice).
_TREEHOLE_FALLBACK_REPLIES: dict[str, str] = {
    "pure_record": "记下了，今天也好好度过了。",
    "emotional_support": "嗯，抱抱你。今天辛苦了。",
    "retrospective_review": "嗯，记下了。慢慢来。",
    "habit_tracking": "坚持记录，真棒。",
}
_FALLBACK_REPLY = "记下了。"


@dataclass(slots=True)
class TreeHoleOutcome:
    """Result of a tree-hole run: short reply + the day digest."""

    reply: str
    digest: DiaryDigest
    token_cost: int
    source: str  # "llm" | "rule"
    log: str
    intent: str = ""
    confidence: float = 0.0


def detect_crisis(content: str, crisis_guard: CrisisGuard | None = None) -> bool:
    """Crisis short-circuit — crisis diaries never reach the LLM."""
    guard = crisis_guard or get_crisis_guard()
    try:
        return guard.detect(content)
    except Exception as exc:
        logger.warning("CrisisGuard detect failed (treated as non-crisis): %s", exc)
        return False


async def classify_intent(
    content: str,
    llm: LLMClient | None = None,
    tracer: LLMCallTracer | None = None,
) -> IntentResult:
    """Rule-layer intent classification (4 classes, zero LLM cost)."""
    return await IntentClassifier(
        llm=None,  # rule layer only — the tree-hole path spends its single
        # LLM call on the reply+digest extraction, not on classification.
        tracer=tracer or NoOpLLMCallTracer(),
    ).classify(content)


def _emotion_snapshot(content: str) -> tuple[str, float, float]:
    """(label, score, mood) from the deterministic EmotionEstimator."""
    estimator = get_emotion_estimator()
    score = estimator.score(content)
    estimate = estimator.estimate(content)
    label = "crisis" if score <= estimator.crisis_threshold else estimate.label
    mood = max(0.0, min(1.0, 0.5 + score * 0.5))
    return label, score, mood


def route_digest_type(content: str, intent: str) -> str:
    """Decide ``basic`` vs ``complex`` (loss-averse: uncertainty → complex).

    Any one of the following routes to ``complex``:
    - intent ∈ {emotional_support, retrospective_review}
    - content length ≥ 300 chars
    - ≥ 3 distinct emotion keywords
    - ≥ 4 paragraphs
    - a cross-day temporal keyword (昨天 / 下周 / ...) — a simple record of
      today should not reference other days.
    """
    if intent in _COMPLEX_INTENTS:
        return "complex"
    if len(content.strip()) >= _COMPLEX_MIN_CHARS:
        return "complex"
    if _count_emotion_words(content) >= _COMPLEX_MIN_EMOTION_WORDS:
        return "complex"
    if _paragraph_count(content) >= _COMPLEX_MIN_PARAGRAPHS:
        return "complex"
    if any(kw in content for kw in _CROSS_DAY_KEYWORDS):
        return "complex"
    return "basic"


def _count_emotion_words(content: str) -> int:
    """Count distinct general-negative/positive keywords present (cheap)."""
    estimator = get_emotion_estimator()
    estimate = estimator.estimate(content)
    return len(estimate.matched_severe) + len(estimate.matched_negative) + len(
        estimate.matched_positive
    )


def _paragraph_count(content: str) -> int:
    return max(1, len([p for p in re.split(r"\n+", content.strip()) if p.strip()]))


# ── Prompt ──────────────────────────────────────────────────────────────


_TREEHOLE_PROMPT = """你是「夜记」的树洞回应者。用户在日记里倒出了今天的心情。

只输出一个 JSON 对象，禁止输出任何解释、说明、markdown 代码块或其他文字。

日记内容：
{content}

JSON 对象格式（严格按此结构）：
{{"reply": "1-3句简短温暖回应(≤40字)", "summary": "一句话概括(20-60字)", "topics": ["话题"], "temporal_refs": [{{"direction": "past或future", "date_hint": "昨天/下周等日期提示", "summary": "非当天发生的事"}}], "key_events": ["当天发生的具体事件"], "emotional_shifts": ["情绪变化"], "relationships": [{{"name": "人物", "relation": "关系", "sentiment": 0.0}}], "conflicts": ["矛盾或冲突"], "concerns": ["担忧"]}}

字段规则：
- temporal_refs 只放非当天发生的事（过去=past，未来=future）；当天的事放 key_events
- 简单日记的复杂字段（key_events/emotional_shifts/conflicts/concerns 等）用空数组
- 不要编造日记里没有的内容"""

#: Retry prompt — terse, JSON-only. Used when the full prompt's reply fails to
#: parse (some fast LLMs occasionally explain instead of emitting JSON).
_TREEHOLE_STRICT_PROMPT = """只输出一个 JSON 对象，不要任何解释或代码块。
日记：{content}
JSON 结构：{{"reply": "1-3句温暖回应", "summary": "一句话摘要", "topics": ["话题"], "temporal_refs": [{{"direction": "past或future", "date_hint": "日期提示", "summary": "非当天事件"}}], "key_events": ["当天事件"], "emotional_shifts": ["情绪变化"], "relationships": [{{"name": "人物", "relation": "关系", "sentiment": 0.0}}], "conflicts": ["冲突"], "concerns": ["担忧"]}}"""


def _parse_treehole_json(text: str) -> dict[str, Any] | None:
    """Parse the tree-hole LLM's JSON reply, tolerating surrounding prose.

    Real LLMs (e.g. deepseek-v4-flash) sometimes wrap the JSON in
    explanation or markdown fences despite ``json_mode``. Strategy:
    1. strip markdown fences and try direct ``json.loads``;
    2. fall back to extracting the first balanced ``{...}`` object.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    extracted = _extract_first_json_object(text)
    if extracted is not None:
        return extracted

    logger.warning("Tree-hole LLM JSON parse failed: %s", text[:200])
    return None


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first balanced JSON object from arbitrary text.

    Walks characters tracking string literals and brace depth so a JSON
    object embedded in prose (or a stray trailing explanation) is recovered.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    parsed = json.loads(candidate)
                except (json.JSONDecodeError, ValueError, TypeError):
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


def _clean_reply(reply: str) -> str:
    reply = (reply or "").strip().replace("\n", " ")
    if len(reply) > MAX_REPLY_CHARS:
        reply = reply[:MAX_REPLY_CHARS].rstrip() + "…"
    return reply or _FALLBACK_REPLY


def _build_digest(
    *,
    digest_type: str,
    day: date,
    source: str,
    intent: str,
    confidence: float,
    emotion_label: str,
    emotion_score: float,
    mood: float,
    diary_tags: list[str],
    cards: list[CardDigest],
    data: dict[str, Any],
) -> DiaryDigest:
    """Assemble the DiaryDigest from deterministic fields + LLM extraction."""
    part = DiaryDigestPart(
        intent=intent,
        intent_confidence=round(confidence, 2),
        emotion=emotion_label,
        emotion_score=round(emotion_score, 2),
        mood=round(mood, 2),
        tags=[t for t in diary_tags if t],
        topics=[str(t) for t in data.get("topics", []) if t],
        summary=str(data.get("summary", "")).strip(),
        temporal_refs=[
            TemporalRef(
                direction=cast(
                    Literal["past", "future"],
                    str(r.get("direction", "past"))
                    if str(r.get("direction", "past")) in ("past", "future")
                    else "past",
                ),
                summary=str(r.get("summary", "")),
                date_hint=str(r.get("date_hint", "")),
            )
            for r in data.get("temporal_refs", [])
            if isinstance(r, dict)
        ],
        key_events=[str(e) for e in data.get("key_events", []) if e],
        emotional_shifts=[str(s) for s in data.get("emotional_shifts", []) if s],
        relationships=[
            DigestEntity(
                name=str(r.get("name", "")),
                relation=str(r.get("relation", "")),
                sentiment=float(r.get("sentiment", 0.0) or 0.0),
            )
            for r in data.get("relationships", [])
            if isinstance(r, dict) and r.get("name")
        ],
        conflicts=[str(c) for c in data.get("conflicts", []) if c],
        concerns=[str(c) for c in data.get("concerns", []) if c],
    )
    return DiaryDigest(
        digest_type=digest_type,  # type: ignore[arg-type]
        date=day,
        source=source,  # type: ignore[arg-type]
        cards=cards,
        diary=part,
    )


def _fallback_reply(intent: str, emotion_label: str) -> str:
    if emotion_label == "crisis":
        return "抱抱你，你的感受是真实的。需要的话，可以找信任的人聊聊。"
    return _TREEHOLE_FALLBACK_REPLIES.get(intent, _FALLBACK_REPLY)


def fallback_treehole(
    *,
    content: str,
    day: date,
    intent: str,
    confidence: float,
    diary_tags: list[str],
    cards: list[CardDigest] | None = None,
    emotion_label: str = "",
    emotion_score: float = 0.0,
    mood: float = 0.5,
) -> TreeHoleOutcome:
    """Rule-based fallback: intent-based short reply + rule digest (no LLM)."""
    label, score, mood_v = _emotion_snapshot(content)
    emotion_label = emotion_label or label
    emotion_score = emotion_score or score
    mood = mood or mood_v

    digest_type = route_digest_type(content, intent)
    summary = content.strip().replace("\n", " ")
    summary = summary[:80] + ("…" if len(summary) > 80 else "")

    data: dict[str, Any] = {
        "topics": [t for t in diary_tags if t][:5],
        "summary": summary or "",
        "temporal_refs": [],
        "key_events": [],
        "emotional_shifts": [],
        "relationships": [],
        "conflicts": [],
        "concerns": [],
    }
    digest = _build_digest(
        digest_type=digest_type,
        day=day,
        source="rule",
        intent=intent,
        confidence=confidence,
        emotion_label=emotion_label,
        emotion_score=emotion_score,
        mood=mood,
        diary_tags=diary_tags,
        cards=cards or [],
        data=data,
    )
    return TreeHoleOutcome(
        reply=_fallback_reply(intent, emotion_label),
        digest=digest,
        token_cost=0,
        source="rule",
        log="[Tree-hole] source=rule fallback",
        intent=intent,
        confidence=confidence,
    )


async def run_treehole(
    *,
    content: str,
    day: date,
    llm: LLMClient,
    tracer: LLMCallTracer | None = None,
    intent_result: IntentResult | None = None,
    diary_tags: list[str] | None = None,
    cards: list[CardDigest] | None = None,
    model: str = "",
) -> TreeHoleOutcome:
    """Single-LLM tree-hole run: short reply + digest extraction.

    Never raises: any LLM / parse failure degrades to
    :func:`fallback_treehole`.
    """
    tracer = tracer or NoOpLLMCallTracer()
    intent_result = intent_result or await classify_intent(content)
    intent = intent_result.intent_category
    confidence = float(intent_result.confidence)
    diary_tags = [t for t in (diary_tags or []) if t]

    label, score, mood = _emotion_snapshot(content)
    digest_type = route_digest_type(content, intent)

    prompt = _TREEHOLE_PROMPT.format(content=content[:1500])
    started = time.perf_counter()
    error: str | None = None
    text = ""
    try:
        response = await llm.ainvoke(prompt)
        text = message_text(response)
        # Parse-failure retry: some fast LLMs occasionally explain instead of
        # emitting JSON — one terse JSON-only retry materially reduces rule
        # fallbacks in production.
        data = _parse_treehole_json(text)
        if data is None:
            strict_prompt = _TREEHOLE_STRICT_PROMPT.format(content=content[:1500])
            response = await llm.ainvoke(strict_prompt)
            text = message_text(response)
    except Exception as exc:
        error = str(exc)
        logger.warning("Tree-hole LLM failed, falling back to rules: %s", exc)
    finally:
        tracer.record(
            LLMCallRecord(
                agent_name="treehole",
                call_type="treehole",
                model=model,
                tier="light",
                prompt=prompt,
                response=text,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=error,
            )
        )

    data = _parse_treehole_json(text) if not error else None
    if data is None:
        return fallback_treehole(
            content=content,
            day=day,
            intent=intent,
            confidence=confidence,
            diary_tags=diary_tags,
            cards=cards,
            emotion_label=label,
            emotion_score=score,
            mood=mood,
        )

    reply = _clean_reply(str(data.get("reply", "")))
    digest = _build_digest(
        digest_type=digest_type,
        day=day,
        source="llm",
        intent=intent,
        confidence=confidence,
        emotion_label=label,
        emotion_score=score,
        mood=mood,
        diary_tags=diary_tags,
        cards=cards or [],
        data=data,
    )
    # Loss-averse upgrade: rules are only a prior — if the LLM actually
    # extracted complex fields (events / conflicts / concerns / temporal
    # refs), the digest must render the rich block in scene 2.
    part = digest.diary
    if digest.digest_type == "basic" and (
        part.key_events
        or part.conflicts
        or part.concerns
        or part.relationships
        or part.emotional_shifts
        or part.temporal_refs
    ):
        digest.digest_type = "complex"
    return TreeHoleOutcome(
        reply=reply,
        digest=digest,
        token_cost=int(getattr(llm, "last_tokens_used", 0) or 0),
        source="llm",
        log=f"[Tree-hole] source=llm digest_type={digest_type}",
        intent=intent,
        confidence=confidence,
    )


__all__ = [
    "MAX_REPLY_CHARS",
    "TreeHoleOutcome",
    "classify_intent",
    "detect_crisis",
    "fallback_treehole",
    "route_digest_type",
    "run_treehole",
]
