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

from core.models.enums.entity_enums import EntityType
from core.models.enums.habit_enums import CompletionStatus
from core.models.enums.scheduling_enums import TimeOfDay
from core.models.type_hints import EntityUID


def _default_all_item_types() -> Any:
    """Default factory for all calendar item types."""
    return list(CalendarItemType)


class CalendarItemType(StrEnum):
    """Kind of item displayed on calendar.

    Four kinds — one per grid-rendered thing (periodic-notes arc E1). Due-ness
    is NOT a kind: a due-but-unscheduled task is still a Task, carrying the
    ``CalendarItem.is_due`` state flag (the way completed is a state).
    """

    EVENT = "event"  # Native event (meeting, appointment)
    TASK = "task"  # Task chip (scheduled work, or due-only via is_due)
    HABIT = "habit"  # Recurring habit block
    MILESTONE = "milestone"  # Goal target date

    def get_icon(self) -> str:
        """Get emoji icon for this calendar item type"""
        icons = {
            CalendarItemType.TASK: "📋",
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
        Due-state urgency is a chip-level cue (⏰ + red accent, calendar.css),
        never a kind color.
        """
        colors = {
            CalendarItemType.EVENT: "#2563eb",
            CalendarItemType.TASK: "#6366f1",
            CalendarItemType.HABIT: "#16a34a",
            CalendarItemType.MILESTONE: "#9333ea",
        }
        return colors.get(self, "#3B82F6")

    def get_label(self) -> str:
        """Human label for this type — legend + item-detail type pill."""
        labels = {
            CalendarItemType.EVENT: "Event",
            CalendarItemType.TASK: "Task",
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


# The '{kind}-{source_uid}' wire format CalendarService's item converters
# author (e.g. 'task-task_123'). Extend here when a new kind gains calendar
# items. This prefix is the calendar's OWN wire format, not entity-type
# sniffing — the source uid after the dash stays opaque.
_CALENDAR_ITEM_UID_PREFIXES: tuple[tuple[str, EntityType], ...] = (
    ("task-", EntityType.TASK),
    ("event-", EntityType.EVENT),
    ("habit-", EntityType.HABIT),
    ("goal-", EntityType.GOAL),
)


def parse_calendar_item_uid(item_uid: str) -> tuple[EntityType, str] | None:
    """Split a calendar item uid into (source entity type, source uid).

    THE single parse of the calendar item wire format — service dispatch and
    route guards both use it, so no second string classifier can drift.
    Returns None for an unknown kind; callers treat that as not-found.
    """
    for prefix, entity_type in _CALENDAR_ITEM_UID_PREFIXES:
        if item_uid.startswith(prefix):
            return entity_type, item_uid[len(prefix) :]
    return None


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
    # Due-state (tasks): due-but-unscheduled — a STATE of a Task, not a kind
    # (periodic-notes arc E1). Chips render it as ⏰ + red accent.
    is_due: bool = False

    # Recurrence
    is_recurring: bool = False
    recurrence_pattern: str | None = None  # RRULE string if recurring

    # Metadata
    priority: int = 1  # 1-5, higher is more important
    category: str | None = None

    # Habit-specific
    occurrence_data: dict[str, Any] | None = None
    streak_count: int | None = None
    # The habit's TimeOfDay slot — the vocabulary a habit chip SPEAKS (M1/M3).
    # ``start_time`` carries the slot's representative hour so the day orders
    # correctly; this carries the slot itself, because the hour cannot be
    # inverted back to it (MORNING and ANYTIME both resolve to 09:00).
    time_of_day: TimeOfDay | None = None

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


def habit_block_on(item: CalendarItem, day: date) -> tuple[datetime, datetime]:
    """Re-date a habit's block onto ``day``, keeping its time of day and length.

    A habit calendar item carries a *fuzzy block* — the ``TimeOfDay`` slot's
    representative time plus the habit's own duration (habit-rhythm arc M3) —
    stamped on a placeholder date, because a recurring habit has no single date
    of its own. Both projections that place a habit on a real day re-date it
    here: the calendar's occurrence expansion (``ui.calendar.components``) and
    the day stamp behind the ``?date=`` item-details modal
    (``CalendarService._stamp_habit_occurrence``). One re-dating truth, so a
    chip and its modal can never disagree about when the block sits or how long
    it runs.

    A block whose length crosses midnight keeps its full length: the day it is
    rendered on is the day it STARTS, and the duration is what the chip states.
    """
    start = datetime.combine(day, item.start_time.time())
    return start, start + (item.end_time - item.start_time)


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
