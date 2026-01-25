"""
Pure Cypher Graph Traversal - Replace APOC with Variable-Length Patterns
=========================================================================

This module provides Pure Cypher alternatives to APOC path traversal operations.
Uses native Neo4j variable-length patterns for portability and performance.

**Philosophy:** "Leverage pre-existing ways of performing actions"

Instead of APOC procedures, we use:
- Variable-length patterns: `()-[*1..5]->()`
- Path functions: `nodes(path)`, `relationships(path)`
- Standard Cypher: Works on ANY Neo4j installation

**Benefits:**
- No APOC dependency required
- Portable across all Neo4j installations
- Simpler to read and maintain
- No plugin configuration needed
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.query._query_models import QueryIntent


def build_graph_context_query(
    node_uid: str,  # noqa: ARG001 - passed to query executor, not embedded in string
    intent: "QueryIntent",
    depth: int = 2,
) -> str:
    """
    Build Pure Cypher query for graph context traversal.

    Uses variable-length patterns instead of APOC procedures.

    Args:
        node_uid: UID of the node to start traversal from (passed to query executor as {"uid": node_uid})
        intent: Type of context to retrieve (HIERARCHICAL, PREREQUISITE, etc.)
        depth: Maximum traversal depth (embedded in variable-length pattern range)

    Returns:
        Pure Cypher query string (no APOC dependency)

    Note:
        This is a query builder function. node_uid is NOT embedded in the returned
        string but should be passed to the Neo4j query executor as {"uid": node_uid}.
        The depth parameter IS embedded in the query at build time.

    Example:
        query = build_graph_context_query("ku.python_basics", QueryIntent.PREREQUISITE, 3)
        result = await session.run(query, {"uid": "ku.python_basics"})
    """
    from core.models.query._query_models import QueryIntent

    if intent == QueryIntent.HIERARCHICAL:
        # Pure Cypher variable-length pattern for hierarchical traversal
        return f"""
            MATCH (u {{uid: $uid}})
            OPTIONAL MATCH path = (u)-[:HAS_CHILD|PARENT_OF|CHILD_OF*0..{depth}]-(related)
            WITH u, collect(DISTINCT related) as related_nodes
            OPTIONAL MATCH (u)-[:HAS_CHILD|CHILD_OF]->(child)
            OPTIONAL MATCH (u)<-[:HAS_CHILD|PARENT_OF]-(parent)
            RETURN related_nodes,
                   collect(DISTINCT child.uid) as children,
                   parent.uid as parent
        """

    elif intent == QueryIntent.PREREQUISITE:
        # Pure Cypher variable-length pattern for prerequisite chains
        return f"""
            MATCH (u {{uid: $uid}})
            OPTIONAL MATCH path = (u)-[:PREREQUISITE_FOR|ENABLES*0..{depth}]->(prereq)
            WITH u, collect(DISTINCT prereq) as prereq_chain
            OPTIONAL MATCH (u)-[:PREREQUISITE_FOR]->(direct_prereq)
            RETURN prereq_chain,
                   collect(DISTINCT direct_prereq.uid) as direct_prerequisites,
                   size(prereq_chain) as prereq_depth
        """

    elif intent == QueryIntent.PRACTICE:
        # Pure Cypher pattern for practice/example nodes
        return f"""
            MATCH (u {{uid: $uid}})
            OPTIONAL MATCH (u)-[:HAS_EXERCISE|HAS_EXAMPLE*0..{depth}]->(practice)
            WHERE practice.content_type IN ['exercise', 'example', 'practice']
            WITH u, collect(DISTINCT practice) as practice_nodes
            RETURN practice_nodes,
                   size(practice_nodes) as practice_count
        """

    elif intent == QueryIntent.RELATIONSHIP:
        # Pure Cypher pattern for relationship exploration
        return f"""
            MATCH (u {{uid: $uid}})
            OPTIONAL MATCH path = (u)-[r*0..{depth}]-(related)
            WHERE length(path) <= {depth}
            WITH u, collect(DISTINCT related) as nodes, collect(DISTINCT r) as relationships
            RETURN nodes, relationships,
                   [rel in relationships | type(rel)] as relationship_types
            LIMIT 50
        """

    else:  # EXPLORATORY or SPECIFIC - no variable-length pattern, depth not applicable
        return """
            MATCH (u {uid: $uid})
            OPTIONAL MATCH (u)-[r]-(related)
            WITH u, type(r) as rel_type, collect(related) as related_nodes
            RETURN collect({type: rel_type, nodes: related_nodes}) as relationships,
                   size(related_nodes) as total_connections
        """


__all__ = ["build_graph_context_query"]
