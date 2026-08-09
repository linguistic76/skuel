"""
Event Request Models (Tier 1 - External)
========================================

Pydantic models for event API boundaries - validation and serialization.

Uses shared validation rules from core.models.validation_rules for DRY compliance.
"""

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field

from core.models.enums import EntityStatus, EventType, Priority, RecurrencePattern, Visibility
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.sentinels import UNSET, Unset
from core.models.type_hints import UserUID
from core.models.validation_rules import (
    validate_recurrence_end_after_start,
    validate_time_after,
    validate_url_when_online,
)


class EventCreateRequest(BaseModel):
    """External API request for creating an event."""

    title: str = Field(min_length=1, max_length=200, description="Event title")
    description: str | None = Field(default=None, description="Event description")

    # Timing
    event_date: date = Field(description="Date of the event")
    start_time: time = Field(description="Start time")
    end_time: time = Field(description="End time")

    # Type and visibility
    event_type: EventType = Field(default=EventType.PERSONAL, description="Type of event")
    visibility: Visibility = Field(default=Visibility.PRIVATE, description="Event visibility")

    # Location
    location: str | None = Field(default=None, description="Event location")
    is_online: bool = Field(default=False, description="Is this an online event")
    meeting_url: str | None = Field(default=None, description="Online meeting URL")

    # Organization
    tags: list[str] = Field(default_factory=list, description="Event tags")
    priority: Priority = Field(default=Priority.MEDIUM, description="Event priority")

    # Attendees
    attendee_emails: list[str] = Field(default_factory=list, description="Attendee email addresses")
    max_attendees: int | None = Field(default=None, ge=1, description="Maximum number of attendees")

    # Recurrence
    recurrence_pattern: RecurrencePattern | None = Field(
        default=None, description="Recurrence pattern"
    )
    recurrence_end_date: date | None = Field(default=None, description="End date for recurrence")

    # Reminders
    reminder_minutes: int | None = Field(
        default=None, ge=0, le=10080, description="Reminder time in minutes before event"
    )

    # Learning Integration (OPTIONAL)
    reinforces_habit_uid: str | None = Field(
        default=None, description="Habit this event reinforces"
    )
    practices_knowledge_uids: list[str] = Field(
        default_factory=list, description="Knowledge practiced in event"
    )
    milestone_celebration_for_goal: str | None = Field(
        default=None, description="Goal milestone being celebrated"
    )
    executes_tasks: list[str] = Field(
        default_factory=list, description="Tasks to execute during event"
    )
    habit_completion_quality: int | None = Field(
        default=None, ge=1, le=5, description="Quality of habit completion (1-5)"
    )
    knowledge_retention_check: bool = Field(
        default=False, description="Is this a knowledge retention check?"
    )

    # Shared validators (DRY pattern)
    _validate_end_time = validate_time_after("end_time", "start_time")
    _validate_meeting_url = validate_url_when_online("meeting_url", "is_online")
    _validate_recurrence_end = validate_recurrence_end_after_start(
        "recurrence_end_date", "event_date"
    )

    model_config = ConfigDict(
        # Pydantic V2 serializes enums, dates, times, and datetimes automatically
    )


class EventUpdateRequest(BaseModel):
    """External API request for updating an event."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    event_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    event_type: EventType | None = None
    visibility: Visibility | None = None
    location: str | None = None
    is_online: bool | None = None
    meeting_url: str | None = None
    tags: list[str] | None = None
    priority: Priority | None = None
    status: EntityStatus | None = None
    reminder_minutes: int | None = Field(default=None, ge=0, le=10080)

    # Learning Integration Updates (OPTIONAL)
    reinforces_habit_uid: str | None = None
    practices_knowledge_uids: list[str] | None = None
    milestone_celebration_for_goal: str | None = None
    executes_tasks: list[str] | None = None
    habit_completion_quality: int | None = Field(default=None, ge=1, le=5)
    knowledge_retention_check: bool | None = None

    model_config = ConfigDict(
        # Pydantic V2 serializes enums, dates, and times automatically
    )

    def to_intent(self) -> EventUpdateIntent:
        """Build the typed ``EventUpdateIntent`` (ADR-066) from explicitly-set fields.

        Only fields the caller actually provided (``model_fields_set``) become non-``UNSET``,
        so the intent carries a true partial patch: an absent field is left untouched, a
        field explicitly set to ``None`` is an explicit clear. Enum fields (visibility,
        priority, status) are lowered to their string value to match the persistence
        boundary.

        The two cross-domain edge UIDs (``milestone_celebration_for_goal`` /
        ``reinforces_habit_uid``) are carried so the facade can split them off into
        graph-edge mutations (``CELEBRATES_GOAL`` / ``REINFORCES_HABIT``).

        ``practices_knowledge_uids`` / ``executes_tasks`` are intentionally **not** carried:
        they are neither node columns nor handled edges on the update path, so writing them
        as properties would leak junk denormalized fields onto the node — exactly what the
        create path (``create_event``) already drops.
        """
        set_fields = self.model_fields_set

        def when_set[T](name: str, value: T) -> T | Unset:
            """Carry ``value`` only if the caller set this field; else ``UNSET``.

            Generic so the intent fields stay fully typed (no ``Any``): the return is
            ``<declared field type> | Unset``, exactly what each intent field expects.
            """
            return value if name in set_fields else UNSET

        return EventUpdateIntent(
            title=when_set("title", self.title),
            description=when_set("description", self.description),
            event_type=when_set(
                "event_type", self.event_type.value if self.event_type is not None else None
            ),
            event_date=when_set("event_date", self.event_date),
            start_time=when_set("start_time", self.start_time),
            end_time=when_set("end_time", self.end_time),
            location=when_set("location", self.location),
            is_online=when_set("is_online", self.is_online),
            meeting_url=when_set("meeting_url", self.meeting_url),
            reminder_minutes=when_set("reminder_minutes", self.reminder_minutes),
            habit_completion_quality=when_set(
                "habit_completion_quality", self.habit_completion_quality
            ),
            knowledge_retention_check=when_set(
                "knowledge_retention_check", self.knowledge_retention_check
            ),
            status=when_set("status", self.status.value if self.status is not None else None),
            visibility=when_set(
                "visibility", self.visibility.value if self.visibility is not None else None
            ),
            priority=when_set(
                "priority", self.priority.value if self.priority is not None else None
            ),
            tags=when_set("tags", self.tags),
            milestone_celebration_for_goal=when_set(
                "milestone_celebration_for_goal", self.milestone_celebration_for_goal
            ),
            reinforces_habit_uid=when_set("reinforces_habit_uid", self.reinforces_habit_uid),
        )


class EventResponse(BaseModel):
    """External API response for an event."""

    uid: str
    title: str
    description: str | None

    # Timing
    event_date: date
    start_time: time
    end_time: time
    duration_minutes: int

    # Type and status
    event_type: str
    status: EntityStatus
    visibility: Visibility
    priority: Priority

    # Location
    location: str | None
    is_online: bool
    meeting_url: str | None

    # Organization
    tags: list[str]

    # Attendees
    attendee_count: int
    max_attendees: int | None
    is_full: bool

    # Recurrence
    recurrence_pattern: RecurrencePattern | None
    recurrence_end_date: date | None
    is_recurring: bool
    recurrence_parent_uid: str | None

    # Reminders
    reminder_minutes: int | None
    reminder_sent: bool

    # Metadata
    created_at: datetime
    updated_at: datetime

    # Learning Integration
    reinforces_habit_uid: str | None
    practices_knowledge_uids: list[str]
    milestone_celebration_for_goal: str | None
    executes_tasks: list[str]
    habit_completion_quality: int | None
    knowledge_retention_check: bool
    recurrence_maintains_habit: bool
    skip_breaks_habit_streak: bool

    # Computed fields
    is_past: bool
    is_today: bool
    is_upcoming: bool
    is_habit_event: bool
    is_learning_event: bool
    is_milestone_event: bool
    has_tasks: bool
    days_until: int
    conflicts_with: list[str]
    learning_impact_score: float
    completion_value: float

    model_config = ConfigDict(
        # Pydantic V2 serializes enums, dates, times, and datetimes automatically
    )


class EventFilterRequest(BaseModel):
    """Request model for filtering events."""

    status: EntityStatus | None = None
    event_type: EventType | None = None
    date_from: date | None = None
    date_to: date | None = None
    tags: list[str] | None = None
    priority: Priority | None = None
    location: str | None = None
    is_online: bool | None = None
    upcoming_only: bool = False
    past_only: bool = False

    model_config = ConfigDict(
        # Pydantic V2 serializes enums and dates automatically
    )


# =============================================================================
# OPERATION-SPECIFIC REQUEST TYPES
# =============================================================================
# These typed request objects make the API contract explicit and refactoring-safe.
# Pattern: Each service operation that takes multiple parameters gets a request type.


class RecurringInstancesRequest(BaseModel):
    """Request for creating recurring event instances."""

    event_uid: str = Field(description="UID of the recurring event template")
    count: int = Field(default=10, ge=1, le=100, description="Number of instances to create")


class GetRecurringEventsRequest(BaseModel):
    """Request for retrieving recurring events."""

    user_uid: UserUID = Field(description="User identifier")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum results to return")


class AddAttendeeRequest(BaseModel):
    """Request for adding an attendee to an event."""

    event_uid: str = Field(description="UID of the event")
    user_uid: UserUID = Field(description="UID of the user to add as attendee")
    role: str = Field(
        default="attendee", description="Attendee role (attendee, organizer, speaker)"
    )
    send_notification: bool = Field(default=True, description="Whether to notify the attendee")


class RemoveAttendeeRequest(BaseModel):
    """Request for removing an attendee from an event."""

    event_uid: str = Field(description="UID of the event")
    user_uid: UserUID = Field(description="UID of the user to remove")
    send_notification: bool = Field(default=True, description="Whether to notify the attendee")


class CheckConflictsRequest(BaseModel):
    """Request for checking event conflicts."""

    event_uid: str = Field(description="UID of the event to check for conflicts")


class EventsInRangeRequest(BaseModel):
    """Request for retrieving events in a date range."""

    start_date: date = Field(description="Start of date range")
    end_date: date = Field(description="End of date range")
    user_uid: UserUID | None = Field(default=None, description="Optional user filter")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum results")


# =============================================================================
# RESPONSE TYPES
# =============================================================================


class EventListResponse(BaseModel):
    """Response for listing multiple events."""

    items: list[EventResponse]
    total: int
    page: int = 1
    page_size: int = 20

    # Summary
    total_today: int
    total_this_week: int
    total_this_month: int
