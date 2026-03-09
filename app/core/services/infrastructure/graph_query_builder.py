"""
Graph Query Builder - Pure Cypher Construction
===============================================

Pure functions for building intent-specific Cypher queries.
Extracted from GraphIntelligenceService to separate query construction from execution.

Each function returns a Cypher query string — no I/O, no side effects.
"""

from __future__ import annotations

from typing import Any

from core.models.enums import Domain
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
            'SUBGOAL_OF', 'HAS_MILESTONE', 'GUIDED_BY_PRINCIPLE',
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
