"""
Semantic Queries - Knowledge Graph Semantic Relationships
==========================================================

Cypher query builders for semantic relationship traversal, prerequisite chains,
and cross-domain knowledge bridges.

Methods:
- build_semantic_context: Semantic knowledge context with confidence filtering
- build_domain_context_with_paths: Cross-domain context with path metadata
- build_prerequisite_chain: Transitive prerequisite discovery
- build_semantic_traversal: Shortest path using semantic relationships
- build_hierarchical_context: Parents and children in knowledge hierarchy
- build_cross_domain_bridges: Find concepts connecting two domains
- build_semantic_filter_query: Filter nodes by semantic relationship presence
"""

from typing import TYPE_CHECKING

from adapters.persistence.neo4j._backend_helpers import direction_clause
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import Neo4jValue

from ._helpers import validate_identifier, validate_label

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import (
        SemanticRelationshipType,
        SemanticTriple,
    )


def build_semantic_context(
    node_uid: str,
    semantic_types: list["SemanticRelationshipType"],
    depth: int = 2,
    min_confidence: float = 0.0,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build pure Cypher query for semantic knowledge context.

    Generates optimized Cypher that:
    - Uses query planner optimization
    - Benefits from indexes
    - Gets cached by Neo4j
    - Has type-safe semantic types
    - No APOC black box

    Args:
        node_uid: Starting node UID
        semantic_types: List of semantic relationship types to traverse
        depth: Maximum traversal depth (default 2)
        min_confidence: Minimum confidence score filter (default 0.0)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    # Convert semantic types to Cypher pattern
    rel_pattern = "|".join([st.to_neo4j_name() for st in semantic_types])

    cypher = f"""
    MATCH (center {{uid: $uid}})
    OPTIONAL MATCH path = (center)-[r:{rel_pattern}*1..{depth}]-(related)
    WITH center, related, path, relationships(path) as rels,
         [rel in relationships(path) | rel.confidence] as confidences,
         length(path) as path_length
    WHERE related IS NOT NULL
      AND all(c in confidences WHERE c >= $min_confidence)
    RETURN
        center.uid as center_uid,
        collect(DISTINCT {{
            uid: related.uid,
            title: related.title,
            depth: path_length,
            avg_confidence: reduce(sum = 0.0, c in confidences | sum + c) / size(confidences),
            relationship_types: [rel in rels | type(rel)]
        }}) as semantic_context
    """

    parameters: dict[str, Neo4jValue] = {"uid": node_uid, "min_confidence": min_confidence}

    return cypher, parameters


def build_semantic_merge(
    triple: "SemanticTriple",
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build the MERGE query + params that persist a single semantic triple.

    The relationship label is sourced from the ``SemanticRelationshipType``
    enum (a closed vocabulary) and validated as a safe identifier before
    interpolation; the triple's metadata is written as edge properties.

    Args:
        triple: The semantic triple (subject-predicate-object + metadata)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    rel_label = triple.predicate.to_neo4j_name()
    validate_identifier(rel_label, "relationship type")

    # RelationshipName owns the edge type (the coarse bucket); the precise
    # namespaced predicate is preserved as the `semantic_type` property so the
    # many-to-one to_neo4j_name() collapse is non-lossy and the two intra-enum
    # collisions (cross:related_to vs moc:related_to, concept:child_of vs
    # moc:child_of) stay distinguishable. See the semantic-relationship-layer
    # roadmap Phase 1.
    props = triple.metadata.to_neo4j_properties()
    props["semantic_type"] = triple.predicate.value
    props_str = ", ".join(f"{k}: ${k}" for k in props)

    cypher = f"""
    MERGE (s {{uid: $subject}})
    MERGE (o {{uid: $object}})
    MERGE (s)-[r:{rel_label}]->(o)
    ON CREATE SET r = {{{props_str}}}
    ON MATCH SET r += {{{props_str}}}
    """

    parameters: dict[str, Neo4jValue] = {"subject": triple.subject, "object": triple.object}
    parameters.update(props)

    return cypher, parameters


def build_domain_context_with_paths(
    node_uid: str,
    node_label: NeoLabel | None = None,
    relationship_types: list[str] | None = None,
    depth: int = 2,
    min_confidence: float = 0.0,
    bidirectional: bool = False,
    limit: int | None = None,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for cross-domain context with path-aware intelligence.

    Accepts LITERAL relationship type strings instead of SemanticRelationshipType enum.
    Essential for domain-specific relationships like "INFORMED_BY_PRINCIPLE", "SUPPORTS_GOAL".

    THE single producer for path-aware graph context. Feeds BOTH the bucketed
    cross-domain-context reader (``get_cross_domain_context`` → incident-edge attribution)
    AND the intent-traversal reader (``query_with_intent`` → ``GraphContext``), so both go
    through one incident-edge-attributed + strongest-path-dedupable Cypher path rather than
    parallel queries (Convergence Phase 2, direction-aware bucketing).
    See: /docs/roadmap/intent-traversal-registry-convergence.md

    The source node is excluded from its own context (``related.uid <> center.uid``),
    so a cycle back to the center never lands the entity in its own result buckets.

    Returns path metadata for each related entity:
    - properties: the related node's full property map — so intent-traversal consumers that
      read ``node.properties`` (e.g. ``get_entity_context`` → ``intelligence_queries``,
      ``activity_knowledge_intelligence_service``) keep their contract under the fold; the
      bucketed reader ignores it.
    - distance: Number of hops from source
    - path_strength: Confidence cascade (product of relationship confidences)
    - via_relationships: Sequence of relationship types in path
    - incident_rel_type: Type of the edge INCIDENT to the related node (the last hop),
      i.e. the edge that determines which cross-domain bucket the node belongs to.
    - incident_into_related: True if that last edge points INTO the related node
      (``related`` is its DB endNode → the node is the object of the relationship),
      False if it points OUT (``related`` is the subject). Lets categorization match a
      mapping's direction at ANY distance, not just distance 1.
    - incident_rel_properties: the incident edge's properties map (e.g.
      ``{"essentiality": "essential"}``). Lets categorization route a node to a
      property-filtered mapping (``filter_property``/``filter_value``) — e.g. a goal's
      essential vs critical vs optional supporting habits, which all share the
      SUPPORTS_GOAL relationship and differ only by this edge property.

    Args:
        node_uid: Starting node UID
        node_label: Starting node label (e.g., "Choice", "Goal", "Task"). ``None`` matches
            on ``uid`` alone — the intent-traversal path has only the domain, not the label.
        relationship_types: Literal relationship type names to traverse. Empty/``None``
            traverses EVERY edge type (the generic ``RELATIONSHIP``/``EXPLORATORY`` lens).
        depth: Maximum traversal depth (default 2)
        min_confidence: Minimum confidence filter (default 0.0)
        bidirectional: Include both incoming and outgoing (default False)
        limit: Optional cap on matched (center, related, path) rows BEFORE the ``collect``
            aggregation — genuinely bounds the materialized node set on dense graphs (the
            intent path passes 100, preserving the old filtered-branch ``LIMIT``; the
            bucketed reader passes ``None`` to keep its depth/registry-bounded behavior).

    Returns:
        Tuple of (cypher_query, parameters)
    """
    # Build relationship pattern. An empty type list means "any relationship type" —
    # the generic intent lens — so omit the `:TYPE|TYPE` filter entirely (a bare
    # `[r:*1..n]` is a Cypher syntax error).
    rel_types = relationship_types or []
    rel_segment = f"[r:{'|'.join(rel_types)}*1..{depth}]" if rel_types else f"[r*1..{depth}]"

    # Build direction pattern
    direction_pattern = "" if bidirectional else ">"

    # Match on label when supplied (index-friendly); else on uid alone.
    center_pattern = (
        f"(center:{node_label} {{uid: $uid}})" if node_label else "(center {uid: $uid})"
    )

    # Optional pre-aggregation row cap (genuinely bounds the result on dense graphs).
    limit_clause = ""
    if limit is not None:
        limit_clause = """
    WITH center, related, rels, confidences, path_length, path_nodes
    LIMIT $limit"""

    # The center row is kept even when no edge matches (``related IS NULL``) — the null is
    # excluded INSIDE the collect, not by a row-dropping WHERE — so an edge-less entity
    # yields one record with an empty ``domain_context`` rather than zero records. That
    # distinction matters: ``query_with_intent`` reads zero records as NOT-FOUND (node
    # absent), so a present-but-unconnected node must still produce a record. (A null row
    # exists ONLY when the OPTIONAL MATCH finds nothing, so it never coexists with real
    # rows.)
    cypher = f"""
    MATCH {center_pattern}
    OPTIONAL MATCH path = (center)-{rel_segment}-{direction_pattern}(related)
    WHERE related IS NULL OR related.uid <> center.uid
    WITH center, related, relationships(path) as rels,
         [rel in relationships(path) | coalesce(rel.confidence, 0.8)] as confidences,
         length(path) as path_length,
         nodes(path) as path_nodes
    WHERE related IS NULL OR all(c in confidences WHERE c >= $min_confidence){limit_clause}
    WITH center, collect(DISTINCT
        CASE WHEN related IS NULL THEN null ELSE {{
            uid: related.uid,
            title: coalesce(related.title, related.name, related.uid),
            labels: labels(related),
            properties: properties(related),
            distance: path_length,
            path_strength: reduce(product = 1.0, c in confidences | product * c),
            via_relationships: [
                rel in rels |
                CASE
                    WHEN startNode(rel) = path_nodes[0] THEN '->' + type(rel)
                    WHEN endNode(rel) = path_nodes[0] THEN '<-' + type(rel)
                    ELSE type(rel)
                END
            ],
            incident_rel_type: type(last(rels)),
            incident_into_related: endNode(last(rels)) = related,
            incident_rel_properties: properties(last(rels))
        }} END
    ) as ctx
    RETURN center.uid as center_uid,
           [x in ctx WHERE x IS NOT NULL] as domain_context
    """

    parameters: dict[str, Neo4jValue] = {"uid": node_uid, "min_confidence": min_confidence}
    if limit is not None:
        parameters["limit"] = limit

    return cypher, parameters


def build_prerequisite_chain(
    node_uid: str,
    semantic_types: list["SemanticRelationshipType"],
    depth: int = 3,
    min_confidence: float = 0.7,
    min_strength: float = 0.0,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build pure Cypher query for prerequisite chain.

    Finds all prerequisites transitively up to specified depth.
    Essential for learning path construction and dependency analysis.

    Args:
        node_uid: Target node UID
        semantic_types: List of semantic relationship types for prerequisites
        depth: Maximum chain depth (default 3)
        min_confidence: Minimum relationship confidence threshold (default 0.7)
        min_strength: Minimum relationship strength threshold (default 0.0)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    rel_pattern = "|".join([st.to_neo4j_name() for st in semantic_types])

    cypher = f"""
    MATCH (target {{uid: $uid}})
    MATCH path = (target)<-[rs:{rel_pattern}*1..{depth}]-(prereq)
    WHERE NOT (prereq)<-[:{rel_pattern}]-()
      AND all(r IN rs WHERE
          coalesce(r.confidence, 1.0) >= $min_confidence
          AND coalesce(r.strength, 1.0) >= $min_strength
      )
    WITH prereq, path, relationships(path) as chain
    RETURN
        prereq.uid as uid,
        prereq.title as title,
        length(path) as depth,
        [rel in chain | {{
            type: type(rel),
            confidence: coalesce(rel.confidence, 0.8),
            strength: coalesce(rel.strength, 1.0)
        }}] as relationship_chain
    ORDER BY depth ASC
    """

    parameters: dict[str, Neo4jValue] = {
        "uid": node_uid,
        "min_confidence": min_confidence,
        "min_strength": min_strength,
    }
    return cypher, parameters


def build_semantic_traversal(
    start_uid: str,
    end_uid: str,
    semantic_types: list["SemanticRelationshipType"],
    max_depth: int = 5,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build pure Cypher query for semantic path finding.

    Finds shortest path using only specified semantic relationship types.
    Useful for learning path generation and knowledge gap analysis.

    Args:
        start_uid: Starting node UID
        end_uid: Ending node UID
        semantic_types: List of semantic relationship types to use
        max_depth: Maximum path depth (default 5)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    rel_pattern = "|".join([st.to_neo4j_name() for st in semantic_types])

    cypher = f"""
    MATCH (start {{uid: $start_uid}})
    MATCH (end {{uid: $end_uid}})
    MATCH path = shortestPath(
        (start)-[r:{rel_pattern}*1..{max_depth}]-(end)
    )
    WITH path, relationships(path) as rels
    RETURN
        [n in nodes(path) | {{
            uid: n.uid,
            title: n.title
        }}] as path_nodes,
        [rel in rels | {{
            type: type(rel),
            confidence: coalesce(rel.confidence, 0.8),
            strength: coalesce(rel.strength, 1.0)
        }}] as path_relationships,
        length(path) as path_length
    """

    parameters: dict[str, Neo4jValue] = {"start_uid": start_uid, "end_uid": end_uid}

    return cypher, parameters


def build_hierarchical_context(
    node_uid: str,
    parent_types: list["SemanticRelationshipType"],
    child_types: list["SemanticRelationshipType"],
    depth: int = 2,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build pure Cypher query for hierarchical context.

    Gets both parents and children using semantic relationship types.
    Essential for understanding position in knowledge hierarchy.

    Args:
        node_uid: Center node UID
        parent_types: List of semantic relationship types for parents
        child_types: List of semantic relationship types for children
        depth: Maximum traversal depth (default 2)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    parent_pattern = "|".join([st.to_neo4j_name() for st in parent_types])
    child_pattern = "|".join([st.to_neo4j_name() for st in child_types])

    cypher = f"""
    MATCH (center {{uid: $uid}})

    // Get parents
    OPTIONAL MATCH parent_path = (center)-[pr:{parent_pattern}*1..{depth}]->(parent)
    WITH center, collect(DISTINCT {{
        uid: parent.uid,
        title: parent.title,
        depth: length(parent_path),
        direction: 'parent'
    }}) as parents

    // Get children
    OPTIONAL MATCH child_path = (center)<-[cr:{child_pattern}*1..{depth}]-(child)
    WITH center, parents, collect(DISTINCT {{
        uid: child.uid,
        title: child.title,
        depth: length(child_path),
        direction: 'child'
    }}) as children

    RETURN
        center.uid as center_uid,
        parents,
        children,
        size(parents) + size(children) as total_related
    """

    parameters: dict[str, Neo4jValue] = {"uid": node_uid}
    return cypher, parameters


def build_cross_domain_bridges(
    domain_a: str,
    domain_b: str,
    semantic_types: list["SemanticRelationshipType"],
    limit: int = 10,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build pure Cypher query for cross-domain knowledge bridges.

    Finds concepts that connect two domains via semantic relationships.
    Essential for interdisciplinary learning and knowledge transfer.

    Args:
        domain_a: First domain
        domain_b: Second domain
        semantic_types: List of semantic relationship types to traverse
        limit: Maximum number of bridges to return (default 10)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    rel_pattern = "|".join([st.to_neo4j_name() for st in semantic_types])

    cypher = f"""
    MATCH (a {{domain: $domain_a}})
    MATCH (b {{domain: $domain_b}})
    MATCH path = shortestPath(
        (a)-[r:{rel_pattern}*1..5]-(b)
    )
    WITH path, relationships(path) as rels, nodes(path) as nodes
    RETURN
        a.uid as source_uid,
        a.title as source_title,
        b.uid as target_uid,
        b.title as target_title,
        [n in nodes | {{uid: n.uid, title: n.title, domain: n.domain}}] as bridge_path,
        [rel in rels | type(rel)] as relationship_types,
        length(path) as bridge_length
    ORDER BY bridge_length ASC
    LIMIT $limit
    """

    parameters: dict[str, Neo4jValue] = {"domain_a": domain_a, "domain_b": domain_b, "limit": limit}

    return cypher, parameters


def build_semantic_filter_query(
    label: NeoLabel,
    semantic_type: "SemanticRelationshipType",
    min_confidence: float = 0.8,
    direction: str = "outgoing",
    limit: int = 50,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build pure Cypher query to find nodes with semantic relationships.

    Finds all nodes of a given label that have specific semantic relationships,
    filtered by confidence and direction.

    Args:
        label: Node label to search
        semantic_type: Semantic relationship type to filter by
        min_confidence: Minimum confidence score (default 0.8)
        direction: 'outgoing', 'incoming', or 'both' (default 'outgoing')
        limit: Max results (default 50)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    validate_label(label)
    rel_name = semantic_type.to_neo4j_name()

    # Build direction pattern (the connected node is anonymous — RETURN only reads n/r)
    pattern = f"(n:{label}){direction_clause(direction, 'r', rel_name)}(other)"

    cypher = f"""
    MATCH {pattern}
    WHERE r.confidence >= $min_confidence
    WITH n, r, count(*) as rel_count
    RETURN
        n.uid as uid,
        n.title as title,
        rel_count,
        avg(r.confidence) as avg_confidence,
        max(r.strength) as max_strength
    ORDER BY rel_count DESC, avg_confidence DESC
    LIMIT $limit
    """

    parameters: dict[str, Neo4jValue] = {"min_confidence": min_confidence, "limit": limit}

    return cypher, parameters
