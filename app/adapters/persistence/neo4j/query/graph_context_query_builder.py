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


def build_context_query_for_intent(
    intent: Any, depth: int, relationship_types: list[str] | None = None
) -> str:
    """
    Build Pure Cypher query for graph context retrieval based on intent.

    Uses variable-length patterns for efficient traversal.

    Args:
        intent: QueryIntent determining traversal strategy
        depth: Maximum traversal depth
        relationship_types: Optional registry-sourced edge vocabulary. When supplied
            (mechanism B / Convergence Phase 1), the ``type(r) IN [...]`` filter comes
            from this list — the domain's
            ``DomainRelationshipConfig.cross_domain_relationship_types`` (the single
            source of truth) — instead of the hard-coded per-intent literal. ``intent``
            still selects the downstream shaping; only the edge vocabulary is registry-
            sourced. When ``None`` (any non-supplying caller), the existing intent-based
            hard-coded clauses are used unchanged.

    Returns:
        Pure Cypher query string

    See: /docs/roadmap/intent-traversal-registry-convergence.md
    """
    from core.models.query_types import QueryIntent

    # Registry-sourced vocabulary (Convergence Phase 1, One Path Forward): the edge
    # filter is the registry's relationship set, not a hand-maintained per-intent list
    # that drifts. A ``LIMIT`` cap is ported from the generic EXPLORATORY branch so a
    # domain that surfaces many neighbours cannot regress into an unbounded result.
    if relationship_types:
        return _build_filtered_context_query(depth, relationship_types)

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


def _build_filtered_context_query(depth: int, relationship_types: list[str]) -> str:
    """Build a registry-sourced filtered traversal query (mechanism B).

    The edge filter is the supplied relationship-type list (the domain's registry
    vocabulary), plus a ``LIMIT`` cap guarding against unbounded results now that the
    edge set is the domain's full cross-domain vocabulary, not a narrow literal.

    The cap is applied to matched ``(related, path)`` rows **before** the ``collect``
    aggregation. The generic EXPLORATORY branch's trailing ``LIMIT`` is a no-op (it caps
    the single post-aggregation row, not the collected nodes); for a dense graph over the
    full registry vocabulary that would let the context grow without bound. Limiting the
    path rows first genuinely bounds the materialized node/relationship set. The
    ``OPTIONAL MATCH ... WHERE`` predicate keeps the origin row alive when nothing matches
    (related = null), so a no-edge entity still yields an empty context rather than a
    not-found error.

    The predicate uses ``all`` (not ``any``): a related node is collected only when it
    is reachable by a path whose **every** edge is registry-sourced. ``any`` would leak
    non-registry tails at ``depth > 1`` — a path ``origin-[:REGISTRY]->x-[:NOISE]->y``
    satisfies "some edge is registry" and would wrongly collect ``y`` and ``NOISE``,
    breaking the registry-sourced guarantee. A node still surfaces whenever *some*
    all-registry path reaches it, so transitive registry context (e.g.
    ``origin-[:DEPENDS_ON]->x-[:CONTRIBUTES_TO_GOAL]->goal``) is preserved.

    ``related <> origin`` excludes the origin's own 0-length self-path: ``all`` over its
    empty relationship list is vacuously true, so without this guard the origin would
    leak into its own context (``any`` excluded it implicitly). Mirrors the
    ``related <> center`` self-exclusion in ``get_cross_domain_context``.

    Relationship types are ``RelationshipName`` enum values from the registry (trusted,
    not user input), interpolated the same way ``depth`` is throughout this builder.
    """
    rel_list = ", ".join(f"'{rel_type}'" for rel_type in relationship_types)
    return f"""
    MATCH (origin {{uid: $uid}})
    OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
    WHERE related <> origin
      AND all(r in relationships(path) WHERE type(r) IN [{rel_list}])
    WITH origin, related, relationships(path) as path_rels
    LIMIT 100
    WITH origin, collect(DISTINCT related) as nodes,
         collect(DISTINCT [r in path_rels | {{
             type: type(r),
             start_uid: startNode(r).uid,
             end_uid: endNode(r).uid,
             properties: properties(r)
         }}]) as rels
    RETURN nodes, rels[0] as relationships
    """
