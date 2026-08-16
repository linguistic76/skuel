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

from core.models.enums import Domain
from core.models.graph_context import (
    ContextRelevance,
    DomainContext,
    GraphContext,
    GraphNode,
    GraphRelationship,
    RelationshipStrength,
)
from core.utils.type_converters import get_enum_value


def determine_domain(node_dict: dict[str, Any], labels: list[str]) -> Domain:
    """
    Determine domain from node properties or labels.

    Args:
        node_dict: Node properties dictionary
        labels: Node labels list

    Returns:
        Domain enum value
    """
    # Check if domain is in properties
    if "domain" in node_dict:
        domain_val = node_dict["domain"]
        try:
            return Domain(domain_val) if isinstance(domain_val, str) else domain_val
        except ValueError:
            pass

    # Infer from labels
    label_to_domain = {
        "Task": Domain.TASKS,
        "Habit": Domain.HABITS,
        "Goal": Domain.GOALS,
        "Event": Domain.EVENTS,
        "Entity": Domain.KNOWLEDGE,
        "Lp": Domain.LEARNING,
        "Finance": Domain.FINANCE,
        "Choice": Domain.CHOICES,
        "Principle": Domain.PRINCIPLES,
        "Journal": Domain.JOURNALS,
    }

    for label in labels:
        if label in label_to_domain:
            return label_to_domain[label]

    return Domain.KNOWLEDGE


def _is_stronger_path(candidate: dict[str, Any], incumbent: dict[str, Any]) -> bool:
    """Strongest-path tiebreak between two path entries for the same node uid.

    The producer collects one entry per DISTINCT path (no ``ORDER BY``), so a node
    reachable by several paths recurs. Keep the strongest: fewest hops first, then highest
    confidence cascade. Mirrors ``_path_rank`` in ``choices/_core_intelligence_mixin``.
    """
    cand_dist = candidate.get("distance", 1)
    inc_dist = incumbent.get("distance", 1)
    if cand_dist != inc_dist:
        return cand_dist < inc_dist
    return candidate.get("path_strength", 0.0) > incumbent.get("path_strength", 0.0)


def build_graph_context_from_domain_context(
    domain_context: list[dict[str, Any]],
    node_uid: str,
    domain: Any,
    intent: Any,
    depth: int,
) -> GraphContext:
    """
    Build a GraphContext from ``build_domain_context_with_paths`` output.

    THE single transform for the intent-traversal reader. Consumes the incident-edge-
    attributed node maps the cross-domain-context producer emits (each carrying ``uid``,
    ``labels``, full ``properties``, ``distance``, ``path_strength``, ``via_relationships``,
    ``incident_rel_type``, ``incident_into_related``), de-dups multi-path recurrences to the
    strongest entry per uid, and assembles the ``GraphContext`` shape that
    ``query_with_intent`` callers already consume (``get_summary``, ``get_nodes_by_domain``,
    ``all_nodes`` w/ ``node.properties``). Replaces the old flat-query transformer so both
    graph readers share one incident-edge-attributed Cypher path (Convergence Phase 2).

    Args:
        domain_context: ``domain_context`` list from build_domain_context_with_paths
        node_uid: UID of the origin node
        domain: Domain of the origin node
        intent: QueryIntent that was used
        depth: Maximum traversal depth used

    Returns:
        Fully populated GraphContext
    """
    # De-dup multi-path recurrences to the strongest entry per uid (the producer has no
    # ORDER BY; keeping the wrong entry misreports distance/path_strength). The old flat
    # query's `collect(DISTINCT related)` was already uid-unique, so dedup preserves that.
    best_by_uid: dict[str, dict[str, Any]] = {}
    for entry in domain_context:
        if not entry:
            continue
        uid = entry.get("uid")
        if not uid:
            continue
        incumbent = best_by_uid.get(uid)
        if incumbent is None or _is_stronger_path(entry, incumbent):
            best_by_uid[uid] = entry

    all_nodes: list[GraphNode] = []
    all_relationships: list[GraphRelationship] = []

    for uid, entry in best_by_uid.items():
        labels = entry.get("labels", ["Unknown"])
        if isinstance(labels, str):
            labels = [labels]

        # Full node properties live under "properties"; fall back to title-only for an
        # entry from a producer that predates the properties column.
        properties = entry.get("properties") or {"title": entry.get("title")}
        node_domain = determine_domain(properties, labels)
        incident_rel = entry.get("incident_rel_type")

        all_nodes.append(
            GraphNode(
                uid=uid,
                labels=labels,
                domain=node_domain,
                properties=properties,
                distance_from_origin=entry.get("distance", 1),
                relevance=ContextRelevance.MEDIUM,
                relationship_to_origin=incident_rel,
            )
        )

        # One GraphRelationship per node from the edge INCIDENT to it. Orientation comes
        # from incident_into_related; the other endpoint is the origin (exact at depth 1,
        # an approximation at depth >= 2 — endpoints are not consumed critically, while the
        # type powers relationship_patterns). No edge → skip.
        if incident_rel:
            into_related = entry.get("incident_into_related")
            start_uid, end_uid = (node_uid, uid) if into_related else (uid, node_uid)
            all_relationships.append(
                GraphRelationship(
                    type=incident_rel,
                    start_node_uid=start_uid,
                    end_node_uid=end_uid,
                    properties=entry.get("incident_rel_properties", {}) or {},
                    strength=RelationshipStrength.MODERATE,
                    bidirectional=False,
                )
            )

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
