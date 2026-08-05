"""轻量级实体提取器——对话轮次的异步 sidecar。

用更简单、更聚焦的实现替换已删除的 KnowledgeExtractor，在每个
对话轮次后从用户消息中提取实体（人物、地点、话题）。作为即发即忘的
后台任务运行，因此从不阻塞回复。

与旧的 KnowledgeExtractor 不同：
- 没有单独的 LLM 调用（使用正则 + 简单 NER 模式，零 token）
- 只提取实体，不提取 mood_score（已由 EmotionEstimator 处理）
- 写入 Neo4j 实体图（如果可用）以支持多跳关系查询
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.infrastructure.task_queue import enqueue_task

logger = logging.getLogger(__name__)

# ── 实体模式 ──────────────────────────────────────────────────

# 人物模式（中文名、称谓）
_PERSON_PATTERNS = [
    re.compile(r"([老小阿])([明华强伟红丽娟])"),  # 老王, 小李, 阿明
    re.compile(r"(妈妈|爸爸|老公|老婆|男友|女友|儿子|女儿|老板|同事|老师|朋友)"),
    re.compile(r"([\u4e00-\u9fa5]{2,3})(说|告诉|给|和|跟|与)"),  # X说/X告诉
]

# 地点模式
_PLACE_PATTERNS = [
    re.compile(r"(公司|学校|家里|医院|公园|超市|地铁|公交|车站|机场|酒店|餐厅|咖啡馆)"),
    re.compile(r"(北京|上海|广州|深圳|杭州|成都|武汉|西安|南京)"),
]

# 话题模式（活动关键词）
_TOPIC_PATTERNS = [
    re.compile(r"(工作|加班|项目|会议|报告|考试|学习|健身|跑步|做饭|看书|看电影|旅行|购物)"),
    re.compile(r"(失眠|焦虑|压力|开心|难过|生气|紧张|放松|疲劳|兴奋)"),
]


@dataclass
class ExtractedEntity:
    """从文本中提取的单个实体。"""

    name: str
    entity_type: str  # person / place / topic（人物 / 地点 / 话题）
    relation: str = ""
    sentiment: float = 0.0


def extract_entities(text: str) -> list[ExtractedEntity]:
    """使用正则模式从文本中提取实体。

    零 token、基于规则的提取。对于常见的中文
    对话实体，无需 LLM 调用即可满足。
    """
    if not text or not text.strip():
        return []

    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()

    # 提取人物
    for pattern in _PERSON_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(0)
            key = (name, "person")
            if key not in seen and len(name) >= 2:
                seen.add(key)
                entities.append(ExtractedEntity(name=name, entity_type="person"))

    # 提取地点
    for pattern in _PLACE_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(0)
            key = (name, "place")
            if key not in seen:
                seen.add(key)
                entities.append(ExtractedEntity(name=name, entity_type="place"))

    # 提取话题
    for pattern in _TOPIC_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(0)
            key = (name, "topic")
            if key not in seen:
                seen.add(key)
                entities.append(ExtractedEntity(name=name, entity_type="topic"))

    return entities


# ── LLM 精炼层 ──────────────────────────────────────────────

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
    """两层实体提取：正则召回 + LLM 精炼。

    第 1 层（正则）：快速、零 token，对常见模式有高召回率。
    第 2 层（LLM）：精确分类、关系标注、情感倾向。
    仅在正则找到候选时才运行 LLM 层（对空输入节省 token）。
    """

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def extract(self, text: str) -> list[ExtractedEntity]:
        """通过正则提取实体，然后可选地用 LLM 精炼。"""
        if not text or not text.strip():
            return []

        # 第 1 层：正则召回
        regex_entities = extract_entities(text)
        if not regex_entities:
            return []

        # 第 2 层：LLM 精炼（可选）
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
        """使用 LLM 精炼/分类实体。解析失败时返回 None。"""
        from app.shared.llm import message_text

        prompt = _ENTITY_REFINE_PROMPT.format(content=text[:800])
        response = self._llm.invoke(prompt)
        raw = message_text(response).strip()

        # 去除 markdown 代码围栏
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

        # 合并：包含 LLM 未覆盖的正则实体
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
    """提取实体并写入 Neo4j 实体图（同步主体）。

    设计为通过 :func:`enqueue_task` 调用——要么在 RQ worker 上
    （当 Redis 可用且传入了点分路径时），要么在守护线程上
    （回退）。尽力而为：从不抛出异常。

    Args:
        source_id: 来源标识符（conversation_id 或 diary_id）。
        source_label: "conversation" 或 "diary"——用于 source 字段。
    """
    try:
        # 尝试获取一个 light 层级 LLM 用于混合提取
        llm = None
        try:
            from app.config import get_settings
            from app.shared.llm_factory import LLMFactory

            factory = LLMFactory(get_settings())
            with session_factory() as db:
                llm = factory.create_for_tier(db, "light", user_id=user_id)
        except Exception:
            pass  # LLM 可选——回退到纯正则

        extractor = HybridEntityExtractor(llm=llm)
        entities = extractor.extract(text)
        if not entities:
            return

        # 写入 Neo4j 实体图（如果可用，用于多跳查询）
        from app.infrastructure.entity_graph import is_neo4j_available, write_entity

        if is_neo4j_available():
            entity_names = [(e.name, e.entity_type) for e in entities]
            for name, etype in entity_names:
                # 查找共现实体作为关联
                related = [(n, t, "co-occurs") for n, t in entity_names if n != name]
                write_entity(
                    user_id=user_id,
                    entity_name=name,
                    entity_type=etype,
                    source=f"{source_label}:{source_id}",
                    context=text[:100],
                    related_entities=related[:5],  # 限制数量以避免爆炸
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
    """为对话轮次或日记条目调度异步实体提取。

    即发即忘：从不阻塞回复，从不抛出异常。

    Args:
        conversation_id: 对话 ID（用于聊天）或日记 ID 字符串（用于日记）。
        source_label: "conversation"（默认）或 "diary"——控制 source 字段。
    """
    if not text or not text.strip():
        return

    session_factory = getattr(container, "session_factory", None)
    if session_factory is None:
        return

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
