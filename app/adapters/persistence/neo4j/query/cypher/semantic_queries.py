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

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType


def build_semantic_context(
    node_uid: str,
    semantic_types: list["SemanticRelationshipType"],
    depth: int = 2,
    min_confidence: float = 0.0,
) -> tuple[str, dict[str, Any]]:
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

    parameters = {"uid": node_uid, "min_confidence": min_confidence}

    return cypher, parameters


def build_domain_context_with_paths(
    node_uid: str,
    node_label: str,
    relationship_types: list[str],
    depth: int = 2,
    min_confidence: float = 0.0,
    bidirectional: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for cross-domain context with path-aware intelligence.

    Accepts LITERAL relationship type strings instead of SemanticRelationshipType enum.
    Essential for domain-specific relationships like "INFORMED_BY_PRINCIPLE", "SUPPORTS_GOAL".

    Returns path metadata for each related entity:
    - distance: Number of hops from source
    - path_strength: Confidence cascade (product of relationship confidences)
    - via_relationships: Sequence of relationship types in path

    Args:
        node_uid: Starting node UID
        node_label: Starting node label (e.g., "Choice", "Goal", "Task")
        relationship_types: List of literal relationship type names
        depth: Maximum traversal depth (default 2)
        min_confidence: Minimum confidence filter (default 0.0)
        bidirectional: Include both incoming and outgoing (default False)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    # Build relationship pattern
    rel_pattern = "|".join(relationship_types)

    # Build direction pattern
    direction_pattern = "" if bidirectional else ">"

    cypher = f"""
    MATCH (center:{node_label} {{uid: $uid}})
    OPTIONAL MATCH path = (center)-[r:{rel_pattern}*1..{depth}]-{direction_pattern}(related)
    WITH center, related, path, relationships(path) as rels,
         [rel in relationships(path) | coalesce(rel.confidence, 0.8)] as confidences,
         length(path) as path_length,
         nodes(path) as path_nodes
    WHERE related IS NOT NULL
      AND all(c in confidences WHERE c >= $min_confidence)
    RETURN
        center.uid as center_uid,
        collect(DISTINCT {{
            uid: related.uid,
            title: coalesce(related.title, related.name, related.uid),
            labels: labels(related),
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
            via_relationships_plain: [rel in rels | type(rel)]
        }}) as domain_context
    """

    parameters = {"uid": node_uid, "min_confidence": min_confidence}

    return cypher, parameters


def build_prerequisite_chain(
    node_uid: str,
    semantic_types: list["SemanticRelationshipType"],
    depth: int = 3,
    min_confidence: float = 0.7,
    min_strength: float = 0.0,
) -> tuple[str, dict[str, Any]]:
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

    parameters = {
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
) -> tuple[str, dict[str, Any]]:
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

    parameters = {"start_uid": start_uid, "end_uid": end_uid}

    return cypher, parameters


def build_hierarchical_context(
    node_uid: str,
    parent_types: list["SemanticRelationshipType"],
    child_types: list["SemanticRelationshipType"],
    depth: int = 2,
) -> tuple[str, dict[str, Any]]:
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

    parameters = {"uid": node_uid}
    return cypher, parameters


def build_cross_domain_bridges(
    domain_a: str,
    domain_b: str,
    semantic_types: list["SemanticRelationshipType"],
    limit: int = 10,
) -> tuple[str, dict[str, Any]]:
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

    parameters = {"domain_a": domain_a, "domain_b": domain_b, "limit": limit}

    return cypher, parameters


def build_semantic_filter_query(
    label: str,
    semantic_type: "SemanticRelationshipType",
    min_confidence: float = 0.8,
    direction: str = "outgoing",
    limit: int = 50,
) -> tuple[str, dict[str, Any]]:
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
    rel_name = semantic_type.to_neo4j_name()

    # Build direction pattern
    if direction == "outgoing":
        pattern = f"(n:{label})-[r:{rel_name}]->(target)"
    elif direction == "incoming":
        pattern = f"(n:{label})<-[r:{rel_name}]-(source)"
    else:  # both
        pattern = f"(n:{label})-[r:{rel_name}]-(connected)"

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

    parameters = {"min_confidence": min_confidence, "limit": limit}

    return cypher, parameters
