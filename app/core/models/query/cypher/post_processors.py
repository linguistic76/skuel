"""
Post-Query Processors - Python calculations for computed context fields.
========================================================================

Contains functions that process graph_context data after Cypher query returns.
These handle calculations that can't be done efficiently in Cypher.

**Usage:**

PostProcessors are defined in the registry and executed by BaseService:
```python
# In DomainRelationshipConfig
post_processors = (
    PostProcessor(
        source_field="milestones",
        target_field="milestone_progress",
        processor_name="calculate_milestone_progress",
    ),
)
```

**Adding New Processors:**

1. Add the function to this module
2. Register it in PROCESSOR_REGISTRY
3. Reference by name in PostProcessor.processor_name

**January 2026 - Initial Implementation**
"""

from typing import Any


def calculate_milestone_progress(milestones: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Calculate milestone completion progress from milestone data.

    Args:
        milestones: List of milestone dicts with 'uid' and 'is_completed' fields

    Returns:
        Dict with:
        - total: Total number of milestones
        - completed: Number of completed milestones
        - percentage: Completion percentage (0.0-100.0)

    Example:
        >>> milestones = [
        ...     {"uid": "m1", "is_completed": True},
        ...     {"uid": "m2", "is_completed": False},
        ...     {"uid": "m3", "is_completed": True},
        ... ]
        >>> calculate_milestone_progress(milestones)
        {'total': 3, 'completed': 2, 'percentage': 66.67}
    """
    if not milestones:
        return {"total": 0, "completed": 0, "percentage": 0.0}

    total = len(milestones)
    completed = sum(1 for m in milestones if m.get("is_completed"))
    percentage = round((completed / total * 100.0), 2) if total > 0 else 0.0

    return {
        "total": total,
        "completed": completed,
        "percentage": percentage,
    }


def calculate_habit_streak_summary(habits: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Calculate habit streak summary from habit data.

    Args:
        habits: List of habit dicts with 'current_streak' field

    Returns:
        Dict with:
        - total: Total number of habits
        - active: Number with streak > 0
        - total_streak_days: Sum of all current streaks
        - avg_streak: Average streak length

    Example:
        >>> habits = [
        ...     {"uid": "h1", "current_streak": 5},
        ...     {"uid": "h2", "current_streak": 0},
        ...     {"uid": "h3", "current_streak": 10},
        ... ]
        >>> calculate_habit_streak_summary(habits)
        {'total': 3, 'active': 2, 'total_streak_days': 15, 'avg_streak': 5.0}
    """
    if not habits:
        return {"total": 0, "active": 0, "total_streak_days": 0, "avg_streak": 0.0}

    total = len(habits)
    streaks = [h.get("current_streak", 0) or 0 for h in habits]
    active = sum(1 for s in streaks if s > 0)
    total_streak_days = sum(streaks)
    avg_streak = round(total_streak_days / total, 2) if total > 0 else 0.0

    return {
        "total": total,
        "active": active,
        "total_streak_days": total_streak_days,
        "avg_streak": avg_streak,
    }


def calculate_task_status_summary(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Calculate task status summary from task data.

    Args:
        tasks: List of task dicts with 'status' field

    Returns:
        Dict with status counts and completion percentage

    Example:
        >>> tasks = [
        ...     {"uid": "t1", "status": "completed"},
        ...     {"uid": "t2", "status": "in_progress"},
        ...     {"uid": "t3", "status": "completed"},
        ... ]
        >>> calculate_task_status_summary(tasks)
        {'total': 3, 'completed': 2, 'in_progress': 1, 'pending': 0, 'completion_percentage': 66.67}
    """
    if not tasks:
        return {
            "total": 0,
            "completed": 0,
            "in_progress": 0,
            "pending": 0,
            "completion_percentage": 0.0,
        }

    total = len(tasks)
    statuses = [t.get("status", "pending") for t in tasks]

    completed = sum(1 for s in statuses if s == "completed")
    in_progress = sum(1 for s in statuses if s == "in_progress")
    pending = sum(1 for s in statuses if s in ("pending", "not_started"))

    percentage = round((completed / total * 100.0), 2) if total > 0 else 0.0

    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "completion_percentage": percentage,
    }


# =============================================================================
# PROCESSOR REGISTRY
# =============================================================================
# Maps processor names to functions. Used by BaseService._parse_context_result()

PROCESSOR_REGISTRY: dict[str, Any] = {
    "calculate_milestone_progress": calculate_milestone_progress,
    "calculate_habit_streak_summary": calculate_habit_streak_summary,
    "calculate_task_status_summary": calculate_task_status_summary,
}


def get_processor(name: str) -> Any:
    """
    Get a processor function by name.

    Args:
        name: Processor name as defined in PostProcessor.processor_name

    Returns:
        The processor function

    Raises:
        KeyError: If processor name not found in registry
    """
    if name not in PROCESSOR_REGISTRY:
        raise KeyError(
            f"Unknown processor: {name}. Available processors: {list(PROCESSOR_REGISTRY.keys())}"
        )
    return PROCESSOR_REGISTRY[name]


def apply_processor(
    processor_name: str,
    source_data: Any,
) -> Any:
    """
    Apply a named processor to source data.

    Args:
        processor_name: Name of the processor function
        source_data: Data to process (typically a list of dicts)

    Returns:
        Processed result (typically a summary dict)
    """
    processor = get_processor(processor_name)
    return processor(source_data)
