"""Unified cross-domain connection fetcher.

Batch-fetches entity connections (outgoing or incoming) via a single
parameterized Cypher query. Replaces 6 near-identical `_fetch_{domain}_connections()`
functions that were duplicated across Activity Domain route files.

Usage:
    from core.utils.connection_fetcher import fetch_entity_connections, TASK_CONNECTION_CONFIG

    connections_map = await fetch_entity_connections(
        backend=service.core.backend,
        config=TASK_CONNECTION_CONFIG,
        entity_uids=uids,
    )
"""

from __future__ import annotations

from dataclasses import dataclass

from core.ports.base_protocols import QueryExecutor
from core.utils.logging import get_logger

logger = get_logger("skuel.utils.connection_fetcher")


@dataclass(frozen=True)
class ConnectionConfig:
    """Per-domain configuration for connection fetching."""

    config_lookup_label: str
    relationship_types: tuple[str, ...]
    direction: str = "outgoing"  # "outgoing" or "incoming"


# -- Per-domain configs -------------------------------------------------------

TASK_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label="Task",
    relationship_types=(
        "FULFILLS_GOAL",
        "REINFORCES_HABIT",
        "APPLIES_KNOWLEDGE",
        "PART_OF_PATH_STEP",
        "PART_OF_LEARNING_PATH",
        "INFORMED_BY_PRINCIPLE",
        "RELATED_TO",
    ),
)

GOAL_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label="Goal",
    direction="incoming",
    relationship_types=(
        "FULFILLS_GOAL",
        "SUPPORTS_GOAL",
        "CONTRIBUTES_TO_GOAL",
        "REINFORCES_GOAL",
        "APPLIES_KNOWLEDGE",
        "INFORMED_BY_GOAL",
        "RELATED_TO",
    ),
)

HABIT_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label="Habit",
    relationship_types=(
        "REINFORCES_GOAL",
        "APPLIES_KNOWLEDGE",
        "REINFORCED_BY_PRINCIPLE",
        "PART_OF_PATH_STEP",
        "PART_OF_LEARNING_PATH",
        "RELATED_TO",
    ),
)

EVENT_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label="Event",
    relationship_types=(
        "REINFORCES_HABIT",
        "MILESTONE_CELEBRATION_FOR_GOAL",
        "PART_OF_PATH_STEP",
        "PART_OF_LEARNING_PATH",
        "DEMONSTRATES_PRINCIPLE",
        "APPLIES_KNOWLEDGE",
        "RELATED_TO",
    ),
)

CHOICE_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label="Choice",
    relationship_types=(
        "INFORMS_GOAL_STRATEGY",
        "ENABLES_HABIT",
        "EXPRESSES_PRINCIPLE",
        "APPLIES_KNOWLEDGE",
        "RELATED_TO",
    ),
)

PRINCIPLE_CONNECTION_CONFIG = ConnectionConfig(
    config_lookup_label="Principle",
    direction="incoming",
    relationship_types=(
        "EXPRESSES_PRINCIPLE",
        "EMBODIES_PRINCIPLE",
        "ALIGNED_WITH_PRINCIPLE",
        "REINFORCED_BY_PRINCIPLE",
        "INFORMED_BY_PRINCIPLE",
        "DEMONSTRATES_PRINCIPLE",
        "RELATED_TO",
    ),
)


async def fetch_entity_connections(
    backend: QueryExecutor,
    config: ConnectionConfig,
    entity_uids: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Batch-fetch cross-domain connections for a list of entities.

    Returns a map of entity_uid -> list of connection dicts, each with keys:
    ``rel_type``, ``connected_uid``, ``title``, ``connected_type``.

    For outgoing domains (Task, Habit, Event, Choice) the connected entity is
    the target. For incoming/gravity-well domains (Goal, Principle) it is the
    source. The dict keys are unified regardless of direction.
    """
    if not entity_uids:
        return {}

    rel_list = list(config.relationship_types)

    if config.direction == "outgoing":
        query = f"""
        MATCH (n:Entity:{config.config_lookup_label})
        WHERE n.uid IN $uids
        OPTIONAL MATCH (n)-[r]->(other:Entity)
        WHERE type(r) IN $rel_types
        RETURN n.uid AS entity_uid,
               type(r) AS rel_type,
               other.uid AS connected_uid,
               other.title AS title,
               other.entity_type AS connected_type
        """
    else:
        query = f"""
        MATCH (n:Entity:{config.config_lookup_label})
        WHERE n.uid IN $uids
        OPTIONAL MATCH (other:Entity)-[r]->(n)
        WHERE type(r) IN $rel_types
        RETURN n.uid AS entity_uid,
               type(r) AS rel_type,
               other.uid AS connected_uid,
               other.title AS title,
               other.entity_type AS connected_type
        """

    try:
        result = await backend.execute_query(query, {"uids": entity_uids, "rel_types": rel_list})
    except Exception:  # safety-net: Neo4j query failure shouldn't break the page
        logger.warning("Failed to fetch %s connections", config.config_lookup_label, exc_info=True)
        return {}

    if result.is_error:
        return {}

    connections_map: dict[str, list[dict[str, str]]] = {}
    for record in result.value:
        entity_uid: str = record["entity_uid"]
        if record.get("rel_type") is None:
            continue
        if entity_uid not in connections_map:
            connections_map[entity_uid] = []
        connections_map[entity_uid].append(
            {
                "rel_type": record["rel_type"],
                "connected_uid": record.get("connected_uid", ""),
                "title": record.get("title", ""),
                "connected_type": record.get("connected_type", ""),
            }
        )
    return connections_map
