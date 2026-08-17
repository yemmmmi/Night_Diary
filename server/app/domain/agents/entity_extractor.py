"""Lightweight entity extractor — async sidecar for conversation turns.

Replaces the deleted KnowledgeExtractor with a simpler, focused implementation
that extracts entities (persons, places, topics) from user messages after each
conversation turn. Runs as a fire-and-forget background task so it never blocks
the reply.

Unlike the old KnowledgeExtractor:
- No separate LLM call (uses regex + simple NER patterns, zero tokens)
- Extracts only entities, not mood_score (already handled by EmotionEstimator)
- Writes to Neo4j entity graph (if available) for multi-hop relationship queries
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.infrastructure.task_queue import enqueue_task

logger = logging.getLogger(__name__)

# ── Entity patterns ──────────────────────────────────────────────────

# Person patterns (Chinese names, role references)
_PERSON_PATTERNS = [
    re.compile(r"([老小阿])([明华强伟红丽娟])"),  # 老王, 小李, 阿明
    re.compile(r"(妈妈|爸爸|老公|老婆|男友|女友|儿子|女儿|老板|同事|老师|朋友)"),
    re.compile(r"([\u4e00-\u9fa5]{2,3})(说|告诉|给|和|跟|与)"),  # X说/X告诉
]

# Place patterns
_PLACE_PATTERNS = [
    re.compile(r"(公司|学校|家里|医院|公园|超市|地铁|公交|车站|机场|酒店|餐厅|咖啡馆)"),
    re.compile(r"(北京|上海|广州|深圳|杭州|成都|武汉|西安|南京)"),
]

# Topic patterns (activity keywords)
_TOPIC_PATTERNS = [
    re.compile(r"(工作|加班|项目|会议|报告|考试|学习|健身|跑步|做饭|看书|看电影|旅行|购物)"),
    re.compile(r"(失眠|焦虑|压力|开心|难过|生气|紧张|放松|疲劳|兴奋)"),
]


@dataclass
class ExtractedEntity:
    """A single entity extracted from text."""

    name: str
    entity_type: str  # person / place / topic
    relation: str = ""
    sentiment: float = 0.0


def extract_entities(text: str) -> list[ExtractedEntity]:
    """Extract entities from text using regex patterns.

    Zero-token, rule-based extraction. Good enough for common Chinese
    conversational entities without an LLM call.
    """
    if not text or not text.strip():
        return []

    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()

    # Extract persons
    for pattern in _PERSON_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(0)
            key = (name, "person")
            if key not in seen and len(name) >= 2:
                seen.add(key)
                entities.append(ExtractedEntity(name=name, entity_type="person"))

    # Extract places
    for pattern in _PLACE_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(0)
            key = (name, "place")
            if key not in seen:
                seen.add(key)
                entities.append(ExtractedEntity(name=name, entity_type="place"))

    # Extract topics
    for pattern in _TOPIC_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(0)
            key = (name, "topic")
            if key not in seen:
                seen.add(key)
                entities.append(ExtractedEntity(name=name, entity_type="topic"))

    return entities


# ── LLM refinement layer ──────────────────────────────────────────────

_ENTITY_REFINE_PROMPT = """请从以下文本中提取实体，返回JSON格式。

文本：{content}

提取要求：
1. 识别人物（姓名、称谓如"妈妈"、"老王"）、地点、话题/活动
2. 为每个实体标注与说话者的关系（如"家人"、"同事"）
3. 标注情感倾向（-1.0 到 1.0，负面到正面）

返回JSON：
```json
{{
  "entities": [
    {{"name": "妈妈", "type": "person", "relation": "家人", "sentiment": 0.5}},
    {{"name": "公司", "type": "place", "relation": "", "sentiment": -0.3}}
  ]
}}
```"""


class HybridEntityExtractor:
    """Two-layer entity extraction: regex recall + LLM refine.

    Layer 1 (regex): fast, zero-token, high recall for common patterns.
    Layer 2 (LLM):   precise classification, relation labeling, sentiment.
    Only runs LLM layer when regex finds candidates (saves tokens on empty input).
    """

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def extract(self, text: str) -> list[ExtractedEntity]:
        """Extract entities via regex then optionally refine with LLM."""
        if not text or not text.strip():
            return []

        # Layer 1: regex recall
        regex_entities = extract_entities(text)
        if not regex_entities:
            return []

        # Layer 2: LLM refine (optional)
        if self._llm is None:
            return regex_entities

        try:
            refined = self._llm_refine(text, regex_entities)
            if refined:
                return refined
        except Exception as exc:
            logger.warning("HybridEntityExtractor LLM refine failed, using regex: %s", exc)

        return regex_entities

    def _llm_refine(
        self, text: str, regex_entities: list[ExtractedEntity]
    ) -> list[ExtractedEntity] | None:
        """Use LLM to refine/classify entities. Returns None on parse failure."""
        from app.shared.llm import message_text

        prompt = _ENTITY_REFINE_PROMPT.format(content=text[:800])
        response = self._llm.invoke(prompt)
        raw = message_text(response).strip()

        # Strip markdown fences
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)
        entities_data = data.get("entities", [])

        refined: list[ExtractedEntity] = []
        seen: set[tuple[str, str]] = set()
        for e in entities_data:
            name = str(e.get("name", "")).strip()
            etype = str(e.get("type", "topic")).strip()
            if not name or (name, etype) in seen:
                continue
            seen.add((name, etype))
            refined.append(
                ExtractedEntity(
                    name=name,
                    entity_type=etype,
                    relation=str(e.get("relation", "")),
                    sentiment=float(e.get("sentiment", 0.0)),
                )
            )

        # Merge: include regex entities not covered by LLM
        llm_names = {(e.name, e.entity_type) for e in refined}
        for re_e in regex_entities:
            if (re_e.name, re_e.entity_type) not in llm_names:
                refined.append(re_e)

        return refined


def _run_extraction_sync(
    session_factory: Any,
    user_id: str,
    source_id: str,
    text: str,
    source_label: str = "conversation",
) -> None:
    """Extract entities and write to Neo4j entity graph (synchronous body).

    Designed to be invoked via :func:`enqueue_task` — either on an RQ worker
    (when Redis is available and a dotted path is passed) or a daemon thread
    (fallback). Best-effort: never raises.

    Args:
        source_id: Identifier for the source (conversation_id or diary_id).
        source_label: "conversation" or "diary" — used in the source field.
    """
    try:
        # Try to get a light-tier LLM for hybrid extraction
        llm = None
        try:
            from app.config import get_settings
            from app.shared.llm_factory import LLMFactory

            factory = LLMFactory(get_settings())
            with session_factory() as db:
                llm = factory.create_for_tier(db, "light", user_id=user_id)
        except Exception:
            pass  # LLM optional — fall back to pure regex

        extractor = HybridEntityExtractor(llm=llm)
        entities = extractor.extract(text)
        if not entities:
            return

        # Write to Neo4j entity graph (if available, for multi-hop queries)
        from app.infrastructure.entity_graph import is_neo4j_available, write_entity

        if is_neo4j_available():
            entity_names = [(e.name, e.entity_type) for e in entities]
            for name, etype in entity_names:
                # Find co-occurring entities as related
                related = [(n, t, "co-occurs") for n, t in entity_names if n != name]
                write_entity(
                    user_id=user_id,
                    entity_name=name,
                    entity_type=etype,
                    source=f"{source_label}:{source_id}",
                    context=text[:100],
                    related_entities=related[:5],  # Limit to avoid explosion
                )
        else:
            logger.info(
                "Entity extraction: Neo4j unavailable, %d entities extracted but not persisted "
                "(source=%s:%s)",
                len(entities),
                source_label,
                source_id,
            )
            return

        logger.info(
            "Entity extraction: source=%s:%s entities=%d types=%s",
            source_label,
            source_id,
            len(entities),
            [e.entity_type for e in entities],
        )
    except Exception as exc:
        logger.warning("Entity extraction failed (best-effort): %s", exc)


def schedule_entity_extraction(
    container: Any,
    *,
    user_id: str,
    conversation_id: str,
    text: str,
    source_label: str = "conversation",
) -> None:
    """Schedule async entity extraction for a conversation turn or diary entry.

    Fire-and-forget: never blocks the reply, never raises.

    Robustness P2-6: the task is recorded as a durable ``jobs`` row before
    dispatch so a process crash/restart re-queues it instead of losing it.
    When job recording is unavailable (degraded container) it falls back to
    plain fire-and-forget dispatch.

    Args:
        conversation_id: Conversation ID (for chat) or diary ID string (for diary).
        source_label: "conversation" (default) or "diary" — controls source field.
    """
    if not text or not text.strip():
        return

    session_factory = getattr(container, "session_factory", None)
    if session_factory is None:
        return

    from app.services.job_service import enqueue_and_dispatch

    job = enqueue_and_dispatch(
        container,
        kind="entity_extraction",
        payload={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "text": text,
            "source_label": source_label,
        },
        user_id=user_id,
    )
    if job is not None:
        return

    # Fallback: plain fire-and-forget (job recording unavailable).

    enqueue_task(
        _run_extraction_sync,
        session_factory,
        user_id,
        conversation_id,
        text,
        source_label,
    )


__all__ = [
    "ExtractedEntity",
    "HybridEntityExtractor",
    "extract_entities",
    "schedule_entity_extraction",
]
