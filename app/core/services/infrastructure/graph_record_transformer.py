"""
Graph Record Transformer - Pure Record→GraphContext Conversion
==============================================================

Pure functions for transforming Neo4j query records into GraphContext objects.
Extracted from GraphIntelligenceService to separate transformation from I/O.

No database access — takes raw records and produces domain objects.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.models.graph_context import (
    ContextRelevance,
    DomainContext,
    GraphContext,
    GraphNode,
    GraphRelationship,
    RelationshipStrength,
)
from core.ports import get_enum_value
from core.services.infrastructure.graph_query_builder import determine_domain


def transform_records_to_graph_context(
    records: list[dict[str, Any]],
    node_uid: str,
    domain: Any,
    intent: Any,
    depth: int,
) -> GraphContext:
    """
    Transform Neo4j query records into a GraphContext object.

    Args:
        records: Raw records from Neo4j query execution
        node_uid: UID of the origin node
        domain: Domain of the origin node
        intent: QueryIntent that was used
        depth: Maximum traversal depth used

    Returns:
        Fully populated GraphContext
    """
    all_nodes: list[GraphNode] = []
    all_relationships: list[GraphRelationship] = []

    for record in records:
        nodes_data = record.get("nodes", []) or record.get("related_nodes", [])
        rels_data = record.get("relationships", [])

        for i, node_dict in enumerate(nodes_data):
            if not node_dict:
                continue

            uid = node_dict.get("uid", f"node_{i}")
            labels = node_dict.get("labels", ["Unknown"])
            if isinstance(labels, str):
                labels = [labels]

            node_domain = determine_domain(node_dict, labels)

            graph_node = GraphNode(
                uid=uid,
                labels=labels,
                domain=node_domain,
                properties=node_dict,
                distance_from_origin=node_dict.get("distance", 1),
                relevance=ContextRelevance.MEDIUM,
                relationship_to_origin=node_dict.get("relationship_type"),
            )
            all_nodes.append(graph_node)

        for rel_dict in rels_data:
            if not rel_dict:
                continue

            graph_rel = GraphRelationship(
                type=rel_dict.get("type", "RELATED_TO"),
                start_node_uid=rel_dict.get("start_uid", ""),
                end_node_uid=rel_dict.get("end_uid", ""),
                properties=rel_dict.get("properties", {}),
                strength=RelationshipStrength.MODERATE,
                bidirectional=rel_dict.get("bidirectional", False),
            )
            all_relationships.append(graph_rel)

    # Group nodes by domain
    domain_contexts_dict: dict[Any, dict[str, list[Any]]] = {}
    for node in all_nodes:
        if node.domain not in domain_contexts_dict:
            domain_contexts_dict[node.domain] = {"nodes": [], "relationships": []}
        domain_contexts_dict[node.domain]["nodes"].append(node)

    # Build DomainContext objects
    domain_contexts: dict[Any, DomainContext] = {}
    for dom, data in domain_contexts_dict.items():
        domain_rels = [
            r
            for r in all_relationships
            if any(n.uid == r.start_node_uid or n.uid == r.end_node_uid for n in data["nodes"])
        ]
        domain_contexts[dom] = DomainContext(
            domain=dom,
            nodes=data["nodes"],
            relationships=domain_rels,
            node_count=len(data["nodes"]),
            relationship_count=len(domain_rels),
        )

    # Calculate relationship patterns
    relationship_patterns: dict[str, int] = {}
    for rel in all_relationships:
        relationship_patterns[rel.type] = relationship_patterns.get(rel.type, 0) + 1

    return GraphContext(
        origin_uid=node_uid,
        origin_domain=domain,
        query_intent=get_enum_value(intent),
        all_nodes=all_nodes,
        all_relationships=all_relationships,
        domain_contexts=domain_contexts,
        cross_domain_insights=[],
        relationship_patterns=relationship_patterns,
        total_nodes=len(all_nodes),
        total_relationships=len(all_relationships),
        domains_involved=list(domain_contexts.keys()),
        max_depth_reached=depth,
        query_timestamp=datetime.now(),
        neo4j_query_time_ms=None,
        processing_time_ms=None,
    )
