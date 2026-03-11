"""
Calendar Protocol for Interoperability
=======================================

Defines the protocol (interface) that any calendar-renderable entity must implement.
This creates a unified contract for tasks, events, habits, learning sessions,
and any future calendar-trackable entities.

The protocol ensures that all entities can be:
- Rendered on a calendar consistently
- Related to each other
- Prioritized and scheduled
- Tracked for progress
"""

__version__ = "1.0"


from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from core.models.enums import (
    ActivityType,
    EntityStatus,
    Priority,
    RecurrencePattern,
    Visibility,
)

# ============================================================================
# WINDOW KIND ENUM
# ============================================================================


class WindowKind(StrEnum):
    """Explicit semantics for time window types"""

    WORK = "work"  # Scheduled work block
    DEADLINE = "deadline"  # Point-in-time deadline
    ALL_DAY = "all_day"  # All-day event
    COMPLETED = "completed"  # Completed work
    EVENT = "event"  # Regular timed event


# ============================================================================
# TIME WINDOW VALUE OBJECT
# ============================================================================


@dataclass(frozen=True)
class TimeWindow:
    """
    Represents a time window on the calendar.

    This is a value object that captures when something appears on the calendar.
    It can represent scheduled work, deadlines, events, or completed activities.
    """

    start: datetime
    end: datetime

    # Window properties
    is_all_day: bool = False  # True for all-day events
    is_estimated: bool = False  # True if duration is an estimate
    is_flexible: bool = False  # True if can be rescheduled
    is_completed: bool = False  # True if represents completed work

    # Optional metadata
    label: str | None = None  # e.g., "Work Block", "Deadline", "Completed"
    color_override: str | None = None  # Override default color
    kind: WindowKind | None = None  # Explicit window type

    @property
    def duration(self) -> timedelta:
        """Calculate the duration of this time window"""
        return self.end - self.start

    @property
    def duration_minutes(self) -> int:
        """Get duration in minutes"""
        return int(self.duration.total_seconds() / 60)

    @property
    def date(self) -> date:
        """Get the date of this window (start date)"""
        return self.start.date()

    def overlaps_with(self, other: "TimeWindow") -> bool:
        """Check if this window overlaps with another"""
        return (self.start < other.end) and (self.end > other.start)

    def contains(self, dt: datetime) -> bool:
        """Check if a datetime falls within this window"""
        return self.start <= dt <= self.end

    def shift(self, delta: timedelta) -> "TimeWindow":
        """Create a new window shifted by the given delta"""
        return TimeWindow(
            start=self.start + delta,
            end=self.end + delta,
            is_all_day=self.is_all_day,
            is_estimated=self.is_estimated,
            is_flexible=self.is_flexible,
            is_completed=self.is_completed,
            label=self.label,
            color_override=self.color_override,
            kind=self.kind,
        )


# ============================================================================
# CALENDAR TRACKABLE PROTOCOL
# ============================================================================


@runtime_checkable
class CalendarTrackable(Protocol):
    """
    Protocol for entities that can be rendered on a calendar.

    Any entity implementing this protocol can be:
    - Displayed on calendar views
    - Scheduled and rescheduled
    - Related to other calendar items
    - Tracked for progress

    This includes: Tasks, Events, Habits, Learning Sessions, Milestones, etc.
    """

    # Required attributes (must be present on implementing classes)
    uid: str  # Unique identifier
    title: str  # Display title

    def get_activity_type(self) -> ActivityType:
        """
        Return the type of activity this represents.

        This determines the icon and default rendering style.
        """
        ...

    def get_calendar_windows(self) -> list[TimeWindow]:
        """
        Return time windows when this appears on the calendar.

        Can return multiple windows for:
        - Tasks with both work blocks and deadlines
        - Recurring items with multiple occurrences
        - Multi-day events

        Returns empty list if not currently scheduled.
        """
        ...

    def get_priority(self) -> Priority:
        """
        Return the priority for calendar rendering.

        Used for:
        - Visual emphasis (color intensity)
        - Conflict resolution
        - Sorting in day views
        """
        ...

    def get_status(self) -> EntityStatus:
        """
        Return the current status.

        Determines:
        - Whether item is shown as active/completed/cancelled
        - Visual styling (opacity, strikethrough)
        - Filtering in calendar views
        """
        ...

    def get_related_uids(self) -> list[str]:
        """
        Return UIDs of related entities.

        Includes:
        - Dependent tasks
        - Related events
        - Linked learning materials
        - Parent/child relationships
        """
        ...

    # Optional methods (provide default implementations)

    def get_description(self) -> str | None:
        """Return detailed description if available"""
        return None

    def get_tags(self) -> list[str]:
        """Return tags for filtering and grouping"""
        return []

    def get_visibility(self) -> Visibility:
        """Return visibility level (for future multi-user support)"""
        return Visibility.PRIVATE

    def get_recurrence_pattern(self) -> RecurrencePattern | None:
        """Return recurrence pattern if this is recurring"""
        return None

    def get_color(self) -> str | None:
        """Return custom color for calendar rendering"""
        return None

    def get_icon(self) -> str | None:
        """Return custom icon/emoji for display"""
        return None

    def get_estimated_duration_minutes(self) -> int | None:
        """Return estimated duration for scheduling assistance"""
        return None

    def get_actual_duration_minutes(self) -> int | None:
        """Return actual duration if tracked"""
        return None

    def get_completion_percentage(self) -> float:
        """Return completion percentage (0.0 to 100.0)"""
        return 0.0

    def get_metadata(self) -> dict[str, Any]:
        """Return additional metadata for specialized rendering"""
        return {}

    def can_reschedule(self) -> bool:
        """Check if this item can be rescheduled"""
        return True

    def can_edit(self) -> bool:
        """Check if this item can be edited"""
        return True

    def can_delete(self) -> bool:
        """Check if this item can be deleted"""
        return True


# ============================================================================
# NOTE: Helper functions (create_work_window, create_deadline_window, etc.)
# were removed as they had zero usage in the codebase.
# TimeWindow instances can be created directly using the dataclass constructor.
# ============================================================================
