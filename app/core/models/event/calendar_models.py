"""
Calendar Domain Models
======================

Pure domain models for the unified calendar system.
These models represent the projection of tasks, events, and habits
onto a temporal grid for calendar views.
"""

__version__ = "1.0"


from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from core.models.enums.activity_enums import Priority
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.habit_enums import CompletionStatus
from core.models.enums.scheduling_enums import TimeOfDay
from core.models.type_hints import EntityUID


class CalendarItemType(StrEnum):
    """Kind of item displayed on a calendar surface.

    Four grid kinds — one per chip the month/week render (periodic-notes arc
    E1) — plus CHOICE, which only the day view renders (as rows, never chips:
    a choice is not a ``CalendarItem``); it is a kind so the day's legend and
    the shared ``data-item-type`` filter can name it. Due-ness is NOT a kind: a
    due-but-unscheduled task is still a Task, carrying the ``CalendarItem.is_due``
    state flag (the way completed is a state).
    """

    EVENT = "event"  # Native event (meeting, appointment)
    TASK = "task"  # Task chip (scheduled work, or due-only via is_due)
    HABIT = "habit"  # Recurring habit block
    MILESTONE = "milestone"  # Goal target date
    CHOICE = "choice"  # A choice due or decided on the day (day view rows)

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
            CalendarItemType.CHOICE: "#0f766e",
        }
        return colors.get(self, "#3B82F6")

    def get_label(self) -> str:
        """Human label for this type — legend + item-detail type pill."""
        labels = {
            CalendarItemType.EVENT: "Event",
            CalendarItemType.TASK: "Task",
            CalendarItemType.HABIT: "Habit",
            CalendarItemType.MILESTONE: "Milestone",
            CalendarItemType.CHOICE: "Choice",
        }
        return labels.get(self, "Event")


class CalendarView(StrEnum):
    """Calendar view modes.

    Exactly the two shipped calendar surfaces. The single-day view was dropped
    (the Today surface owns the current day); AGENDA was never built. Each view
    declares what it renders in ``VIEW_SPECS``.
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
    Items are generated from tasks, events, habits and goal milestones.
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
    all_day: bool = False
    # Due-state (tasks): due-but-unscheduled — a STATE of a Task, not a kind
    # (periodic-notes arc E1). Chips render it as ⏰ + red accent.
    is_due: bool = False

    # Recurrence
    is_recurring: bool = False
    recurrence_pattern: str | None = None  # RRULE string if recurring

    # Membership + state: the source entity's priority is what a view's
    # ``ViewSpec`` admits by (None = unstated, read as MEDIUM); the status is
    # what the item-details modal reads (a terminal task offers no reschedule).
    priority: Priority | None = None
    status: EntityStatus | None = None

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

    tags: list[str] = field(default_factory=list)


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
    start_date: date
    end_date: date


@dataclass(frozen=True)
class ViewSpec:
    """What a calendar view renders: the kinds it admits and, per kind, the
    minimum priority.

    A kind absent from ``members`` is not fetched for the view at all. An item
    whose source entity states no priority reads as MEDIUM — the request-model
    default — so an unstated habit is shown, not hidden. The view's declared
    membership is rendered server-side; within it, the legend's client-side
    filters are the only hiding mechanism.
    """

    members: Mapping[CalendarItemType, Priority]

    def admits_kind(self, kind: CalendarItemType) -> bool:
        """Whether the view fetches and renders this kind at all."""
        return kind in self.members

    def admits(self, kind: CalendarItemType, priority: Priority | None) -> bool:
        """Whether an item of ``kind`` at ``priority`` belongs to the view."""
        floor = self.members.get(kind)
        if floor is None:
            return False
        return (priority or Priority.MEDIUM).to_numeric() >= floor.to_numeric()


VIEW_SPECS: Mapping[CalendarView, ViewSpec] = {
    # Month: the month's commitments — events at medium or above, nothing else.
    CalendarView.MONTH: ViewSpec({CalendarItemType.EVENT: Priority.MEDIUM}),
    # Week: the week's rhythm — events, habits and goal milestones at medium or
    # above, and high-priority tasks.
    CalendarView.WEEK: ViewSpec(
        {
            CalendarItemType.EVENT: Priority.MEDIUM,
            CalendarItemType.HABIT: Priority.MEDIUM,
            CalendarItemType.TASK: Priority.HIGH,
            CalendarItemType.MILESTONE: Priority.MEDIUM,
        }
    ),
}
