"""
Graph Context Query Builder
===========================

Builds intent-specific Cypher for graph-context traversal, below the hexagonal
boundary. Pure function — no I/O, no side effects — consumed by
``CrossDomainBackend.query_with_intent``.

Relocated from ``core/services/infrastructure/graph_query_builder.py`` (2026-05):
Cypher generation is a persistence concern and belongs in
``adapters/persistence/neo4j/query/`` per ADR-044, not the service layer.

See: /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

from typing import Any

from core.ports import get_enum_value


def build_context_query_for_intent(intent: Any, depth: int) -> str:
    """
    Build Pure Cypher query for graph context retrieval based on intent.

    Uses variable-length patterns for efficient traversal.

    Args:
        intent: QueryIntent determining traversal strategy
        depth: Maximum traversal depth

    Returns:
        Pure Cypher query string
    """
    from core.models.query_types import QueryIntent

    intent_value = get_enum_value(intent)

    if intent_value == QueryIntent.HIERARCHICAL.value:
        return f"""
        MATCH (origin {{uid: $uid}})
        OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
        WHERE any(r in relationships(path) WHERE type(r) IN ['HAS_CHILD', 'PARENT_OF', 'CHILD_OF'])
        WITH origin, collect(DISTINCT related) as nodes,
             collect(DISTINCT [r in relationships(path) | {{
                 type: type(r),
                 start_uid: startNode(r).uid,
                 end_uid: endNode(r).uid,
                 properties: properties(r)
             }}]) as rels
        RETURN nodes, rels[0] as relationships
        """

    elif intent_value == QueryIntent.PREREQUISITE.value:
        return f"""
        MATCH (origin {{uid: $uid}})
        OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
        WHERE any(r in relationships(path) WHERE type(r) IN ['REQUIRES_KNOWLEDGE', 'PREREQUISITE_FOR', 'ENABLES'])
        WITH origin, collect(DISTINCT related) as nodes,
             collect(DISTINCT [r in relationships(path) | {{
                 type: type(r),
                 start_uid: startNode(r).uid,
                 end_uid: endNode(r).uid,
                 properties: properties(r)
             }}]) as rels
        RETURN nodes, rels[0] as relationships
        """

    elif intent_value == QueryIntent.PRACTICE.value:
        return f"""
        MATCH (origin {{uid: $uid}})
        OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
        WHERE any(r in relationships(path) WHERE type(r) IN ['PRACTICES', 'REINFORCES', 'APPLIES_KNOWLEDGE'])
        WITH origin, collect(DISTINCT related) as nodes,
             collect(DISTINCT [r in relationships(path) | {{
                 type: type(r),
                 start_uid: startNode(r).uid,
                 end_uid: endNode(r).uid,
                 properties: properties(r)
             }}]) as rels
        RETURN nodes, rels[0] as relationships
        """

    elif intent_value == QueryIntent.GOAL_ACHIEVEMENT.value:
        return f"""
        MATCH (origin {{uid: $uid}})
        OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
        WHERE any(r in relationships(path) WHERE type(r) IN [
            'FULFILLS_GOAL', 'SUPPORTS_GOAL', 'REQUIRES_KNOWLEDGE',
            'SUBGOAL_OF', 'GUIDED_BY_PRINCIPLE',
            'CONTRIBUTES_TO_GOAL'
        ])
        WITH origin, collect(DISTINCT related) as nodes,
             collect(DISTINCT [r in relationships(path) | {{
                 type: type(r),
                 start_uid: startNode(r).uid,
                 end_uid: endNode(r).uid,
                 properties: properties(r)
             }}]) as rels
        RETURN nodes, rels[0] as relationships
        """

    elif intent_value == QueryIntent.PRINCIPLE_EMBODIMENT.value:
        return f"""
        MATCH (origin {{uid: $uid}})
        OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
        WHERE any(r in relationships(path) WHERE type(r) IN [
            'GUIDED_BY_PRINCIPLE', 'ALIGNED_WITH_PRINCIPLE', 'INSPIRES_HABIT',
            'GROUNDED_IN_KNOWLEDGE', 'GUIDES_GOAL', 'GUIDES_CHOICE'
        ])
        WITH origin, collect(DISTINCT related) as nodes,
             collect(DISTINCT [r in relationships(path) | {{
                 type: type(r),
                 start_uid: startNode(r).uid,
                 end_uid: endNode(r).uid,
                 properties: properties(r)
             }}]) as rels
        RETURN nodes, rels[0] as relationships
        """

    elif intent_value == QueryIntent.PRINCIPLE_ALIGNMENT.value:
        return f"""
        MATCH (origin {{uid: $uid}})
        OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
        WHERE any(r in relationships(path) WHERE type(r) IN [
            'ALIGNED_WITH_PRINCIPLE', 'INFORMED_BY_KNOWLEDGE', 'SUPPORTS_GOAL',
            'CONFLICTS_WITH_GOAL', 'REQUIRES_KNOWLEDGE_FOR_DECISION',
            'OPENS_LEARNING_PATH', 'GUIDED_BY_PRINCIPLE'
        ])
        WITH origin, collect(DISTINCT related) as nodes,
             collect(DISTINCT [r in relationships(path) | {{
                 type: type(r),
                 start_uid: startNode(r).uid,
                 end_uid: endNode(r).uid,
                 properties: properties(r)
             }}]) as rels
        RETURN nodes, rels[0] as relationships
        """

    elif intent_value == QueryIntent.SCHEDULED_ACTION.value:
        return f"""
        MATCH (origin {{uid: $uid}})
        OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
        WHERE any(r in relationships(path) WHERE type(r) IN [
            'EXECUTES_TASK', 'PRACTICES_KNOWLEDGE', 'REINFORCES_HABIT',
            'MILESTONE_FOR_GOAL', 'CONFLICTS_WITH', 'SUPPORTS_GOAL',
            'SCHEDULED_FOR', 'DERIVED_FROM_TASK'
        ])
        WITH origin, collect(DISTINCT related) as nodes,
             collect(DISTINCT [r in relationships(path) | {{
                 type: type(r),
                 start_uid: startNode(r).uid,
                 end_uid: endNode(r).uid,
                 properties: properties(r)
             }}]) as rels
        RETURN nodes, rels[0] as relationships
        """

    else:  # RELATIONSHIP, EXPLORATORY, SPECIFIC, AGGREGATION - generic traversal
        return f"""
        MATCH (origin {{uid: $uid}})
        OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
        WITH origin, collect(DISTINCT related) as nodes,
             collect(DISTINCT [r in relationships(path) | {{
                 type: type(r),
                 start_uid: startNode(r).uid,
                 end_uid: endNode(r).uid,
                 properties: properties(r)
             }}]) as rels
        RETURN nodes, rels[0] as relationships
        LIMIT 100
        """
