"""
DSL Mappings
============

Shared mapping functions and type aliases for converting DSL values
to SKUEL domain enums. Used by all converter modules.
"""

from typing import Any

from core.models.choice.choice_request import ChoiceCreateRequest
from core.models.enums import Priority, RecurrencePattern
from core.models.event.event_request import EventCreateRequest
from core.models.goal.goal_request import GoalCreateRequest
from core.models.habit.habit_request import HabitCreateRequest
from core.models.principle.principle_request import PrincipleCreateRequest
from core.models.task.task_request import TaskCreateRequest

# Type alias for conversion results.
# The 6 Activity Domain converters emit typed *CreateRequest objects; the
# specialized converters (ku, calendar, ...) still emit dicts.
ConversionResult = (
    TaskCreateRequest
    | HabitCreateRequest
    | GoalCreateRequest
    | EventCreateRequest
    | PrincipleCreateRequest
    | ChoiceCreateRequest
    | dict[str, Any]
)


def map_dsl_priority_to_enum(dsl_priority: int | None) -> Priority:
    """
    Map DSL priority (1-5) to SKUEL Priority enum.

    DSL: 1=highest, 5=lowest
    SKUEL: LOW, MEDIUM, HIGH, CRITICAL

    Mapping:
    - 1 → CRITICAL
    - 2 → HIGH
    - 3 → MEDIUM
    - 4, 5 → LOW
    """
    if dsl_priority is None:
        return Priority.MEDIUM

    if dsl_priority == 1:
        return Priority.CRITICAL
    elif dsl_priority == 2:
        return Priority.HIGH
    elif dsl_priority == 3:
        return Priority.MEDIUM
    else:
        return Priority.LOW


def map_repeat_to_recurrence(repeat_pattern: dict[str, Any] | None) -> RecurrencePattern | None:
    """
    Map DSL repeat pattern to SKUEL RecurrencePattern.

    DSL patterns:
    - {"type": "daily"}
    - {"type": "weekly", "days": ["Mon", "Wed"]}
    - {"type": "monthly", "days": [1, 15]}
    - {"type": "interval", "interval": 3, "unit": "days"}

    SKUEL patterns: DAILY, WEEKLY, BIWEEKLY, MONTHLY, QUARTERLY, YEARLY, CUSTOM
    """
    if not repeat_pattern:
        return None

    pattern_type = repeat_pattern.get("type", "")

    if pattern_type == "daily":
        return RecurrencePattern.DAILY

    if pattern_type == "weekly":
        repeat_pattern.get("days", [])
        # If specific days, it's WEEKLY
        # If all weekdays, still WEEKLY
        return RecurrencePattern.WEEKLY

    if pattern_type == "monthly":
        return RecurrencePattern.MONTHLY

    if pattern_type == "interval":
        interval = repeat_pattern.get("interval", 1)
        unit = repeat_pattern.get("unit", "days")

        if unit == "days":
            if interval == 1:
                return RecurrencePattern.DAILY
            elif interval == 7:
                return RecurrencePattern.WEEKLY
            elif interval == 14:
                return RecurrencePattern.BIWEEKLY
        elif unit == "weeks":
            if interval == 1:
                return RecurrencePattern.WEEKLY
            elif interval == 2:
                return RecurrencePattern.BIWEEKLY
        elif unit == "months":
            if interval == 1:
                return RecurrencePattern.MONTHLY
            elif interval == 3:
                return RecurrencePattern.QUARTERLY
            elif interval == 12:
                return RecurrencePattern.YEARLY

        # Default to CUSTOM for complex intervals
        return RecurrencePattern.CUSTOM

    if pattern_type == "custom":
        return RecurrencePattern.CUSTOM

    return None
