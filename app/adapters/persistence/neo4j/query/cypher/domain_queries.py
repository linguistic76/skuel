"""
Domain Queries - Domain-Specific Dependencies and Context
==========================================================

Query builders for domain-specific dependency chains and entity context.

Sections:
1. Prerequisite Chain Queries - Generic prerequisite traversal
2. Entity With Context - Full graph neighborhood in single query

These methods wrap the semantic queries with domain-specific defaults.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from adapters.persistence.neo4j._backend_helpers import direction_clause
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import Neo4jValue, UserUID

from ._helpers import validate_identifier, validate_label

if TYPE_CHECKING:
    from datetime import date

    from ._types import RelationshipSpec


# =============================================================================
# PREREQUISITE CHAIN QUERIES
# =============================================================================


def build_simple_prerequisite_chain(
    node_uid: str,
    node_label: NeoLabel,
    relationship_type: str,
    depth: int = 3,
    order: str = "DESC",
    include_leaf_only: bool = True,
    min_confidence: float = 0.7,
    min_strength: float = 0.0,
    as_of_date: datetime | None = None,
    include_deprecated: bool = False,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for simple prerequisite chains (domain-agnostic, non-semantic).

    Use this for domain-specific REQUIRES relationships (e.g., KnowledgeUnit REQUIRES,
    Task DEPENDS_ON).

    Args:
        node_uid: Target node UID
        node_label: Node label (e.g., "Entity", "Task", "Goal")
        relationship_type: Relationship type (e.g., "REQUIRES_KNOWLEDGE", "DEPENDS_ON")
        depth: Maximum chain depth (default 3)
        order: "ASC" (shallowest first) or "DESC" (deepest first)
        include_leaf_only: Only return leaf nodes (no further prerequisites)
        min_confidence: Minimum relationship confidence threshold (default 0.7)
        min_strength: Minimum relationship strength threshold (default 0.0)
        as_of_date: Filter relationships valid at this date (default: now)
        include_deprecated: If True, include relationships that are no longer valid

    Returns:
        Tuple of (cypher_query, parameters)
    """
    validate_label(node_label)
    validate_identifier(relationship_type, "relationship type")

    # Build WHERE clauses
    where_clauses = []

    # Confidence + Strength + Temporal filter
    filter_conditions = [
        "coalesce(r.confidence, 1.0) >= $min_confidence",
        "coalesce(r.strength, 1.0) >= $min_strength",
    ]

    # Temporal validity filter
    if not include_deprecated:
        filter_conditions.extend(
            [
                "(r.valid_from IS NULL OR r.valid_from <= $as_of_date)",
                "(r.valid_until IS NULL OR r.valid_until >= $as_of_date)",
            ]
        )

    where_clauses.append(f"all(r IN rs WHERE {' AND '.join(filter_conditions)})")

    # Leaf node filter if requested
    if include_leaf_only:
        where_clauses.append(f"NOT (prereq)-[:{relationship_type}]->()")

    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    cypher = f"""
    MATCH path = (target:{node_label} {{uid: $uid}})-[rs:{relationship_type}*1..{depth}]->(prereq:{node_label})
    {where_clause}
    RETURN DISTINCT prereq, length(path) as depth
    ORDER BY depth {order}
    """

    check_date = as_of_date or datetime.now()

    return cypher.strip(), {
        "uid": node_uid,
        "min_confidence": min_confidence,
        "min_strength": min_strength,
        "as_of_date": check_date,
    }


# =============================================================================
# ENTITY WITH CONTEXT QUERIES
# =============================================================================


def build_entity_with_context(
    entity_label: NeoLabel,
    relationships: list["RelationshipSpec"],
    confidence_param: str | None = "min_confidence",
    default_confidence: float = 0.7,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for fetching an entity with its full graph neighborhood context.

    This helper generates optimized Cypher that fetches an entity plus all its
    related entities in a SINGLE database round-trip, eliminating N+1 query patterns.

    Args:
        entity_label: The Neo4j label for the main entity (e.g., "Task", "Goal")
        relationships: List of relationship specifications
        confidence_param: Parameter name for confidence threshold
        default_confidence: Default confidence value if not provided

    Returns:
        Tuple of (cypher_query, base_parameters)
    """
    validate_label(entity_label)
    for rel in relationships:
        validate_identifier(rel["rel_types"], "relationship type")
        validate_label(rel["target_label"])
        validate_identifier(rel["alias"], "alias")
        for field in rel.get("fields", ["uid", "title"]):
            validate_identifier(field, "field")
        # filter_property is interpolated into Cypher (the value is parameterized).
        filter_property = rel.get("filter_property")
        if filter_property:
            validate_identifier(filter_property, "filter property")

    parts = []
    with_vars = ["entity"]
    return_vars = ["entity"]
    filter_params: dict[str, Neo4jValue] = {}  # edge-property filter values, collected per spec

    # Initial MATCH
    parts.append(f"MATCH (entity:{entity_label} {{uid: $uid}})")

    # Build each relationship clause
    for i, rel in enumerate(relationships):
        rel_types = rel["rel_types"]
        target_label = rel["target_label"]
        alias = rel["alias"]
        direction = rel.get("direction", "outgoing")
        fields = rel.get("fields", ["uid", "title"])
        use_confidence = rel.get("use_confidence", False)
        single = rel.get("single", False)
        limit = rel.get("limit")
        include_rel_type = rel.get("include_rel_type", False)

        # Relationship variable for accessing properties
        rel_var = f"r{i}"

        # Build OPTIONAL MATCH
        parts.append(
            f"OPTIONAL MATCH (entity){direction_clause(direction, rel_var, rel_types)}({alias}_node:{target_label})"
        )

        # Combine all edge predicates into ONE WHERE (Cypher allows a single WHERE per
        # clause): confidence threshold and/or an edge-property filter (e.g. essentiality
        # tier). The filter value is parameterized; its property name was validated above.
        where_conditions = []
        if use_confidence:
            where_conditions.append(f"coalesce({rel_var}.confidence, 1.0) >= ${confidence_param}")
        filter_property = rel.get("filter_property")
        if filter_property:
            filter_param = f"{alias}_filter"
            where_conditions.append(f"{rel_var}.{filter_property} = ${filter_param}")
            filter_params[filter_param] = rel.get("filter_value")
        if where_conditions:
            parts.append(f"WHERE {' AND '.join(where_conditions)}")

        # Build field collection
        field_parts = [f"{field}: {alias}_node.{field}" for field in fields]

        # Add confidence to fields if using confidence
        if use_confidence:
            field_parts.append(f"confidence: coalesce({rel_var}.confidence, 1.0)")

        # Add relationship type if requested
        if include_rel_type:
            field_parts.append(f"relationship_type: type({rel_var})")

        fields_str = ", ".join(field_parts)

        # Build WITH clause
        prev_vars = ", ".join(with_vars)

        if single:
            collect_expr = f"""CASE WHEN {alias}_node IS NOT NULL THEN {{
                {fields_str}
            }} END as {alias}"""
        else:
            collect_expr = f"collect(DISTINCT {{{fields_str}}}) as {alias}"
            if limit:
                collect_expr = f"collect(DISTINCT {{{fields_str}}})[0..{limit}] as {alias}"

        parts.append(f"WITH {prev_vars}, {collect_expr}")

        with_vars.append(alias)
        return_vars.append(alias)

    # Build RETURN
    parts.append(f"RETURN {', '.join(return_vars)}")

    cypher = "\n".join(parts)
    parameters: dict[str, Neo4jValue] = dict(filter_params)

    if any(rel.get("use_confidence", False) for rel in relationships):
        parameters[confidence_param or "min_confidence"] = default_confidence

    return cypher, parameters


def build_task_with_context(
    include_subtasks: bool = True,
    include_dependencies: bool = True,
    include_knowledge: bool = True,
    include_goal: bool = True,
    include_habit: bool = True,
    _include_related: bool = True,
    _related_limit: int = 5,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for Task entity with full graph context.

    Args:
        include_subtasks: Include child tasks (default True)
        include_dependencies: Include blocking/dependent tasks (default True)
        include_knowledge: Include applied/required knowledge (default True)
        include_goal: Include goal context (default True)
        include_habit: Include habit context (default True)
        include_related: Include related tasks (default True)
        related_limit: Max related tasks to return (default 5)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    relationships: list[RelationshipSpec] = []

    if include_subtasks:
        relationships.append(
            {
                # Was "PARENT_OF|CHILD_OF" — neither is a RelationshipName member
                # nor a live edge. The written subtask edge is the inverse leg of
                # _HierarchyMixin's bidirectional pair, (child)-[:SUBTASK_OF]->
                # (parent), which is exactly this spec's "incoming" direction
                # (findings §8). This is a Python-side edge string, so SKUEL030
                # could not see it and it carried no baseline pair.
                "rel_types": "SUBTASK_OF",
                "target_label": NeoLabel.TASK,
                "alias": "subtasks",
                "direction": "incoming",
                "fields": ["uid", "title", "status", "priority"],
            }
        )

    if include_dependencies:
        relationships.append(
            {
                "rel_types": "BLOCKS|DEPENDS_ON",
                "target_label": NeoLabel.TASK,
                "alias": "dependencies",
                "direction": "incoming",
                "fields": ["uid", "title", "status", "priority"],
                "include_rel_type": True,
            }
        )
        relationships.append(
            {
                "rel_types": "BLOCKS|DEPENDS_ON",
                "target_label": NeoLabel.TASK,
                "alias": "dependents",
                "direction": "outgoing",
                "fields": ["uid", "title", "status"],
            }
        )

    if include_knowledge:
        relationships.append(
            {
                "rel_types": "APPLIES_KNOWLEDGE",
                "target_label": NeoLabel.ENTITY,
                "alias": "applied_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
                "use_confidence": True,
            }
        )
        relationships.append(
            {
                "rel_types": "REQUIRES_KNOWLEDGE",
                "target_label": NeoLabel.ENTITY,
                "alias": "required_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
                "use_confidence": True,
            }
        )

    if include_goal:
        relationships.append(
            {
                "rel_types": "FULFILLS_GOAL",
                "target_label": NeoLabel.GOAL,
                "alias": "goal_context",
                "direction": "outgoing",
                "fields": ["uid", "title", "progress_percentage"],
                "single": True,
            }
        )

    if include_habit:
        relationships.append(
            {
                "rel_types": "REINFORCES_HABIT",
                "target_label": NeoLabel.HABIT,
                "alias": "habit_context",
                "direction": "outgoing",
                "fields": ["uid", "title", "current_streak"],
                "single": True,
            }
        )

    return build_entity_with_context(
        entity_label=NeoLabel.TASK,
        relationships=relationships,
    )


def build_goal_with_context(
    include_tasks: bool = True,
    include_habits: bool = True,
    include_subgoals: bool = True,
    include_knowledge: bool = True,
    include_principles: bool = True,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for Goal entity with full graph context.

    Note: milestones are stored as an embedded tuple on Goal
    (`Goal.milestones: tuple[Milestone, ...]`), not as graph nodes — they
    are not traversed by this query.

    Args:
        include_tasks: Include contributing tasks (default True)
        include_habits: Include contributing habits (default True)
        include_subgoals: Include sub-goals (default True)
        include_knowledge: Include required knowledge (default True)
        include_principles: Include aligned principles (default True)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    relationships: list[RelationshipSpec] = []

    if include_tasks:
        relationships.append(
            {
                "rel_types": "FULFILLS_GOAL",
                "target_label": NeoLabel.TASK,
                "alias": "contributing_tasks",
                "direction": "incoming",
                "fields": ["uid", "title", "status", "priority"],
            }
        )

    if include_habits:
        relationships.append(
            {
                "rel_types": "SUPPORTS_GOAL",
                "target_label": NeoLabel.HABIT,
                "alias": "contributing_habits",
                "direction": "incoming",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    if include_subgoals:
        relationships.append(
            {
                "rel_types": "PARENT_GOAL",
                "target_label": NeoLabel.GOAL,
                "alias": "sub_goals",
                "direction": "incoming",
                "fields": ["uid", "title", "status", "progress_percentage"],
            }
        )

    if include_knowledge:
        relationships.append(
            {
                "rel_types": "REQUIRES_KNOWLEDGE",
                "target_label": NeoLabel.ENTITY,
                "alias": "required_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
                "use_confidence": True,
            }
        )

    if include_principles:
        relationships.append(
            {
                "rel_types": "ALIGNED_WITH_PRINCIPLE",
                "target_label": NeoLabel.PRINCIPLE,
                "alias": "aligned_principles",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    return build_entity_with_context(
        entity_label=NeoLabel.GOAL,
        relationships=relationships,
    )


# ============================================================================
# DOMAIN-SPECIFIC BUILD_*_WITH_CONTEXT() FUNCTIONS
# ============================================================================
# These functions provide domain-specific context queries with full control
# over included relationships. They complement the registry-driven approach
# in context_query_generator.py - use these when you need explicit control
# over which relationships to include.
#
# See also: generate_context_query() for registry-driven dynamic generation.
# ============================================================================


def build_ku_with_context(
    include_prerequisites: bool = True,
    include_enables: bool = True,
    include_related: bool = True,
    include_applied_in_tasks: bool = True,
    include_reinforced_by_habits: bool = True,
    include_supports_goals: bool = True,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for KU entity with full graph context.

    Args:
        include_prerequisites: Include prerequisite KUs (default True)
        include_enables: Include KUs this enables (default True)
        include_related: Include related KUs (default True)
        include_applied_in_tasks: Include tasks applying this KU (default True)
        include_reinforced_by_habits: Include habits reinforcing this KU (default True)
        include_supports_goals: Include goals requiring this KU (default True)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    relationships: list[RelationshipSpec] = []

    if include_prerequisites:
        relationships.append(
            {
                "rel_types": "REQUIRES_KNOWLEDGE",
                "target_label": NeoLabel.ENTITY,
                "alias": "prerequisites",
                "direction": "outgoing",
                "fields": ["uid", "title"],
                "use_confidence": True,
            }
        )

    if include_enables:
        relationships.append(
            {
                "rel_types": "ENABLES_KNOWLEDGE",
                "target_label": NeoLabel.ENTITY,
                "alias": "enables_learning",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_related:
        relationships.append(
            {
                "rel_types": "RELATED_TO",
                "target_label": NeoLabel.ENTITY,
                "alias": "related",
                "direction": "both",
                "fields": ["uid", "title"],
            }
        )

    if include_applied_in_tasks:
        relationships.append(
            {
                "rel_types": "APPLIES_KNOWLEDGE",
                "target_label": NeoLabel.TASK,
                "alias": "applied_in_tasks",
                "direction": "incoming",
                "fields": ["uid", "title", "status"],
            }
        )

    if include_reinforced_by_habits:
        relationships.append(
            {
                "rel_types": "REINFORCES_KNOWLEDGE",
                "target_label": NeoLabel.HABIT,
                "alias": "reinforced_by_habits",
                "direction": "incoming",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    if include_supports_goals:
        relationships.append(
            {
                "rel_types": "REQUIRES_KNOWLEDGE",
                "target_label": NeoLabel.GOAL,
                "alias": "supports_goals",
                "direction": "incoming",
                "fields": ["uid", "title", "progress_percentage"],
            }
        )

    return build_entity_with_context(
        entity_label=NeoLabel.ENTITY,
        relationships=relationships,
    )


def build_habit_with_context(
    include_knowledge: bool = True,
    include_principles: bool = True,
    include_goals: bool = True,
    include_prerequisite_habits: bool = True,
    include_reinforcing_habits: bool = True,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for Habit entity with full graph context.

    Args:
        include_knowledge: Include reinforced knowledge (default True)
        include_principles: Include embodied principles (default True)
        include_goals: Include supported goals (default True)
        include_prerequisite_habits: Include prerequisite habits (default True)
        include_reinforcing_habits: Include habits that reinforce this one (default True)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    relationships: list[RelationshipSpec] = []

    if include_knowledge:
        relationships.append(
            {
                "rel_types": "REINFORCES_KNOWLEDGE",
                "target_label": NeoLabel.ENTITY,
                "alias": "reinforced_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_principles:
        relationships.append(
            {
                "rel_types": "EMBODIES_PRINCIPLE",
                "target_label": NeoLabel.PRINCIPLE,
                "alias": "embodied_principles",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_goals:
        relationships.append(
            {
                "rel_types": "SUPPORTS_GOAL",
                "target_label": NeoLabel.GOAL,
                "alias": "supported_goals",
                "direction": "outgoing",
                "fields": ["uid", "title", "progress_percentage"],
            }
        )

    if include_prerequisite_habits:
        relationships.append(
            {
                "rel_types": "REQUIRES_PREREQUISITE_HABIT",
                "target_label": NeoLabel.HABIT,
                "alias": "prerequisite_habits",
                "direction": "outgoing",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    if include_reinforcing_habits:
        relationships.append(
            {
                "rel_types": "REINFORCES_HABIT",
                "target_label": NeoLabel.HABIT,
                "alias": "reinforcing_habits",
                "direction": "incoming",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    return build_entity_with_context(
        entity_label=NeoLabel.HABIT,
        relationships=relationships,
    )


def build_event_with_context(
    include_knowledge: bool = True,
    include_goals: bool = True,
    include_habits: bool = True,
    include_practiced_habits: bool = True,
    include_celebrated_goals: bool = True,
    include_conflicting_events: bool = True,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for Event entity with full graph context.

    Args:
        include_knowledge: Include applied knowledge (default True)
        include_goals: Include supported goals (default True)
        include_habits: Include reinforced habits (default True)
        include_practiced_habits: Include habits practiced at this event (default True)
        include_celebrated_goals: Include goals celebrated by this event (default True)
        include_conflicting_events: Include conflicting events (default True)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    relationships: list[RelationshipSpec] = []

    if include_knowledge:
        relationships.append(
            {
                "rel_types": "APPLIES_KNOWLEDGE",
                "target_label": NeoLabel.ENTITY,
                "alias": "applied_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_goals:
        relationships.append(
            {
                "rel_types": "CONTRIBUTES_TO_GOAL",
                "target_label": NeoLabel.GOAL,
                "alias": "supported_goals",
                "direction": "outgoing",
                "fields": ["uid", "title", "progress_percentage"],
            }
        )

    if include_habits:
        relationships.append(
            {
                "rel_types": "REINFORCES_HABIT",
                "target_label": NeoLabel.HABIT,
                "alias": "reinforced_habits",
                "direction": "outgoing",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    if include_practiced_habits:
        relationships.append(
            {
                "rel_types": "PRACTICED_AT_EVENT",
                "target_label": NeoLabel.HABIT,
                "alias": "practiced_habits",
                "direction": "incoming",
                "fields": ["uid", "title"],
            }
        )

    if include_celebrated_goals:
        relationships.append(
            {
                "rel_types": "CELEBRATES_GOAL",
                "target_label": NeoLabel.GOAL,
                "alias": "celebrated_goals",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_conflicting_events:
        relationships.append(
            {
                "rel_types": "CONFLICTS_WITH",
                "target_label": NeoLabel.EVENT,
                "alias": "conflicting_events",
                "direction": "both",
                "fields": ["uid", "title", "scheduled_for"],
            }
        )

    return build_entity_with_context(
        entity_label=NeoLabel.EVENT,
        relationships=relationships,
    )


def build_choice_with_context(
    include_knowledge: bool = True,
    include_principles: bool = True,
    include_goals: bool = True,
    include_learning_paths: bool = True,
    include_inspired_choices: bool = True,
    include_implementing_tasks: bool = True,
    include_guiding_principles: bool = True,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for Choice entity with full graph context.

    Args:
        include_knowledge: Include informed-by knowledge (default True)
        include_principles: Include aligned principles (default True)
        include_goals: Include affected goals (default True)
        include_learning_paths: Include opened learning paths (default True)
        include_inspired_choices: Include choices inspired by this one (default True)
        include_implementing_tasks: Include tasks implementing this choice (default True)
        include_guiding_principles: Include principles guiding this choice (default True)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    relationships: list[RelationshipSpec] = []

    if include_knowledge:
        relationships.append(
            {
                "rel_types": "INFORMED_BY_KNOWLEDGE",
                "target_label": NeoLabel.ENTITY,
                "alias": "informed_by_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_principles:
        relationships.append(
            {
                "rel_types": "INFORMED_BY_PRINCIPLE",
                "target_label": NeoLabel.PRINCIPLE,
                "alias": "aligned_principles",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_goals:
        relationships.append(
            {
                "rel_types": "AFFECTS_GOAL",
                "target_label": NeoLabel.GOAL,
                "alias": "affected_goals",
                "direction": "outgoing",
                "fields": ["uid", "title", "progress_percentage"],
            }
        )

    if include_learning_paths:
        relationships.append(
            {
                "rel_types": "OPENS_LEARNING_PATH",
                "target_label": NeoLabel.LEARNING_PATH,
                "alias": "opened_paths",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_inspired_choices:
        relationships.append(
            {
                "rel_types": "INSPIRED_BY_CHOICE",
                "target_label": NeoLabel.CHOICE,
                "alias": "inspired_choices",
                "direction": "incoming",
                "fields": ["uid", "title"],
            }
        )

    if include_implementing_tasks:
        relationships.append(
            {
                "rel_types": "IMPLEMENTS_CHOICE",
                "target_label": NeoLabel.TASK,
                "alias": "implementing_tasks",
                "direction": "incoming",
                "fields": ["uid", "title", "status"],
            }
        )

    if include_guiding_principles:
        relationships.append(
            {
                "rel_types": "GUIDES_CHOICE",
                "target_label": NeoLabel.PRINCIPLE,
                "alias": "guiding_principles",
                "direction": "incoming",
                "fields": ["uid", "title"],
            }
        )

    return build_entity_with_context(
        entity_label=NeoLabel.CHOICE,
        relationships=relationships,
    )


def build_principle_with_context(
    include_knowledge: bool = True,
    include_goals: bool = True,
    include_choices: bool = True,
    include_habits: bool = True,
    include_embodying_habits: bool = True,
    include_supporting_principles: bool = True,
    include_conflicting_principles: bool = True,
    include_aligned_tasks: bool = True,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for Principle entity with full graph context.

    Args:
        include_knowledge: Include grounding knowledge (default True)
        include_goals: Include guided goals (default True)
        include_choices: Include guided choices (default True)
        include_habits: Include inspired habits (default True)
        include_embodying_habits: Include habits embodying this principle (default True)
        include_supporting_principles: Include supporting principles (default True)
        include_conflicting_principles: Include conflicting principles (default True)
        include_aligned_tasks: Include tasks aligned with this principle (default True)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    relationships: list[RelationshipSpec] = []

    if include_knowledge:
        relationships.append(
            {
                "rel_types": "GROUNDED_IN_KNOWLEDGE",
                "target_label": NeoLabel.ENTITY,
                "alias": "grounding_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_goals:
        relationships.append(
            {
                "rel_types": "GUIDES_GOAL",
                "target_label": NeoLabel.GOAL,
                "alias": "guided_goals",
                "direction": "outgoing",
                "fields": ["uid", "title", "progress_percentage"],
            }
        )

    if include_choices:
        relationships.append(
            {
                "rel_types": "GUIDES_CHOICE",
                "target_label": NeoLabel.CHOICE,
                "alias": "guided_choices",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_habits:
        relationships.append(
            {
                "rel_types": "INSPIRES_HABIT",
                "target_label": NeoLabel.HABIT,
                "alias": "inspired_habits",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_embodying_habits:
        relationships.append(
            {
                "rel_types": "EMBODIES_PRINCIPLE",
                "target_label": NeoLabel.HABIT,
                "alias": "embodying_habits",
                "direction": "incoming",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    if include_supporting_principles:
        relationships.append(
            {
                "rel_types": "SUPPORTS_PRINCIPLE",
                "target_label": NeoLabel.PRINCIPLE,
                "alias": "supporting_principles",
                "direction": "incoming",
                "fields": ["uid", "title"],
            }
        )

    if include_conflicting_principles:
        relationships.append(
            {
                "rel_types": "CONFLICTS_WITH_PRINCIPLE",
                "target_label": NeoLabel.PRINCIPLE,
                "alias": "conflicting_principles",
                "direction": "incoming",
                "fields": ["uid", "title"],
            }
        )

    if include_aligned_tasks:
        relationships.append(
            {
                "rel_types": "ALIGNED_WITH_PRINCIPLE",
                "target_label": NeoLabel.TASK,
                "alias": "aligned_tasks",
                "direction": "incoming",
                "fields": ["uid", "title", "status"],
            }
        )

    return build_entity_with_context(
        entity_label=NeoLabel.PRINCIPLE,
        relationships=relationships,
    )


# ============================================================================
# META-SERVICE QUERY HELPERS
# ============================================================================


def build_user_activity_query(
    user_uid: UserUID,
    node_label: NeoLabel,
    date_field: str | None = None,
    start_date: "date | None" = None,
    end_date: "date | None" = None,
    exclude_statuses: list[str] | None = None,
    limit: int = 100,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for user's activity items with common filters.

    Generic query builder for ALL activity domains (Tasks, Habits, Goals, Events,
    Finance, Choices, Principles). Designed for meta-services (Calendar, Reports)
    that need consistent querying across domains.

    Args:
        user_uid: User UID
        node_label: Node label (e.g., "Task", "Habit", "Event")
        date_field: Field to filter by date ("due_date", "scheduled_for", etc.)
        start_date: Start of date range
        end_date: End of date range
        exclude_statuses: Status values to exclude (e.g., ["completed", "cancelled"])
        limit: Maximum results (default 100)

    Returns:
        Tuple of (cypher_query, parameters)

    Examples:
        # Get user's active tasks in date range
        query, params = build_user_activity_query(
            user_uid="user.mike",
            node_label="Task",
            date_field="due_date",
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 31),
            exclude_statuses=["completed"]
        )

        # Get user's active habits (no date filter)
        query, params = build_user_activity_query(
            user_uid="user.mike",
            node_label="Habit",
            exclude_statuses=["archived"]
        )
    """
    validate_label(node_label)
    if date_field:
        validate_identifier(date_field, "date field")

    # Build WHERE clauses
    where_clauses = ["n.user_uid = $user_uid"]

    # Date range filtering (if provided)
    if date_field and start_date and end_date:
        # left(toString(...), 10) takes the YYYY-MM-DD prefix before date() so the
        # comparison is date-vs-date, not string-vs-date (Neo4j evaluates the latter
        # to null → the row is silently dropped). Bare date() on a *datetime* string
        # ("2026-06-17T09:00") THROWS ("Text cannot be parsed to a Date"), taking the
        # whole range query down (see #766); the prefix tolerates every storage shape
        # — date/datetime temporal types and date-only/datetime strings alike.
        where_clauses.append(f"date(left(toString(n.{date_field}), 10)) >= date($start_date)")
        where_clauses.append(f"date(left(toString(n.{date_field}), 10)) <= date($end_date)")

    # Status filtering (if provided)
    if exclude_statuses:
        where_clauses.append("NOT n.status IN $exclude_statuses")

    where_clause = " AND ".join(where_clauses)

    # Build query
    cypher = f"""
    MATCH (n:{node_label})
    WHERE {where_clause}
    RETURN n
    ORDER BY n.created_at DESC
    LIMIT $limit
    """

    # Build parameters
    params: dict[str, Neo4jValue] = {"user_uid": user_uid, "limit": limit}

    if date_field and start_date and end_date:
        params["start_date"] = start_date.isoformat()
        params["end_date"] = end_date.isoformat()

    if exclude_statuses:
        params["exclude_statuses"] = exclude_statuses  # type: ignore[assignment]  # list[str] is subtype at runtime; Neo4jValue uses list[str | int | float]

    return cypher.strip(), params


# =============================================================================
# TIME-BASED QUERIES (Due Soon / Overdue)
# =============================================================================


def build_due_soon_query(
    node_label: NeoLabel,
    date_field: str,
    days_ahead: int = 7,
    exclude_statuses: list[str] | None = None,
    user_uid: UserUID | None = None,
    limit: int = 100,
    secondary_sort_field: str | None = None,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for entities due within N days.

    Used by TimeQueryMixin.get_upcoming() for all Activity Domains.

    Args:
        node_label: Neo4j node label (e.g., "Task", "Goal", "Event")
        date_field: Date field to check (e.g., "due_date", "target_date")
        days_ahead: Number of days to look ahead (default 7)
        exclude_statuses: Statuses to exclude (e.g., ["completed", "cancelled"])
        user_uid: Optional user UID for ownership filter
        limit: Maximum results
        secondary_sort_field: Optional secondary sort field (e.g., "start_time")

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        >>> query, params = build_due_soon_query(
        ...     node_label="Task",
        ...     date_field="due_date",
        ...     days_ahead=7,
        ...     exclude_statuses=["completed"],
        ...     user_uid="user.mike",
        ... )
    """
    from datetime import date, timedelta

    validate_label(node_label)
    validate_identifier(date_field, "date field")
    if secondary_sort_field:
        validate_identifier(secondary_sort_field, "sort field")

    today = date.today()
    end_date = today + timedelta(days=days_ahead)

    # date(left(toString(...), 10)) coerces ISO date/datetime strings — see build_user_activity_query
    where_clauses = [
        f"date(left(toString(n.{date_field}), 10)) >= date($today)",
        f"date(left(toString(n.{date_field}), 10)) <= date($end_date)",
    ]

    if exclude_statuses:
        where_clauses.append("NOT n.status IN $exclude_statuses")

    if user_uid:
        where_clauses.append("n.user_uid = $user_uid")

    where_clause = " AND ".join(where_clauses)

    # Sort by date ASC (nearest first), with optional secondary sort
    order_clause = f"n.{date_field} ASC"
    if secondary_sort_field:
        order_clause += f", n.{secondary_sort_field} ASC"

    cypher = f"""
    MATCH (n:{node_label})
    WHERE {where_clause}
    RETURN n
    ORDER BY {order_clause}
    LIMIT $limit
    """

    params: dict[str, Neo4jValue] = {
        "today": today.isoformat(),
        "end_date": end_date.isoformat(),
        "limit": limit,
    }

    if exclude_statuses:
        params["exclude_statuses"] = exclude_statuses  # type: ignore[assignment]  # list[str] is subtype at runtime; Neo4jValue uses list[str | int | float]
    if user_uid:
        params["user_uid"] = user_uid

    return cypher.strip(), params


def build_overdue_query(
    node_label: NeoLabel,
    date_field: str,
    exclude_statuses: list[str] | None = None,
    user_uid: UserUID | None = None,
    limit: int = 100,
    secondary_sort_field: str | None = None,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for entities past their due date.

    Used by BaseService.get_overdue() for all Activity Domains.

    Args:
        node_label: Neo4j node label (e.g., "Task", "Goal", "Event")
        date_field: Date field to check (e.g., "due_date", "target_date")
        exclude_statuses: Statuses to exclude (e.g., ["completed", "cancelled"])
        user_uid: Optional user UID for ownership filter
        limit: Maximum results
        secondary_sort_field: Optional secondary sort field (e.g., "start_time")

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        >>> query, params = build_overdue_query(
        ...     node_label="Task",
        ...     date_field="due_date",
        ...     exclude_statuses=["completed"],
        ...     user_uid="user.mike",
        ...     limit=50,
        ... )
    """
    from datetime import date

    validate_label(node_label)
    validate_identifier(date_field, "date field")
    if secondary_sort_field:
        validate_identifier(secondary_sort_field, "sort field")

    today = date.today()

    # date(left(toString(...), 10)) coerces ISO date/datetime strings — see build_user_activity_query
    where_clauses = [
        f"date(left(toString(n.{date_field}), 10)) < date($today)",
    ]

    if exclude_statuses:
        where_clauses.append("NOT n.status IN $exclude_statuses")

    if user_uid:
        where_clauses.append("n.user_uid = $user_uid")

    where_clause = " AND ".join(where_clauses)

    # Sort by date ASC (oldest/most overdue first), with optional secondary sort
    order_clause = f"n.{date_field} ASC"
    if secondary_sort_field:
        order_clause += f", n.{secondary_sort_field} ASC"

    cypher = f"""
    MATCH (n:{node_label})
    WHERE {where_clause}
    RETURN n
    ORDER BY {order_clause}
    LIMIT $limit
    """

    params: dict[str, Neo4jValue] = {
        "today": today.isoformat(),
        "limit": limit,
    }

    if exclude_statuses:
        params["exclude_statuses"] = exclude_statuses  # type: ignore[assignment]  # list[str] is subtype at runtime; Neo4jValue uses list[str | int | float]
    if user_uid:
        params["user_uid"] = user_uid

    return cypher.strip(), params


def build_active_query(
    node_label: NeoLabel,
    user_uid: UserUID,
    exclude_statuses: list[str] | None = None,
    limit: int = 100,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Build query for active (non-terminal) entities owned by a user.

    Used by TimeQueryMixin.get_active() for all Activity Domains. Active means the
    entity's status is NOT in exclude_statuses (terminal states). Entities without
    a status are included (null-safe).

    Args:
        node_label: Neo4j node label (e.g., "Task", "Goal", "Event")
        user_uid: Owner UID — traversed via (u:User)-[:OWNS]->(n)
        exclude_statuses: Terminal statuses to exclude (e.g., ["completed", "cancelled"])
        limit: Maximum results

    Returns:
        Tuple of (cypher_query, parameters)
    """
    validate_label(node_label)

    where_clauses: list[str] = []

    if exclude_statuses:
        where_clauses.append("(n.status IS NULL OR NOT n.status IN $exclude_statuses)")

    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    cypher = f"""
    MATCH (u:User {{uid: $user_uid}})-[:OWNS]->(n:{node_label})
    {where_clause}
    RETURN n
    ORDER BY n.created_at DESC
    LIMIT $limit
    """

    params: dict[str, Neo4jValue] = {
        "user_uid": user_uid,
        "limit": limit,
    }

    if exclude_statuses:
        params["exclude_statuses"] = exclude_statuses  # type: ignore[assignment]  # list[str] is subtype at runtime; Neo4jValue uses list[str | int | float]

    return cypher.strip(), params
