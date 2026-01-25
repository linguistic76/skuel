"""
Domain Queries - Domain-Specific Dependencies and Context
==========================================================

Query builders for domain-specific dependency chains and entity context.

Sections:
1. Prerequisite Chain Queries - Generic prerequisite traversal
2. Domain-Specific Dependencies - Task, Goal, Habit, Event, Choice, Principle dependencies
3. Entity With Context - Full graph neighborhood in single query

These methods wrap the semantic queries with domain-specific defaults.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import date

    from ._types import RelationshipSpec


# =============================================================================
# PREREQUISITE CHAIN QUERIES
# =============================================================================


def build_simple_prerequisite_chain(
    node_uid: str,
    node_label: str,
    relationship_type: str,
    depth: int = 3,
    order: str = "DESC",
    include_leaf_only: bool = True,
    min_confidence: float = 0.7,
    min_strength: float = 0.0,
    as_of_date: datetime | None = None,
    include_deprecated: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for simple prerequisite chains (domain-agnostic, non-semantic).

    Use this for domain-specific REQUIRES relationships (e.g., KnowledgeUnit REQUIRES,
    Task DEPENDS_ON).

    Args:
        node_uid: Target node UID
        node_label: Node label (e.g., "Ku", "Task", "Goal")
        relationship_type: Relationship type (e.g., "REQUIRES", "DEPENDS_ON")
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


def build_unmastered_prerequisite_chain(
    node_uid: str,
    user_uid: str,
    node_label: str = "Ku",
    relationship_type: str = "REQUIRES",
    mastery_relationship: str = "MASTERED_BY",
    depth: int = 3,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for prerequisites not yet mastered by user.

    Useful for identifying learning gaps and blockers.

    Args:
        node_uid: Target node UID
        user_uid: User UID to check mastery
        node_label: Node label (default "Ku")
        relationship_type: Prerequisite relationship type (default "REQUIRES")
        mastery_relationship: User mastery relationship (default "MASTERED_BY")
        depth: Maximum chain depth (default 3)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    cypher = f"""
    MATCH path = (target:{node_label} {{uid: $target_uid}})<-[:{relationship_type}*1..{depth}]-(prereq:{node_label})
    WHERE NOT (prereq)-[:{mastery_relationship}]->(:User {{uid: $user_uid}})
    RETURN prereq, length(path) as depth
    ORDER BY depth ASC
    """

    return cypher.strip(), {"target_uid": node_uid, "user_uid": user_uid}


def build_multi_domain_context(
    start_uid: str,
    start_label: str,
    relationship_types: list[str],
    depth: int = 3,
    bidirectional: bool = True,
    include_relationships: bool = True,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for multi-domain neighborhood traversal.

    Traverses multiple relationship types simultaneously to gather comprehensive
    context around a node.

    Args:
        start_uid: Starting node UID
        start_label: Starting node label (e.g., "User", "Task", "Ku")
        relationship_types: List of relationship types to traverse
        depth: Maximum traversal depth (default 3)
        bidirectional: Include both directions (default True)
        include_relationships: Return relationship metadata (default True)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    # Build relationship pattern
    rel_pattern = "|".join(relationship_types)

    # Build direction arrow
    direction = "" if bidirectional else ">"

    # Build relationship return clause
    rel_return = ""
    if include_relationships:
        rel_return = ", collect(DISTINCT relationships(path)) as relationships"

    cypher = f"""
    MATCH (start:{start_label} {{uid: $start_uid}})
    OPTIONAL MATCH path = (start)-[:{rel_pattern}*1..{depth}]-{direction}(related)
    WITH start, collect(DISTINCT related) as related_nodes{rel_return}
    RETURN
        start,
        related_nodes,
        size(related_nodes) as node_count
        {", relationships" if include_relationships else ""}
    """

    return cypher.strip(), {"start_uid": start_uid}


# =============================================================================
# DOMAIN-SPECIFIC DEPENDENCY WRAPPERS
# =============================================================================


def build_knowledge_prerequisites(
    ku_uid: str, user_uid: str | None = None, depth: int = 3, include_optional: bool = False
) -> tuple[str, dict[str, Any]]:
    """
    Build query for knowledge unit prerequisites (domain-specific convenience).

    Args:
        ku_uid: Knowledge unit UID
        user_uid: Optional user UID for mastery filtering
        depth: Maximum prerequisite chain depth (default 3)
        include_optional: Include optional prerequisites (default False, leaf-only)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    if user_uid:
        return build_unmastered_prerequisite_chain(
            node_uid=ku_uid,
            user_uid=user_uid,
            node_label="Ku",
            relationship_type="REQUIRES",
            mastery_relationship="MASTERED_BY",
            depth=depth,
        )
    else:
        return build_simple_prerequisite_chain(
            node_uid=ku_uid,
            node_label="Ku",
            relationship_type="REQUIRES",
            depth=depth,
            order="DESC",
            include_leaf_only=not include_optional,
        )


def build_task_dependencies(
    task_uid: str,
    direction: str = "prerequisites",
    depth: int = 2,
    include_all_levels: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for task dependency chains.

    Args:
        task_uid: Task UID
        direction: "prerequisites" (what this depends on) or "dependents" (what depends on this)
        depth: Maximum chain depth (default 2)
        include_all_levels: Include all chain levels, not just leaf nodes

    Returns:
        Tuple of (cypher_query, parameters)
    """
    if direction == "prerequisites":
        return build_simple_prerequisite_chain(
            node_uid=task_uid,
            node_label="Task",
            relationship_type="DEPENDS_ON",
            depth=depth,
            order="ASC",
            include_leaf_only=not include_all_levels,
        )
    elif direction == "dependents":
        leaf_filter = ""
        if not include_all_levels:
            leaf_filter = "WHERE NOT (dependent)<-[:DEPENDS_ON]-()"

        cypher = f"""
        MATCH path = (task:Task {{uid: $uid}})<-[:DEPENDS_ON*1..{depth}]-(dependent:Task)
        {leaf_filter}
        RETURN DISTINCT dependent, length(path) as depth
        ORDER BY depth ASC
        """

        return cypher.strip(), {"uid": task_uid}
    else:
        raise ValueError(f"Invalid direction: {direction}. Use 'prerequisites' or 'dependents'")


def build_goal_dependencies(
    goal_uid: str,
    direction: str = "prerequisites",
    depth: int = 3,
    include_subgoals: bool = True,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for goal dependency chains.

    Args:
        goal_uid: Goal UID
        direction: "prerequisites" (required goals) or "dependents" (goals this enables)
        depth: Maximum chain depth (default 3)
        include_subgoals: Include subgoal relationships in addition to DEPENDS_ON

    Returns:
        Tuple of (cypher_query, parameters)
    """
    if include_subgoals:
        if direction == "prerequisites":
            return build_multi_domain_context(
                start_uid=goal_uid,
                start_label="Goal",
                relationship_types=["DEPENDS_ON", "PART_OF"],
                depth=depth,
                bidirectional=False,
                include_relationships=True,
            )
        else:
            return build_multi_domain_context(
                start_uid=goal_uid,
                start_label="Goal",
                relationship_types=["DEPENDS_ON", "HAS_SUBGOAL"],
                depth=depth,
                bidirectional=False,
                include_relationships=True,
            )
    else:
        if direction == "prerequisites":
            return build_simple_prerequisite_chain(
                node_uid=goal_uid,
                node_label="Goal",
                relationship_type="DEPENDS_ON",
                depth=depth,
                order="ASC",
                include_leaf_only=True,
            )
        else:
            cypher = f"""
            MATCH path = (goal:Goal {{uid: $uid}})<-[:DEPENDS_ON*1..{depth}]-(dependent:Goal)
            WHERE NOT (dependent)<-[:DEPENDS_ON]-()
            RETURN DISTINCT dependent, length(path) as depth
            ORDER BY depth ASC
            """
            return cypher.strip(), {"uid": goal_uid}


def build_habit_dependencies(
    habit_uid: str,
    user_uid: str | None = None,
    direction: str = "prerequisites",
    depth: int = 2,
    include_all_levels: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for habit dependency chains.

    Args:
        habit_uid: Habit UID
        user_uid: Optional user UID for filtering by established habits
        direction: "prerequisites" (foundation habits) or "dependents" (advanced habits)
        depth: Maximum chain depth (default 2)
        include_all_levels: Include all chain levels, not just leaf nodes

    Returns:
        Tuple of (cypher_query, parameters)
    """
    if user_uid:
        if direction == "prerequisites":
            cypher = f"""
            MATCH path = (habit:Habit {{uid: $habit_uid}})-[:REQUIRES*1..{depth}]->(prereq:Habit)
            WHERE NOT (prereq)<-[:PRACTICES]-(:User {{uid: $user_uid}})
            RETURN prereq, length(path) as depth
            ORDER BY depth ASC
            """
            return cypher.strip(), {"habit_uid": habit_uid, "user_uid": user_uid}
        else:
            cypher = f"""
            MATCH path = (habit:Habit {{uid: $habit_uid}})<-[:REQUIRES*1..{depth}]-(dependent:Habit)
            WHERE NOT (dependent)<-[:PRACTICES]-(:User {{uid: $user_uid}})
            RETURN dependent, length(path) as depth
            ORDER BY depth ASC
            """
            return cypher.strip(), {"habit_uid": habit_uid, "user_uid": user_uid}
    else:
        if direction == "prerequisites":
            return build_simple_prerequisite_chain(
                node_uid=habit_uid,
                node_label="Habit",
                relationship_type="REQUIRES",
                depth=depth,
                order="ASC",
                include_leaf_only=not include_all_levels,
            )
        else:
            leaf_filter = ""
            if not include_all_levels:
                leaf_filter = "WHERE NOT (dependent)<-[:REQUIRES]-()"

            cypher = f"""
            MATCH path = (habit:Habit {{uid: $uid}})<-[:REQUIRES*1..{depth}]-(dependent:Habit)
            {leaf_filter}
            RETURN DISTINCT dependent, length(path) as depth
            ORDER BY depth ASC
            """
            return cypher.strip(), {"uid": habit_uid}


def build_event_dependencies(
    event_uid: str,
    user_uid: str | None = None,
    direction: str = "prerequisites",
    depth: int = 2,
    include_all_levels: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for event dependency chains.

    Args:
        event_uid: Event UID
        user_uid: Optional user UID for filtering by attended events
        direction: "prerequisites" (required events) or "dependents" (unlocked events)
        depth: Maximum chain depth (default 2)
        include_all_levels: Include all chain levels, not just leaf nodes

    Returns:
        Tuple of (cypher_query, parameters)
    """
    if user_uid:
        if direction == "prerequisites":
            cypher = f"""
            MATCH path = (event:Event {{uid: $event_uid}})-[:REQUIRES*1..{depth}]->(prereq:Event)
            WHERE NOT (prereq)<-[:ATTENDED]-(:User {{uid: $user_uid}})
            RETURN prereq, length(path) as depth
            ORDER BY depth ASC
            """
            return cypher.strip(), {"event_uid": event_uid, "user_uid": user_uid}
        else:
            cypher = f"""
            MATCH path = (event:Event {{uid: $event_uid}})<-[:REQUIRES*1..{depth}]-(dependent:Event)
            WHERE NOT (dependent)<-[:ATTENDED]-(:User {{uid: $user_uid}})
            RETURN dependent, length(path) as depth
            ORDER BY depth ASC
            """
            return cypher.strip(), {"event_uid": event_uid, "user_uid": user_uid}
    else:
        if direction == "prerequisites":
            return build_simple_prerequisite_chain(
                node_uid=event_uid,
                node_label="Event",
                relationship_type="REQUIRES",
                depth=depth,
                order="ASC",
                include_leaf_only=not include_all_levels,
            )
        else:
            leaf_filter = ""
            if not include_all_levels:
                leaf_filter = "WHERE NOT (dependent)<-[:REQUIRES]-()"

            cypher = f"""
            MATCH path = (event:Event {{uid: $uid}})<-[:REQUIRES*1..{depth}]-(dependent:Event)
            {leaf_filter}
            RETURN DISTINCT dependent, length(path) as depth
            ORDER BY depth ASC
            """
            return cypher.strip(), {"uid": event_uid}


def build_principle_dependencies(
    principle_uid: str,
    user_uid: str | None = None,
    depth: int = 3,
    include_optional: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for principle dependency chains.

    Args:
        principle_uid: Principle UID
        user_uid: Optional user UID for filtering by adopted principles
        depth: Maximum chain depth (default 3)
        include_optional: Include optional prerequisites (default False, leaf-only)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    if user_uid:
        cypher = f"""
        MATCH path = (principle:Principle {{uid: $principle_uid}})-[:REQUIRES*1..{depth}]->(prereq:Principle)
        WHERE NOT (prereq)<-[:ADHERES_TO]-(:User {{uid: $user_uid}})
        RETURN prereq, length(path) as depth
        ORDER BY depth ASC
        """
        return cypher.strip(), {"principle_uid": principle_uid, "user_uid": user_uid}
    else:
        return build_simple_prerequisite_chain(
            node_uid=principle_uid,
            node_label="Principle",
            relationship_type="REQUIRES",
            depth=depth,
            order="DESC",
            include_leaf_only=not include_optional,
        )


def build_choice_dependencies(
    choice_uid: str,
    user_uid: str | None = None,
    direction: str = "prerequisites",
    depth: int = 2,
    include_all_levels: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for choice dependency chains.

    Args:
        choice_uid: Choice UID
        user_uid: Optional user UID for filtering by made choices
        direction: "prerequisites" (required decisions) or "dependents" (unlocked decisions)
        depth: Maximum chain depth (default 2)
        include_all_levels: Include all chain levels, not just leaf nodes

    Returns:
        Tuple of (cypher_query, parameters)
    """
    if user_uid:
        if direction == "prerequisites":
            cypher = f"""
            MATCH path = (choice:Choice {{uid: $choice_uid}})-[:REQUIRES*1..{depth}]->(prereq:Choice)
            WHERE NOT (prereq)<-[:MADE_CHOICE]-(:User {{uid: $user_uid}})
            RETURN prereq, length(path) as depth
            ORDER BY depth ASC
            """
            return cypher.strip(), {"choice_uid": choice_uid, "user_uid": user_uid}
        else:
            cypher = f"""
            MATCH path = (choice:Choice {{uid: $choice_uid}})<-[:REQUIRES*1..{depth}]-(dependent:Choice)
            WHERE NOT (dependent)<-[:MADE_CHOICE]-(:User {{uid: $user_uid}})
            RETURN dependent, length(path) as depth
            ORDER BY depth ASC
            """
            return cypher.strip(), {"choice_uid": choice_uid, "user_uid": user_uid}
    else:
        if direction == "prerequisites":
            return build_simple_prerequisite_chain(
                node_uid=choice_uid,
                node_label="Choice",
                relationship_type="REQUIRES",
                depth=depth,
                order="ASC",
                include_leaf_only=not include_all_levels,
            )
        else:
            leaf_filter = ""
            if not include_all_levels:
                leaf_filter = "WHERE NOT (dependent)<-[:REQUIRES]-()"

            cypher = f"""
            MATCH path = (choice:Choice {{uid: $uid}})<-[:REQUIRES*1..{depth}]-(dependent:Choice)
            {leaf_filter}
            RETURN DISTINCT dependent, length(path) as depth
            ORDER BY depth ASC
            """
            return cypher.strip(), {"uid": choice_uid}


# =============================================================================
# ENTITY WITH CONTEXT QUERIES
# =============================================================================


def build_entity_with_context(
    entity_label: str,
    relationships: list["RelationshipSpec"],
    confidence_param: str | None = "min_confidence",
    default_confidence: float = 0.7,
) -> tuple[str, dict[str, Any]]:
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
    parts = []
    with_vars = ["entity"]
    return_vars = ["entity"]

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

        # Build direction arrows
        if direction == "incoming":
            arrow_left, arrow_right = "<-", "-"
        elif direction == "outgoing":
            arrow_left, arrow_right = "-", "->"
        else:  # both
            arrow_left, arrow_right = "-", "-"

        # Relationship variable for accessing properties
        rel_var = f"r{i}"

        # Build OPTIONAL MATCH
        parts.append(
            f"OPTIONAL MATCH (entity){arrow_left}[{rel_var}:{rel_types}]{arrow_right}({alias}_node:{target_label})"
        )

        # Confidence filter if needed
        if use_confidence:
            parts.append(f"WHERE coalesce({rel_var}.confidence, 1.0) >= ${confidence_param}")

        # Build field collection
        field_parts = []
        for field in fields:
            field_parts.append(f"{field}: {alias}_node.{field}")

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
    parameters: dict[str, Any] = {}

    if any(rel.get("use_confidence", False) for rel in relationships):
        parameters[confidence_param or "min_confidence"] = default_confidence

    return cypher, parameters


def build_task_with_context(
    include_subtasks: bool = True,
    include_dependencies: bool = True,
    include_knowledge: bool = True,
    include_goal: bool = True,
    include_habit: bool = True,
    include_related: bool = True,
    related_limit: int = 5,
) -> tuple[str, dict[str, Any]]:
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
                "rel_types": "PARENT_OF|CHILD_OF",
                "target_label": "Task",
                "alias": "subtasks",
                "direction": "incoming",
                "fields": ["uid", "title", "status", "priority"],
            }
        )

    if include_dependencies:
        relationships.append(
            {
                "rel_types": "BLOCKS|DEPENDS_ON",
                "target_label": "Task",
                "alias": "dependencies",
                "direction": "incoming",
                "fields": ["uid", "title", "status", "priority"],
                "include_rel_type": True,
            }
        )
        relationships.append(
            {
                "rel_types": "BLOCKS|DEPENDS_ON",
                "target_label": "Task",
                "alias": "dependents",
                "direction": "outgoing",
                "fields": ["uid", "title", "status"],
            }
        )

    if include_knowledge:
        relationships.append(
            {
                "rel_types": "APPLIES_KNOWLEDGE",
                "target_label": "Ku",
                "alias": "applied_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
                "use_confidence": True,
            }
        )
        relationships.append(
            {
                "rel_types": "REQUIRES_KNOWLEDGE",
                "target_label": "Ku",
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
                "target_label": "Goal",
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
                "target_label": "Habit",
                "alias": "habit_context",
                "direction": "outgoing",
                "fields": ["uid", "title", "current_streak"],
                "single": True,
            }
        )

    return build_entity_with_context(
        entity_label="Task",
        relationships=relationships,
    )


def build_goal_with_context(
    include_tasks: bool = True,
    include_habits: bool = True,
    include_subgoals: bool = True,
    include_knowledge: bool = True,
    include_principles: bool = True,
    include_milestones: bool = True,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for Goal entity with full graph context.

    Args:
        include_tasks: Include contributing tasks (default True)
        include_habits: Include contributing habits (default True)
        include_subgoals: Include sub-goals (default True)
        include_knowledge: Include required knowledge (default True)
        include_principles: Include aligned principles (default True)
        include_milestones: Include milestone progress (default True)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    relationships: list[RelationshipSpec] = []

    if include_tasks:
        relationships.append(
            {
                "rel_types": "FULFILLS_GOAL",
                "target_label": "Task",
                "alias": "contributing_tasks",
                "direction": "incoming",
                "fields": ["uid", "title", "status", "priority"],
            }
        )

    if include_habits:
        relationships.append(
            {
                "rel_types": "SUPPORTS_GOAL",
                "target_label": "Habit",
                "alias": "contributing_habits",
                "direction": "incoming",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    if include_subgoals:
        relationships.append(
            {
                "rel_types": "PARENT_GOAL",
                "target_label": "Goal",
                "alias": "sub_goals",
                "direction": "incoming",
                "fields": ["uid", "title", "status", "progress_percentage"],
            }
        )

    if include_knowledge:
        relationships.append(
            {
                "rel_types": "REQUIRES_KNOWLEDGE",
                "target_label": "Ku",
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
                "target_label": "Principle",
                "alias": "aligned_principles",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_milestones:
        relationships.append(
            {
                "rel_types": "HAS_MILESTONE",
                "target_label": "Milestone",
                "alias": "milestones",
                "direction": "outgoing",
                "fields": ["uid", "title", "is_completed", "target_date", "order"],
            }
        )

    return build_entity_with_context(
        entity_label="Goal",
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
) -> tuple[str, dict[str, Any]]:
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
                "target_label": "Ku",
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
                "target_label": "Ku",
                "alias": "enables_learning",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_related:
        relationships.append(
            {
                "rel_types": "RELATED_TO",
                "target_label": "Ku",
                "alias": "related",
                "direction": "both",
                "fields": ["uid", "title"],
            }
        )

    if include_applied_in_tasks:
        relationships.append(
            {
                "rel_types": "APPLIES_KNOWLEDGE",
                "target_label": "Task",
                "alias": "applied_in_tasks",
                "direction": "incoming",
                "fields": ["uid", "title", "status"],
            }
        )

    if include_reinforced_by_habits:
        relationships.append(
            {
                "rel_types": "REINFORCES_KNOWLEDGE",
                "target_label": "Habit",
                "alias": "reinforced_by_habits",
                "direction": "incoming",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    if include_supports_goals:
        relationships.append(
            {
                "rel_types": "REQUIRES_KNOWLEDGE",
                "target_label": "Goal",
                "alias": "supports_goals",
                "direction": "incoming",
                "fields": ["uid", "title", "progress_percentage"],
            }
        )

    return build_entity_with_context(
        entity_label="Ku",
        relationships=relationships,
    )


def build_habit_with_context(
    include_knowledge: bool = True,
    include_principles: bool = True,
    include_goals: bool = True,
    include_prerequisite_habits: bool = True,
    include_reinforcing_habits: bool = True,
) -> tuple[str, dict[str, Any]]:
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
                "target_label": "Ku",
                "alias": "reinforced_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_principles:
        relationships.append(
            {
                "rel_types": "EMBODIES_PRINCIPLE",
                "target_label": "Principle",
                "alias": "embodied_principles",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_goals:
        relationships.append(
            {
                "rel_types": "SUPPORTS_GOAL",
                "target_label": "Goal",
                "alias": "supported_goals",
                "direction": "outgoing",
                "fields": ["uid", "title", "progress_percentage"],
            }
        )

    if include_prerequisite_habits:
        relationships.append(
            {
                "rel_types": "REQUIRES_PREREQUISITE_HABIT",
                "target_label": "Habit",
                "alias": "prerequisite_habits",
                "direction": "outgoing",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    if include_reinforcing_habits:
        relationships.append(
            {
                "rel_types": "REINFORCES_HABIT",
                "target_label": "Habit",
                "alias": "reinforcing_habits",
                "direction": "incoming",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    return build_entity_with_context(
        entity_label="Habit",
        relationships=relationships,
    )


def build_event_with_context(
    include_knowledge: bool = True,
    include_goals: bool = True,
    include_habits: bool = True,
    include_practiced_habits: bool = True,
    include_celebrated_goals: bool = True,
    include_conflicting_events: bool = True,
) -> tuple[str, dict[str, Any]]:
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
                "target_label": "Ku",
                "alias": "applied_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_goals:
        relationships.append(
            {
                "rel_types": "CONTRIBUTES_TO_GOAL",
                "target_label": "Goal",
                "alias": "supported_goals",
                "direction": "outgoing",
                "fields": ["uid", "title", "progress_percentage"],
            }
        )

    if include_habits:
        relationships.append(
            {
                "rel_types": "REINFORCES_HABIT",
                "target_label": "Habit",
                "alias": "reinforced_habits",
                "direction": "outgoing",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    if include_practiced_habits:
        relationships.append(
            {
                "rel_types": "PRACTICED_AT_EVENT",
                "target_label": "Habit",
                "alias": "practiced_habits",
                "direction": "incoming",
                "fields": ["uid", "title"],
            }
        )

    if include_celebrated_goals:
        relationships.append(
            {
                "rel_types": "CELEBRATED_BY_EVENT",
                "target_label": "Goal",
                "alias": "celebrated_goals",
                "direction": "incoming",
                "fields": ["uid", "title"],
            }
        )

    if include_conflicting_events:
        relationships.append(
            {
                "rel_types": "CONFLICTS_WITH",
                "target_label": "Event",
                "alias": "conflicting_events",
                "direction": "both",
                "fields": ["uid", "title", "scheduled_for"],
            }
        )

    return build_entity_with_context(
        entity_label="Event",
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
) -> tuple[str, dict[str, Any]]:
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
                "target_label": "Ku",
                "alias": "informed_by_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_principles:
        relationships.append(
            {
                "rel_types": "INFORMED_BY_PRINCIPLE",
                "target_label": "Principle",
                "alias": "aligned_principles",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_goals:
        relationships.append(
            {
                "rel_types": "AFFECTS_GOAL",
                "target_label": "Goal",
                "alias": "affected_goals",
                "direction": "outgoing",
                "fields": ["uid", "title", "progress_percentage"],
            }
        )

    if include_learning_paths:
        relationships.append(
            {
                "rel_types": "OPENS_LEARNING_PATH",
                "target_label": "Lp",
                "alias": "opened_paths",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_inspired_choices:
        relationships.append(
            {
                "rel_types": "INSPIRED_BY_CHOICE",
                "target_label": "Choice",
                "alias": "inspired_choices",
                "direction": "incoming",
                "fields": ["uid", "title"],
            }
        )

    if include_implementing_tasks:
        relationships.append(
            {
                "rel_types": "IMPLEMENTS_CHOICE",
                "target_label": "Task",
                "alias": "implementing_tasks",
                "direction": "incoming",
                "fields": ["uid", "title", "status"],
            }
        )

    if include_guiding_principles:
        relationships.append(
            {
                "rel_types": "GUIDES_CHOICE",
                "target_label": "Principle",
                "alias": "guiding_principles",
                "direction": "incoming",
                "fields": ["uid", "title"],
            }
        )

    return build_entity_with_context(
        entity_label="Choice",
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
) -> tuple[str, dict[str, Any]]:
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
                "target_label": "Ku",
                "alias": "grounding_knowledge",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_goals:
        relationships.append(
            {
                "rel_types": "GUIDES_GOAL",
                "target_label": "Goal",
                "alias": "guided_goals",
                "direction": "outgoing",
                "fields": ["uid", "title", "progress_percentage"],
            }
        )

    if include_choices:
        relationships.append(
            {
                "rel_types": "GUIDES_CHOICE",
                "target_label": "Choice",
                "alias": "guided_choices",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_habits:
        relationships.append(
            {
                "rel_types": "INSPIRES_HABIT",
                "target_label": "Habit",
                "alias": "inspired_habits",
                "direction": "outgoing",
                "fields": ["uid", "title"],
            }
        )

    if include_embodying_habits:
        relationships.append(
            {
                "rel_types": "EMBODIES_PRINCIPLE",
                "target_label": "Habit",
                "alias": "embodying_habits",
                "direction": "incoming",
                "fields": ["uid", "title", "current_streak"],
            }
        )

    if include_supporting_principles:
        relationships.append(
            {
                "rel_types": "SUPPORTS_PRINCIPLE",
                "target_label": "Principle",
                "alias": "supporting_principles",
                "direction": "incoming",
                "fields": ["uid", "title"],
            }
        )

    if include_conflicting_principles:
        relationships.append(
            {
                "rel_types": "CONFLICTS_WITH_PRINCIPLE",
                "target_label": "Principle",
                "alias": "conflicting_principles",
                "direction": "incoming",
                "fields": ["uid", "title"],
            }
        )

    if include_aligned_tasks:
        relationships.append(
            {
                "rel_types": "ALIGNED_WITH_PRINCIPLE",
                "target_label": "Task",
                "alias": "aligned_tasks",
                "direction": "incoming",
                "fields": ["uid", "title", "status"],
            }
        )

    return build_entity_with_context(
        entity_label="Principle",
        relationships=relationships,
    )


# ============================================================================
# META-SERVICE QUERY HELPERS
# ============================================================================


def build_user_activity_query(
    user_uid: str,
    node_label: str,
    date_field: str | None = None,
    start_date: "date | None" = None,
    end_date: "date | None" = None,
    exclude_statuses: list[str] | None = None,
    limit: int = 100,
) -> tuple[str, dict[str, Any]]:
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

    # Build WHERE clauses
    where_clauses = ["n.user_uid = $user_uid"]

    # Date range filtering (if provided)
    if date_field and start_date and end_date:
        where_clauses.append(f"n.{date_field} >= date($start_date)")
        where_clauses.append(f"n.{date_field} <= date($end_date)")

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
    params: dict[str, Any] = {"user_uid": user_uid, "limit": limit}

    if date_field and start_date and end_date:
        params["start_date"] = start_date.isoformat()
        params["end_date"] = end_date.isoformat()

    if exclude_statuses:
        params["exclude_statuses"] = exclude_statuses

    return cypher.strip(), params


# =============================================================================
# TIME-BASED QUERIES (Due Soon / Overdue)
# =============================================================================


def build_due_soon_query(
    node_label: str,
    date_field: str,
    days_ahead: int = 7,
    exclude_statuses: list[str] | None = None,
    user_uid: str | None = None,
    limit: int = 100,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for entities due within N days.

    Used by BaseService.get_due_soon() for all Activity Domains.

    Args:
        node_label: Neo4j node label (e.g., "Task", "Goal", "Event")
        date_field: Date field to check (e.g., "due_date", "target_date")
        days_ahead: Number of days to look ahead (default 7)
        exclude_statuses: Statuses to exclude (e.g., ["completed", "cancelled"])
        user_uid: Optional user UID for ownership filter
        limit: Maximum results

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

    today = date.today()
    end_date = today + timedelta(days=days_ahead)

    # Build WHERE clauses
    where_clauses = [
        f"n.{date_field} >= date($today)",
        f"n.{date_field} <= date($end_date)",
    ]

    if exclude_statuses:
        where_clauses.append("NOT n.status IN $exclude_statuses")

    if user_uid:
        where_clauses.append("n.user_uid = $user_uid")

    where_clause = " AND ".join(where_clauses)

    # Sort by date ASC (nearest first)
    cypher = f"""
    MATCH (n:{node_label})
    WHERE {where_clause}
    RETURN n
    ORDER BY n.{date_field} ASC
    LIMIT $limit
    """

    params: dict[str, Any] = {
        "today": today.isoformat(),
        "end_date": end_date.isoformat(),
        "limit": limit,
    }

    if exclude_statuses:
        params["exclude_statuses"] = exclude_statuses
    if user_uid:
        params["user_uid"] = user_uid

    return cypher.strip(), params


def build_overdue_query(
    node_label: str,
    date_field: str,
    exclude_statuses: list[str] | None = None,
    user_uid: str | None = None,
    limit: int = 100,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for entities past their due date.

    Used by BaseService.get_overdue() for all Activity Domains.

    Args:
        node_label: Neo4j node label (e.g., "Task", "Goal", "Event")
        date_field: Date field to check (e.g., "due_date", "target_date")
        exclude_statuses: Statuses to exclude (e.g., ["completed", "cancelled"])
        user_uid: Optional user UID for ownership filter
        limit: Maximum results

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

    today = date.today()

    # Build WHERE clauses
    where_clauses = [
        f"n.{date_field} < date($today)",
    ]

    if exclude_statuses:
        where_clauses.append("NOT n.status IN $exclude_statuses")

    if user_uid:
        where_clauses.append("n.user_uid = $user_uid")

    where_clause = " AND ".join(where_clauses)

    # Sort by date ASC (oldest/most overdue first)
    cypher = f"""
    MATCH (n:{node_label})
    WHERE {where_clause}
    RETURN n
    ORDER BY n.{date_field} ASC
    LIMIT $limit
    """

    params: dict[str, Any] = {
        "today": today.isoformat(),
        "limit": limit,
    }

    if exclude_statuses:
        params["exclude_statuses"] = exclude_statuses
    if user_uid:
        params["user_uid"] = user_uid

    return cypher.strip(), params
