"""
Path-Aware Type Factory - Dynamic Path-Aware Entity Creation
=============================================================

Provides factory functions for creating path-aware entities from raw
graph query results, enabling the UnifiedRelationshipService to
produce typed context objects.

The factory maps raw Neo4j query results to domain-specific path-aware
types (PathAwareTask, PathAwareGoal, etc.) without hardcoding domain logic.

Version: 1.0.0
Date: 2025-12-03
"""

from typing import Any

from core.models.graph.path_aware_types import (
    ChoiceCrossContext,
    EventCrossContext,
    GoalCrossContext,
    HabitCrossContext,
    PathAwareChoice,
    PathAwareEvent,
    PathAwareGoal,
    PathAwareHabit,
    PathAwareKnowledge,
    PathAwarePrinciple,
    PathAwareTask,
    PrincipleCrossContext,
    TaskCrossContext,
)
from core.models.shared_enums import Domain

# Mapping from domain to path-aware type
PATH_AWARE_TYPE_MAP: dict[Domain, type] = {
    Domain.TASKS: PathAwareTask,
    Domain.GOALS: PathAwareGoal,
    Domain.HABITS: PathAwareHabit,
    Domain.EVENTS: PathAwareEvent,
    Domain.CHOICES: PathAwareChoice,
    Domain.PRINCIPLES: PathAwarePrinciple,
    Domain.KNOWLEDGE: PathAwareKnowledge,
}

# Mapping from domain to cross-context type
CROSS_CONTEXT_TYPE_MAP: dict[Domain, type] = {
    Domain.TASKS: TaskCrossContext,
    Domain.GOALS: GoalCrossContext,
    Domain.HABITS: HabitCrossContext,
    Domain.EVENTS: EventCrossContext,
    Domain.CHOICES: ChoiceCrossContext,
    Domain.PRINCIPLES: PrincipleCrossContext,
}

# Core field mappings for each path-aware type
CORE_FIELD_MAPPINGS: dict[Domain, list[str]] = {
    Domain.TASKS: ["status", "priority", "due_date"],
    Domain.GOALS: ["status", "target_date", "progress"],
    Domain.HABITS: ["frequency", "current_streak"],
    Domain.EVENTS: ["event_date", "event_type"],
    Domain.CHOICES: ["decision_date", "resolution"],
    Domain.PRINCIPLES: ["description"],
    Domain.KNOWLEDGE: ["domain", "mastery_level"],
}


def create_path_aware_entity(
    domain: Domain,
    raw_data: dict[str, Any],
    distance: int = 1,
    path_strength: float = 1.0,
    via_relationships: list[str] | None = None,
) -> Any:
    """
    Create a path-aware entity from raw data.

    Factory function that creates the appropriate path-aware type
    (PathAwareTask, PathAwareGoal, etc.) from raw Neo4j query results.

    Args:
        domain: The domain of the entity
        raw_data: Raw data dict from Neo4j query
        distance: Number of hops from source entity
        path_strength: Confidence cascade (0-1)
        via_relationships: List of relationship types in path

    Returns:
        Path-aware entity instance (PathAwareTask, PathAwareGoal, etc.)

    Example:
        >>> raw = {"uid": "task:123", "title": "Fix bug", "status": "pending"}
        >>> entity = create_path_aware_entity(Domain.TASKS, raw, distance=1)
        >>> isinstance(entity, PathAwareTask)
        True
    """
    path_aware_type = PATH_AWARE_TYPE_MAP.get(domain)
    if not path_aware_type:
        raise ValueError(f"No path-aware type defined for domain: {domain}")

    # Build kwargs for path-aware type
    kwargs: dict[str, Any] = {
        "uid": raw_data.get("uid", ""),
        "title": raw_data.get("title", raw_data.get("name", "")),
        "distance": distance,
        "path_strength": path_strength,
        "via_relationships": via_relationships or [],
    }

    # Add domain-specific core fields
    core_fields = CORE_FIELD_MAPPINGS.get(domain, [])
    for field_name in core_fields:
        if field_name in raw_data:
            kwargs[field_name] = raw_data[field_name]

    return path_aware_type(**kwargs)


def create_path_aware_entities_batch(
    domain: Domain,
    raw_data_list: list[dict[str, Any]],
) -> list[Any]:
    """
    Create multiple path-aware entities from raw data list.

    Args:
        domain: The domain of the entities
        raw_data_list: List of raw data dicts from Neo4j query

    Returns:
        List of path-aware entity instances
    """
    return [
        create_path_aware_entity(
            domain=domain,
            raw_data=raw_data,
            distance=raw_data.get("distance", 1),
            path_strength=raw_data.get("path_strength", 1.0),
            via_relationships=raw_data.get("via_relationships", []),
        )
        for raw_data in raw_data_list
    ]


def create_cross_context(
    source_domain: Domain,
    source_uid: str,
    categorized_data: dict[str, list[dict[str, Any]]],
    category_domain_map: dict[str, Domain],
) -> Any:
    """
    Create a cross-domain context object from categorized data.

    Factory function that creates the appropriate cross-context type
    (TaskCrossContext, GoalCrossContext, etc.) from categorized graph results.

    Args:
        source_domain: The domain of the source entity
        source_uid: UID of the source entity
        categorized_data: Dict mapping category names to raw entity lists
        category_domain_map: Dict mapping category names to target domains

    Returns:
        Cross-context instance (TaskCrossContext, GoalCrossContext, etc.)

    Example:
        >>> categorized = {
        ...     "prerequisites": [{"uid": "task:1", "title": "Setup"}],
        ...     "dependents": [{"uid": "task:2", "title": "Deploy"}],
        ...     "required_knowledge": [{"uid": "ku:py", "title": "Python"}],
        ... }
        >>> category_map = {
        ...     "prerequisites": Domain.TASKS,
        ...     "dependents": Domain.TASKS,
        ...     "required_knowledge": Domain.KNOWLEDGE,
        ... }
        >>> ctx = create_cross_context(Domain.TASKS, "task:123", categorized, category_map)
        >>> isinstance(ctx, TaskCrossContext)
        True
    """
    cross_context_type = CROSS_CONTEXT_TYPE_MAP.get(source_domain)
    if not cross_context_type:
        raise ValueError(f"No cross-context type defined for domain: {source_domain}")

    # Build kwargs for cross-context type
    # Start with UID field
    uid_field = f"{source_domain.value.rstrip('s')}_uid"
    kwargs: dict[str, Any] = {uid_field: source_uid}

    # Convert each category to path-aware entities
    for category_name, raw_entities in categorized_data.items():
        target_domain = category_domain_map.get(category_name)
        if target_domain:
            path_aware_entities = create_path_aware_entities_batch(target_domain, raw_entities)
            kwargs[category_name] = path_aware_entities
        else:
            kwargs[category_name] = raw_entities

    return cross_context_type(**kwargs)


def get_domain_from_label(label: str) -> Domain | None:
    """
    Get Domain enum from Neo4j node label.

    Args:
        label: Neo4j node label (e.g., "Task", "Goal", "Ku")

    Returns:
        Domain enum or None if not found
    """
    label_to_domain: dict[str, Domain] = {
        "Task": Domain.TASKS,
        "Goal": Domain.GOALS,
        "Habit": Domain.HABITS,
        "Event": Domain.EVENTS,
        "Choice": Domain.CHOICES,
        "Principle": Domain.PRINCIPLES,
        "Ku": Domain.KNOWLEDGE,
        "KnowledgeUnit": Domain.KNOWLEDGE,
    }
    return label_to_domain.get(label)
