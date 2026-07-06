"""Entity graph store — Neo4j integration with SQLite fallback.

Stores entities (persons, places, topics) and their relationships as a graph
for multi-hop queries (e.g. "who does the user mention most when stressed?").

When Neo4j is available (NEO4J_URL set), entities are written to the graph
database for GraphRAG and complex relationship queries. When unavailable,
entities are stored in SQLite via the existing DomainKnowledgeStore —
simpler queries still work, but multi-hop graph traversals are not supported.

The graph schema:
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
    """Initialize Neo4j driver if NEO4J_URL is set."""
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
        logger.info("Neo4j connected: %s", _NEO4J_URL.split("@")[-1] if "@" in _NEO4J_URL else "(local)")
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
    """Write an entity and its relationships to the graph.

    Args:
        user_id: The user who mentioned this entity.
        entity_name: Name of the entity (e.g. "妈妈", "公司").
        entity_type: Type (person / place / topic).
        source: Source identifier (e.g. "diary:42", "conversation:abc").
        emotion: Emotion associated with this mention.
        context: Brief context of the mention.
        related_entities: List of (name, type, relation_type) tuples for
            entities mentioned alongside this one.
    """
    if _neo4j_available:
        _write_to_neo4j(
            user_id, entity_name, entity_type,
            source=source, emotion=emotion, context=context,
            related_entities=related_entities or [],
        )
    # SQLite fallback is handled by DomainKnowledgeStore in entity_extractor.py


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
    """Write entity and relationships to Neo4j."""
    if _neo4j_driver is None:
        return
    try:
        with _neo4j_driver.session() as session:
            # Create or merge User node
            session.run(
                "MERGE (u:User {user_id: $user_id})",
                user_id=user_id,
            )

            # Create or merge Entity node
            session.run(
                """
                MERGE (e:Entity {name: $name, user_id: $user_id})
                SET e.type = $entity_type
                """,
                name=entity_name,
                user_id=user_id,
                entity_type=entity_type,
            )

            # Create MENTIONS relationship
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

            # Create relationships to related entities
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
    """Query entities related to a given entity (multi-hop).

    Returns a list of dicts with name, type, relation_type, and depth.
    Only works with Neo4j; returns empty list on SQLite fallback.
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
    """Find entities most frequently mentioned with a given emotion.

    Example: "who does the user mention most when feeling low?"
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


# Initialize on import
_init_neo4j()


__all__ = [
    "is_neo4j_available",
    "query_entities_by_emotion",
    "query_related_entities",
    "write_entity",
]
