"""
Calendar Event Domain Events
=============================

Events published when calendar event operations occur.

These events enable:
- User context invalidation when events change
- Cross-domain reactions to event updates
- Habit reinforcement tracking
- Learning session tracking

Note: Named "calendar_event_events" to avoid confusion with infrastructure Event class.,

Version: 1.0.0
Date: 2025-10-16
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class CalendarEventCreated(BaseEvent):
    """
    Published when a new calendar event is created.

    Triggers:
    - User context invalidation (calendar changes)
    - Habit reinforcement tracking initialization
    - Learning path progress updates
    """

    event_uid: str
    user_uid: str
    title: str
    event_date: date
    calendar_event_type: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "calendar_event.created"


@dataclass(frozen=True)
class CalendarEventUpdated(BaseEvent):
    """
    Published when a calendar event is updated.

    Triggers:
    - User context invalidation (event details changed)
    - Habit reinforcement recalculation
    - Learning session adjustments
    """

    event_uid: str
    user_uid: str
    updated_fields: dict[str, Any]
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "calendar_event.updated"


@dataclass(frozen=True)
class CalendarEventCompleted(BaseEvent):
    """
    Published when a calendar event is completed.

    Triggers:
    - Habit completion tracking
    - Learning session outcome recording
    - Goal progress updates
    """

    event_uid: str
    user_uid: str
    completion_date: date
    quality_score: int | None
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "calendar_event.completed"


@dataclass(frozen=True)
class CalendarEventDeleted(BaseEvent):
    """
    Published when a calendar event is deleted.

    Triggers:
    - User context invalidation (calendar changes)
    - Cleanup of event relationships
    - Habit streak recalculation
    """

    event_uid: str
    user_uid: str
    title: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "calendar_event.deleted"


@dataclass(frozen=True)
class CalendarEventRescheduled(BaseEvent):
    """
    Published when a calendar event is rescheduled.

    Triggers:
    - User context invalidation (schedule changes)
    - Habit reinforcement timeline adjustment
    - Learning path schedule updates
    """

    event_uid: str
    user_uid: str
    old_date: date
    new_date: date
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "calendar_event.rescheduled"


@dataclass(frozen=True)
class EventAttendeeAdded(BaseEvent):
    """
    Published when an attendee is added to an event.

    Triggers:
    - Notification to the added attendee
    - User context invalidation for the attendee
    """

    event_uid: str
    event_title: str
    attendee_uid: str
    added_by_uid: str
    role: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "calendar_event.attendee_added"


@dataclass(frozen=True)
class EventAttendeeRemoved(BaseEvent):
    """
    Published when an attendee is removed from an event.

    Triggers:
    - Notification to the removed attendee
    - User context invalidation for the attendee
    """

    event_uid: str
    event_title: str
    attendee_uid: str
    removed_by_uid: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "calendar_event.attendee_removed"
