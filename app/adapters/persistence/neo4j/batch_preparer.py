"""
Batch data preparation for Neo4j ingestion.

Pure functions that transform domain entities into Neo4j-ready dictionaries.
Extracted from CypherExecutor to separate data transformation from database execution.

CONNECTION DATA FLOW:
    1. YAML frontmatter → the ingestion preparer flattens ``connections`` to dotted
       keys on the entity dict (``connections.enables``; Neo4j stores no maps)
    2. HERE: the relationship keys are set aside, the rest is checked against the
       node's class and serialized as ``_node_props``, and the keys ride on the item
    3. BulkUpsertBackend: writes the node from ``_node_props``
    4. Cypher template: creates the graph edges via FOREACH + MERGE
    5. Result: edges exist in the graph; the keys are not node properties
"""

from __future__ import annotations

from typing import Any

from adapters.persistence.neo4j.neo4j_mapper import (
    UnstorableValueError,
    to_neo4j_patch,
    without_embedding_props,
)


def prepare_batch_items(
    entities: list[dict[str, Any]],  # boundary: prepared vault files, one dict each
    entity_class: type,
    rel_config: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[UnstorableValueError]]:  # boundary: batch items
    """
    Full pipeline: convert entities to Neo4j-ready dicts with connection handling.

    Steps:
        1. Drop the embedding writer's properties: they never ride in an entity payload.
        2. Set the relationship-config keys aside (the edge sources the Cypher template
           consumes), and serialize the rest with ``to_neo4j_patch`` against
           ``entity_class``, the class its node is read as. An entity holding a key
           that names no field of the class, or a value that read would refuse, is
           left out and returned among the refusals.
        3. Put the relationship keys back on the item; with ``rel_config``, each item
           also gets ``_node_props``, the item without them, for node storage.

    A file's connections arrive as dotted keys (``connections.enables``) already:
    the ingestion preparer flattens them (``core/services/ingestion/preparer.py``).

    Args:
        entities: Prepared entity dicts, one per file
        entity_class: The model class the entities' nodes are read as
        rel_config: Relationship configuration dict. Keys are connection field names
            (e.g. "connections.enables"), each an edge source, never a node property.

    Returns:
        The items ready for CypherExecutor.execute_batch(), and one refusal for each
        entity left out
    """
    connection_keys = set(rel_config or ())
    items = []
    refusals: list[UnstorableValueError] = []
    for entity in entities:
        # The bulk template is ``MERGE … ON MATCH SET n += props``: the embedding
        # writer's properties must never ride in an entity payload (a null under
        # ``+=`` removes the stored vector).
        authored = without_embedding_props(entity)
        edge_sources = {k: v for k, v in authored.items() if k in connection_keys}
        node_part = {k: v for k, v in authored.items() if k not in connection_keys}
        try:
            item = to_neo4j_patch(node_part, entity_class, uid=entity.get("uid"))
        except UnstorableValueError as refusal:
            refusals.append(refusal)
            continue
        if rel_config is None:
            items.append(item)
            continue
        # The template reads each edge source as ``coalesce(item.`key`, [])``; the node
        # is written from ``_node_props`` alone, so no edge source becomes a property.
        items.append({**item, **edge_sources, "_node_props": item})
    return items, refusals
