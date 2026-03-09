"""
Batch data preparation for Neo4j ingestion.

Pure functions that transform domain entities into Neo4j-ready dictionaries.
Extracted from CypherExecutor to separate data transformation from database execution.

CONNECTION DATA FLOW:
    1. YAML frontmatter → MarkdownSyncService stores in metadata._connections
    2. HERE: Extract and flatten to dotted keys (Neo4j can't store nested maps)
    3. BulkIngestionEngine: Uses filtered _node_props to exclude from node storage
    4. Cypher template: Creates graph edges via FOREACH + MERGE
    5. Result: Edges exist in graph, properties don't exist in nodes
"""

from __future__ import annotations

from typing import Any

from core.utils.neo4j_mapper import to_neo4j_node


def flatten_entity_connections(entity: Any, item: dict[str, Any]) -> dict[str, Any]:
    """
    Extract metadata._connections and flatten to dotted keys.

    Neo4j properties cannot store nested dictionaries, but CAN use them
    in Cypher queries. By flattening {"requires": ["ku:A"]} to
    {"connections.requires": ["ku:A"]}, we make it accessible in Cypher
    via backtick escaping: item.`connections.requires`

    Args:
        entity: Domain entity with optional metadata attribute
        item: Neo4j node dict (from to_neo4j_node)

    Returns:
        The item dict with flattened connection keys added (mutated in place)
    """
    metadata = getattr(entity, "metadata", None)
    if isinstance(metadata, dict):
        connections = metadata.get("_connections")
        if connections and isinstance(connections, dict):
            for key, value in connections.items():
                if value:  # Only add non-empty lists
                    item[f"connections.{key}"] = value
    return item


def prepare_batch_items(
    entities: list[Any],
    rel_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Full pipeline: convert entities to Neo4j-ready dicts with connection handling.

    Steps:
        1. Convert each entity via to_neo4j_node()
        2. Flatten metadata._connections to dotted keys
        3. If rel_config provided, create _node_props with connection keys filtered out

    Args:
        entities: Domain entities to prepare
        rel_config: Relationship configuration dict. Keys are connection field names
            (e.g. "connections.requires"). When provided, each item gets a _node_props
            dict with connection keys removed for clean node storage.

    Returns:
        List of dicts ready for CypherExecutor.execute_batch()
    """
    items = []
    for entity in entities:
        item = to_neo4j_node(entity)
        flatten_entity_connections(entity, item)
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
        return filtered_items

    return items
