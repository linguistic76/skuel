"""
Batch data preparation for Neo4j ingestion.

Pure functions that transform domain entities into Neo4j-ready dictionaries.
Extracted from CypherExecutor to separate data transformation from database execution.

CONNECTION DATA FLOW:
    1. YAML frontmatter → the ingestion preparer flattens ``connections`` to dotted
       keys on the entity dict (``connections.requires``; Neo4j stores no maps)
    2. HERE: the relationship keys are kept on the item and filtered off ``_node_props``
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
        1. Serialize each entity with ``to_neo4j_patch`` against ``entity_class``, the
           class its node is read as. An entity holding a value that read
           would refuse is left out and returned among the refusals.
        2. If rel_config provided, create _node_props with connection keys filtered out

    A file's connections arrive as dotted keys (``connections.requires``) already:
    the ingestion preparer flattens them (``core/services/ingestion/preparer.py``).

    Args:
        entities: Prepared entity dicts, one per file
        entity_class: The model class the entities' nodes are read as
        rel_config: Relationship configuration dict. Keys are connection field names
            (e.g. "connections.requires"). When provided, each item gets a _node_props
            dict with connection keys removed for clean node storage.

    Returns:
        The items ready for CypherExecutor.execute_batch(), and one refusal for each
        entity left out
    """
    items = []
    refusals: list[UnstorableValueError] = []
    for entity in entities:
        # The bulk template is ``MERGE … ON MATCH SET n += props``: the embedding
        # writer's properties must never ride in an entity payload (a null under
        # ``+=`` removes the stored vector).
        try:
            item = without_embedding_props(
                to_neo4j_patch(entity, entity_class, uid=entity.get("uid"))
            )
        except UnstorableValueError as refusal:
            refusals.append(refusal)
            continue
        # to_neo4j_patch drops RELATIONSHIP_SKIP_FIELDS (graph-native: edges, not
        # node properties) — but the registry's yaml_field_path keys in rel_config
        # are exactly the edge SOURCES the Cypher template consumes. Restore any
        # the mapper stripped (e.g. exercise_uids, learning_path_uids) so edges
        # get created; the _node_props filter below still keeps them off the node.
        if rel_config is not None:
            for key in rel_config:
                if key not in item and entity.get(key):
                    item[key] = entity[key]
        items.append(item)

    if rel_config is not None:
        connection_keys = set(rel_config.keys())
        filtered_items = []
        for item_dict in items:
            props = {k: v for k, v in item_dict.items() if k not in connection_keys}
            filtered_item = {
                **item_dict,  # Keep connections for FOREACH clauses
                "_node_props": props,  # Filtered properties for node storage
            }
            filtered_items.append(filtered_item)
        return filtered_items, refusals

    return items, refusals
