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
from enum import Enum
from typing import Any


def _default_all_item_types() -> Any:
    """Default factory for all calendar item types."""
    return list(CalendarItemType)


class CalendarItemType(str, Enum):
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


class CalendarView(str, Enum):
    """Calendar view modes"""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    AGENDA = "agenda"  # List view


@dataclass(frozen=True)
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
    occurrence_data: dict[str, Any] | None = None  # type: ignore[assignment]
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


@dataclass(frozen=True)
class CalendarOccurrence:
    """
    Represents a specific occurrence of a recurring calendar item.
    Used for habit tracking overlays.
    """

    calendar_item_uid: str
    date: date
    status: str  # "done", "skipped", "partial", "missed"
    notes: str = ""
    completion_time: datetime | None = None  # type: ignore[assignment]
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
    occurrences: dict[str, list[CalendarOccurrence]]
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
