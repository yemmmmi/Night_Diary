"""实体图谱存储 — Neo4j 集成，带 SQLite 回退。

将实体（人物、地点、主题）及其关系存储为图，
用于多跳查询（例如"用户压力大时最常提到谁？"）。

当 Neo4j 可用（设置了 NEO4J_URL）时，实体写入图数据库
以支持 GraphRAG 和复杂关系查询。当不可用时，实体通过
现有的 DomainKnowledgeStore 存储在 SQLite 中 —
简单查询仍可使用，但不支持多跳图遍历。

图模式：
    (:User {user_id}) -[:MENTIONS]-> (:Entity {name, type})
    (:Entity) -[:RELATED_TO {context}]-> (:Entity)
    (:Entity) -[:APPEARS_IN {source, emotion}]-> (:DiaryEntry|:Conversation)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_NEO4J_URL = os.getenv("NEO4J_URL", "")
_neo4j_driver = None
_neo4j_available = False


def _init_neo4j() -> None:
    """如果设置了 NEO4J_URL 则初始化 Neo4j 驱动。"""
    global _neo4j_driver, _neo4j_available, _NEO4J_URL
    if not _NEO4J_URL:
        return
    try:
        from neo4j import GraphDatabase

        from app.config import get_settings

        settings = get_settings()
        _neo4j_driver = GraphDatabase.driver(
            _NEO4J_URL,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        _neo4j_driver.verify_connectivity()
        _neo4j_available = True
        logger.info(
            "Neo4j connected: %s", _NEO4J_URL.split("@")[-1] if "@" in _NEO4J_URL else "(local)"
        )
    except ImportError:
        logger.debug("neo4j package not installed; using SQLite fallback for entity graph")
    except Exception as exc:
        logger.warning("Neo4j connection failed (%s); using SQLite fallback", exc)


def is_neo4j_available() -> bool:
    return _neo4j_available


def write_entity(
    user_id: str,
    entity_name: str,
    entity_type: str,
    *,
    source: str = "",
    emotion: str = "",
    context: str = "",
    related_entities: list[tuple[str, str, str]] | None = None,
) -> None:
    """将实体及其关系写入图。

    Args:
        user_id: 提及该实体的用户。
        entity_name: 实体名称（如 "妈妈"、"公司"）。
        entity_type: 类型（person / place / topic）。
        source: 来源标识符（如 "diary:42"、"conversation:abc"）。
        emotion: 与此次提及关联的情绪。
        context: 提及的简要上下文。
        related_entities: 同时提及的实体的
            (name, type, relation_type) 元组列表。
    """
    if _neo4j_available:
        _write_to_neo4j(
            user_id,
            entity_name,
            entity_type,
            source=source,
            emotion=emotion,
            context=context,
            related_entities=related_entities or [],
        )
    # SQLite 回退由 entity_extractor.py 中的 DomainKnowledgeStore 处理


def _write_to_neo4j(
    user_id: str,
    entity_name: str,
    entity_type: str,
    *,
    source: str,
    emotion: str,
    context: str,
    related_entities: list[tuple[str, str, str]],
) -> None:
    """将实体和关系写入 Neo4j。"""
    if _neo4j_driver is None:
        return
    try:
        with _neo4j_driver.session() as session:
            # 创建或合并 User 节点
            session.run(
                "MERGE (u:User {user_id: $user_id})",
                user_id=user_id,
            )

            # 创建或合并 Entity 节点
            session.run(
                """
                MERGE (e:Entity {name: $name, user_id: $user_id})
                SET e.type = $entity_type
                """,
                name=entity_name,
                user_id=user_id,
                entity_type=entity_type,
            )

            # 创建 MENTIONS 关系
            session.run(
                """
                MATCH (u:User {user_id: $user_id}), (e:Entity {name: $name, user_id: $user_id})
                MERGE (u)-[r:MENTIONS]->(e)
                SET r.source = $source, r.emotion = $emotion, r.context = $context,
                    r.last_mentioned = datetime()
                """,
                user_id=user_id,
                name=entity_name,
                source=source,
                emotion=emotion,
                context=context,
            )

            # 创建与相关实体的关系
            for rel_name, rel_type, relation_type in related_entities:
                session.run(
                    """
                    MERGE (e1:Entity {name: $name1, user_id: $user_id})
                    SET e1.type = $type1
                    MERGE (e2:Entity {name: $name2, user_id: $user_id})
                    SET e2.type = $type2
                    MERGE (e1)-[r:RELATED_TO {relation_type: $relation_type}]->(e2)
                    """,
                    user_id=user_id,
                    name1=entity_name,
                    type1=entity_type,
                    name2=rel_name,
                    type2=rel_type,
                    relation_type=relation_type,
                )
    except Exception as exc:
        logger.warning("Neo4j write failed (best-effort): %s", exc)


def query_related_entities(
    user_id: str,
    entity_name: str,
    *,
    max_depth: int = 2,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """查询与给定实体相关的实体（多跳）。

    返回包含 name、type、relation_type 和 depth 的字典列表。
    仅在 Neo4j 下可用；SQLite 回退时返回空列表。
    """
    if not _neo4j_available or _neo4j_driver is None:
        return []

    try:
        with _neo4j_driver.session() as session:
            result = session.run(
                """
                MATCH path = (e:Entity {name: $name, user_id: $user_id})
                              -[:RELATED_TO*1..$depth]-> (related:Entity)
                WITH related, relationships(path) as rels, length(path) as depth
                RETURN related.name as name, related.type as type,
                       [r in rels | r.relation_type] as relation_types,
                       depth
                ORDER BY depth ASC
                LIMIT $limit
                """,
                name=entity_name,
                user_id=user_id,
                depth=max_depth,
                limit=limit,
            )
            return [
                {
                    "name": record["name"],
                    "type": record["type"],
                    "relation_types": record["relation_types"],
                    "depth": record["depth"],
                }
                for record in result
            ]
    except Exception as exc:
        logger.warning("Neo4j query failed: %s", exc)
        return []


def query_entities_by_emotion(
    user_id: str,
    emotion: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """查找在给定情绪下最常被提及的实体。

    示例："用户情绪低落时最常提到谁？"
    """
    if not _neo4j_available or _neo4j_driver is None:
        return []

    try:
        with _neo4j_driver.session() as session:
            result = session.run(
                """
                MATCH (u:User {user_id: $user_id})-[r:MENTIONS]->(e:Entity)
                WHERE r.emotion = $emotion
                RETURN e.name as name, e.type as type, count(r) as mention_count
                ORDER BY mention_count DESC
                LIMIT $limit
                """,
                user_id=user_id,
                emotion=emotion,
                limit=limit,
            )
            return [
                {
                    "name": record["name"],
                    "type": record["type"],
                    "mention_count": record["mention_count"],
                }
                for record in result
            ]
    except Exception as exc:
        logger.warning("Neo4j query failed: %s", exc)
        return []


# 导入时初始化
_init_neo4j()


__all__ = [
    "is_neo4j_available",
    "query_entities_by_emotion",
    "query_related_entities",
    "write_entity",
]
