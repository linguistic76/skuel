"""
Calendar Converters
====================

Unified calendar entity conversion for all Activity domains.

Consolidates the entity-to-CalendarItem conversion logic from:
- tasks_views.py
- goals_views.py
- events_views.py
- habits_views.py

Usage:
    from ui.calendar.converters import (
        task_to_calendar_item,
        goal_to_calendar_item,
        event_to_calendar_item,
        habit_to_calendar_items,
    )
"""

from datetime import date, datetime, time, timedelta
from typing import Any

from adapters.calendar_adapters import adapt_entities
from core.models.enums import ActivityType, Priority
from core.models.event.calendar_models import CalendarItem, CalendarItemType
from core.ports import get_enum_value
from core.ports.calendar_protocol import CalendarTrackable, WindowKind
from core.utils.neo4j_temporal import convert_neo4j_date, convert_neo4j_time

# =============================================================================
# SHARED HELPERS
# =============================================================================


def _normalize_priority(
    priority: Priority | str | None, default: Priority = Priority.MEDIUM
) -> Priority:
    """
    Normalize priority value to Priority enum.

    Args:
        priority: Priority enum, string, or None
        default: Default priority if conversion fails

    Returns:
        Priority enum value
    """
    if priority is None:
        return default
    if isinstance(priority, Priority):
        return priority
    try:
        return Priority(priority)
    except ValueError:
        return default


def get_priority_calendar_color(priority: Priority | str | None) -> str:
    """
    Convert priority to color for calendar display.

    Uses Priority.get_calendar_color() for the canonical color mapping.

    Args:
        priority: Priority value (enum, string, or None)

    Returns:
        Hex color string for calendar display
    """
    normalized = _normalize_priority(priority, Priority.LOW)
    return normalized.get_calendar_color()


def _make_calendar_uid(prefix: str, entity_uid: str, suffix: str | None = None) -> str:
    """
    Generate consistent calendar item UID.

    Args:
        prefix: Entity type prefix (e.g., "task", "goal", "event", "habit")
        entity_uid: Source entity UID
        suffix: Optional suffix for multi-item entities (e.g., date for habits)

    Returns:
        Calendar item UID in format "prefix-uid" or "prefix-uid-suffix"
    """
    if suffix:
        return f"{prefix}-{entity_uid}-{suffix}"
    return f"{prefix}-{entity_uid}"


# =============================================================================
# EVENT TYPE COLORS
# =============================================================================

EVENT_TYPE_COLORS = {
    "meeting": "#3b82f6",  # Blue
    "deadline": "#ef4444",  # Red
    "personal": "#22c55e",  # Green
    "work": "#f97316",  # Orange
    "social": "#8b5cf6",  # Purple
    "learning": "#06b6d4",  # Cyan
}

FREQUENCY_COLORS = {
    "daily": "#22c55e",  # Green
    "weekly": "#3b82f6",  # Blue
    "monthly": "#8b5cf6",  # Purple
}


# =============================================================================
# DOMAIN-SPECIFIC CONVERTERS
# =============================================================================


def task_to_calendar_item(task: Any) -> CalendarItem:
    """
    Convert a Task to CalendarItem for calendar rendering.

    Args:
        task: Task domain model or DTO

    Returns:
        CalendarItem for calendar components
    """
    # Determine which date to use
    task_date = getattr(task, "due_date", None) or getattr(task, "scheduled_date", None)
    if not task_date:
        task_date = date.today()

    # Determine item type based on whether it's a due date or scheduled work
    item_type = (
        CalendarItemType.TASK_DEADLINE
        if getattr(task, "due_date", None)
        else CalendarItemType.TASK_WORK
    )

    # Get duration or default to 60 minutes
    duration = getattr(task, "duration_minutes", 60) or 60

    # Create start and end times
    start_dt = datetime.combine(task_date, time(9, 0))  # Default 9am
    end_dt = start_dt + timedelta(minutes=duration)

    priority = _normalize_priority(getattr(task, "priority", None))

    return CalendarItem(
        uid=_make_calendar_uid("task", task.uid),
        source_uid=task.uid,
        item_type=item_type,
        title=task.title,
        start_time=start_dt,
        end_time=end_dt,
        all_day=True,
        description=getattr(task, "description", "") or "",
        color=get_priority_calendar_color(priority),
        icon="✅",
        priority=get_enum_value(priority),
        tags=getattr(task, "tags", []) or [],
        category=getattr(task, "project", None),
        metadata={
            "status": getattr(task, "status", None),
            "assignee": getattr(task, "assignee", None),
        },
    )


def goal_to_calendar_item(goal: Any) -> CalendarItem | None:
    """
    Convert a Goal to CalendarItem for calendar rendering.

    Args:
        goal: Goal domain model or DTO

    Returns:
        CalendarItem for calendar components, or None if no target date
    """
    # Get target date and convert to date object if string
    target_date = getattr(goal, "target_date", None)
    if not target_date:
        return None

    # Convert string date to date object
    if isinstance(target_date, str):
        try:
            target_date = date.fromisoformat(target_date)
        except ValueError:
            return None

    # Goals appear as single-day items on their target (due) date
    start_dt = datetime.combine(target_date, time(0, 0))
    end_dt = datetime.combine(target_date, time(23, 59))

    priority = _normalize_priority(getattr(goal, "priority", None))

    return CalendarItem(
        uid=_make_calendar_uid("goal", goal.uid),
        source_uid=goal.uid,
        item_type=CalendarItemType.TASK_DEADLINE,  # Goals appear as milestones
        title=goal.title,
        start_time=start_dt,
        end_time=end_dt,
        all_day=True,
        description=getattr(goal, "description", "") or "",
        color=get_priority_calendar_color(priority),
        icon="🎯",
        priority=get_enum_value(priority),
        tags=getattr(goal, "tags", []) or [],
        category=str(getattr(goal, "domain", "")) if getattr(goal, "domain", None) else None,
        metadata={
            "status": str(getattr(goal, "status", "")).replace("EntityStatus.", ""),
            "timeframe": str(getattr(goal, "timeframe", "")),
            "progress": getattr(goal, "current_value", 0),
        },
    )


def event_to_calendar_item(event: Any) -> CalendarItem:
    """
    Convert an Event to CalendarItem for calendar rendering.

    Args:
        event: Event domain model or DTO

    Returns:
        CalendarItem for calendar components
    """
    # Convert Neo4j temporal types to Python types
    event_date = (
        convert_neo4j_date(getattr(event, "event_date", None), default=date.today()) or date.today()
    )
    start_time_val = convert_neo4j_time(
        getattr(event, "start_time", None), default=time(9, 0)
    ) or time(9, 0)
    end_time_val = convert_neo4j_time(
        getattr(event, "end_time", None), default=time(10, 0)
    ) or time(10, 0)

    start_dt = datetime.combine(event_date, start_time_val)
    end_dt = datetime.combine(event_date, end_time_val)

    event_type = str(getattr(event, "event_type", "personal")).lower()

    return CalendarItem(
        uid=_make_calendar_uid("event", event.uid),
        source_uid=event.uid,
        item_type=CalendarItemType.EVENT,
        title=event.title,
        start_time=start_dt,
        end_time=end_dt,
        all_day=False,
        description=getattr(event, "description", "") or "",
        color=EVENT_TYPE_COLORS.get(event_type, "#3b82f6"),
        icon="📅",
        priority=str(getattr(event, "priority", "medium")),
        tags=getattr(event, "tags", []) or [],
        category=event_type,
        metadata={
            "location": getattr(event, "location", ""),
            "status": str(getattr(event, "status", "")),
        },
    )


def habit_to_calendar_items(habit: Any, current_date: date) -> list[CalendarItem]:
    """
    Convert a Habit to CalendarItems for calendar rendering.

    Unlike other converters, habits generate multiple calendar items
    based on their recurrence pattern for the month around current_date.

    Args:
        habit: Habit domain model or DTO
        current_date: Date to generate items around

    Returns:
        List of CalendarItems representing habit schedule
    """
    items: list[CalendarItem] = []
    frequency = str(getattr(habit, "recurrence_pattern", "daily") or "daily").lower()

    # Generate items for the month around current_date
    start_date = current_date.replace(day=1)
    if current_date.month == 12:
        end_date = current_date.replace(year=current_date.year + 1, month=1, day=1) - timedelta(
            days=1
        )
    else:
        end_date = current_date.replace(month=current_date.month + 1, day=1) - timedelta(days=1)

    current = start_date
    while current <= end_date:
        should_show = False
        if frequency == "daily":
            should_show = True
        elif frequency == "weekly":
            # Show on specific day of week (default Monday)
            should_show = current.weekday() == 0
        elif frequency == "monthly":
            # Show on first day of month
            should_show = current.day == 1

        if should_show:
            start_dt = datetime.combine(current, time(8, 0))
            duration = getattr(habit, "duration_minutes", 15) or 15
            end_dt = start_dt + timedelta(minutes=duration)

            category_str = (
                str(habit.habit_category) if getattr(habit, "habit_category", None) else None
            )

            items.append(
                CalendarItem(
                    uid=_make_calendar_uid("habit", habit.uid, current.isoformat()),
                    source_uid=habit.uid,
                    item_type=CalendarItemType.TASK_WORK,
                    title=getattr(habit, "name", habit.uid),
                    start_time=start_dt,
                    end_time=end_dt,
                    all_day=False,
                    description=getattr(habit, "description", "") or "",
                    color=FREQUENCY_COLORS.get(frequency, "#22c55e"),
                    icon="🔄",
                    priority="medium",
                    tags=list(habit.tags) if getattr(habit, "tags", None) else [],
                    category=category_str,
                    metadata={
                        "frequency": frequency,
                        "current_streak": getattr(habit, "current_streak", 0) or 0,
                    },
                )
            )

        current += timedelta(days=1)

    return items


# =============================================================================
# PROTOCOL-BASED CONVERTERS (uniform interface for mixed entity lists)
# =============================================================================

_ACTIVITY_TYPE_TO_ITEM_TYPE: dict[ActivityType, CalendarItemType] = {
    ActivityType.TASK: CalendarItemType.TASK_WORK,
    ActivityType.HABIT: CalendarItemType.HABIT,
    ActivityType.EVENT: CalendarItemType.EVENT,
    ActivityType.LEARNING: CalendarItemType.EVENT,
    ActivityType.MILESTONE: CalendarItemType.MILESTONE,
    ActivityType.DEADLINE: CalendarItemType.TASK_DEADLINE,
    ActivityType.MEETING: CalendarItemType.EVENT,
    ActivityType.PRACTICE: CalendarItemType.TASK_WORK,
    ActivityType.REVIEW: CalendarItemType.TASK_WORK,
    ActivityType.BREAK: CalendarItemType.EVENT,
}


def trackable_to_calendar_items(trackable: CalendarTrackable) -> list[CalendarItem]:
    """
    Convert a CalendarTrackable entity to CalendarItem objects.

    One CalendarItem is generated per time window. Entities with no
    scheduled windows return an empty list.

    Args:
        trackable: Entity implementing CalendarTrackable protocol

    Returns:
        List of CalendarItems (empty if entity has no calendar windows)
    """
    windows = trackable.get_calendar_windows()
    if not windows:
        return []

    activity_type = trackable.get_activity_type()
    priority = trackable.get_priority()
    color = trackable.get_color() or get_priority_calendar_color(priority)
    icon = trackable.get_icon() or CalendarItemType.EVENT.get_icon()
    tags = trackable.get_tags()
    related_uids = trackable.get_related_uids()
    description = trackable.get_description() or ""
    metadata = trackable.get_metadata()

    items = []
    for i, window in enumerate(windows):
        # WindowKind.DEADLINE overrides the activity type mapping
        if window.kind == WindowKind.DEADLINE:
            item_type = CalendarItemType.TASK_DEADLINE
        else:
            item_type = _ACTIVITY_TYPE_TO_ITEM_TYPE.get(activity_type, CalendarItemType.EVENT)

        uid_suffix = f"-{i}" if len(windows) > 1 else ""
        items.append(
            CalendarItem(
                uid=f"{activity_type.value}-{trackable.uid}{uid_suffix}",
                source_uid=trackable.uid,
                item_type=item_type,
                title=trackable.title,
                start_time=window.start,
                end_time=window.end,
                all_day=window.is_all_day,
                description=description,
                color=color,
                icon=icon,
                priority=get_enum_value(priority),  # type: ignore[arg-type]
                tags=tags,
                related_uids=related_uids,
                metadata=metadata,
            )
        )
    return items


def entities_to_calendar_items(entities: list[Any]) -> list[CalendarItem]:
    """
    Convert a mixed list of calendar entities to CalendarItem objects.

    Uses CalendarTrackable adapters for uniform entity handling — no type
    switching required in calling code.

    Args:
        entities: Mixed list of Tasks, Events, Habits (or any CalendarTrackable-
                  compatible entity)

    Returns:
        Flat list of CalendarItems across all adapted entities
    """
    trackables = adapt_entities(entities)
    items: list[CalendarItem] = []
    for trackable in trackables:
        items.extend(trackable_to_calendar_items(trackable))
    return items


__all__ = [
    "task_to_calendar_item",
    "goal_to_calendar_item",
    "event_to_calendar_item",
    "habit_to_calendar_items",
    "trackable_to_calendar_items",
    "entities_to_calendar_items",
    "get_priority_calendar_color",
    "EVENT_TYPE_COLORS",
    "FREQUENCY_COLORS",
]
