"""
Calendar Domain Models
======================

Pure domain models for the unified calendar system.
These models represent the projection of tasks, events, and habits
onto a temporal grid for calendar views.
"""

__version__ = "1.0"


from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from core.models.enums.habit_enums import CompletionStatus
from core.models.type_hints import EntityUID


def _default_all_item_types() -> Any:
    """Default factory for all calendar item types."""
    return list(CalendarItemType)


class CalendarItemType(StrEnum):
    """Type of item displayed on calendar"""

    EVENT = "event"  # Native event (meeting, appointment)
    TASK_WORK = "task_work"  # Scheduled work block from task
    TASK_DEADLINE = "task_deadline"  # Task due date marker
    HABIT = "habit"  # Recurring habit block
    MILESTONE = "milestone"  # Project milestone

    def get_icon(self) -> str:
        """Get emoji icon for this calendar item type"""
        icons = {
            CalendarItemType.TASK_WORK: "📋",
            CalendarItemType.TASK_DEADLINE: "⏰",
            CalendarItemType.EVENT: "📅",
            CalendarItemType.HABIT: "🔄",
            CalendarItemType.MILESTONE: "🎯",
        }
        return icons.get(self, "📅")

    def get_color(self) -> str:
        """Hex color for this type — chip fill/accent/dot and legend swatch.

        The calendar's per-type palette (Dynamic Enum Pattern): color communicates
        the KIND of item, so the legend stays truthful across month/week/day.
        These are item-data hex values (CalendarItem.color), not CSS tokens.
        """
        colors = {
            CalendarItemType.EVENT: "#2563eb",
            CalendarItemType.TASK_WORK: "#6366f1",
            CalendarItemType.TASK_DEADLINE: "#e11d48",
            CalendarItemType.HABIT: "#16a34a",
            CalendarItemType.MILESTONE: "#9333ea",
        }
        return colors.get(self, "#3B82F6")

    def get_label(self) -> str:
        """Human label for this type — legend + item-detail type pill."""
        labels = {
            CalendarItemType.EVENT: "Event",
            CalendarItemType.TASK_WORK: "Task",
            CalendarItemType.TASK_DEADLINE: "Deadline",
            CalendarItemType.HABIT: "Habit",
            CalendarItemType.MILESTONE: "Milestone",
        }
        return labels.get(self, "Event")


class CalendarView(StrEnum):
    """Calendar view modes.

    Exactly the two shipped calendar surfaces. The single-day view was dropped
    (the Today surface owns the current day); AGENDA was never built.
    """

    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True, kw_only=True)
class CalendarItem:
    """
    Unified calendar item that can represent any time-based entity.

    This is a projection/view model, not a storage model.
    Items are generated from tasks, events, and habits.
    """

    # Required fields (no defaults)
    # Identity
    uid: str  # Unique ID for this calendar item
    source_uid: str  # UID of source entity (task/event/habit)
    item_type: CalendarItemType  # What kind of calendar item
    title: str  # Display title
    start_time: datetime  # When item begins
    end_time: datetime  # When item ends

    # Optional fields (with defaults)
    # Display
    description: str = ""
    color: str = "#3B82F6"  # Hex color for rendering
    icon: str = "📅"  # Emoji or icon class
    all_day: bool = False

    # Recurrence
    is_recurring: bool = False
    recurrence_pattern: str | None = None  # RRULE string if recurring

    # Metadata
    priority: int = 1  # 1-5, higher is more important
    category: str | None = None

    # Habit-specific
    occurrence_data: dict[str, Any] | None = None
    streak_count: int | None = None

    # Event-specific
    attendee_emails: tuple[str, ...] = ()  # Email addresses of attendees
    max_attendees: int | None = None  # Maximum allowed attendees
    location: str = ""  # Event location
    is_online: bool = False  # Whether event is online

    # Relationships
    project_uid: str | None = None

    # Lists (with proper default factory)
    tags: list[str] = field(default_factory=list)
    related_uids: list[str] = field(default_factory=list)  # Related tasks/events

    # Additional metadata (catch-all for domain-specific fields)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class CalendarOccurrence:
    """
    Represents a specific occurrence of a recurring calendar item.
    Used for habit tracking overlays.
    """

    calendar_item_uid: str
    date: date
    status: CompletionStatus
    notes: str = ""
    completion_time: datetime | None = None
    value: float | None = None  # For quantified habits


@dataclass(frozen=True)
class TimeBlock:
    """Represents a block of time for scheduling"""

    start: datetime
    end: datetime
    available: bool = True
    label: str = ""


@dataclass(frozen=True)
class CalendarData:
    """Container for calendar view data."""

    items: list[CalendarItem]
    occurrences: dict[EntityUID, list[CalendarOccurrence]]
    view: CalendarView
    start_date: date
    end_date: date
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CalendarFilter:
    """Filter criteria for calendar queries"""

    start_date: date
    end_date: date
    view: CalendarView = CalendarView.MONTH
    categories: list[str] = field(default_factory=list)
    item_types: list[CalendarItemType] = field(default_factory=_default_all_item_types)
    show_completed: bool = True
    show_habits: bool = True
    show_occurrences: bool = True
