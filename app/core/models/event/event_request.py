"""
Event Request Models (Tier 1 - External)
========================================

Pydantic models for event API boundaries - validation and serialization.

Uses shared validation rules from core.models.validation_rules for DRY compliance.
"""

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.models.enums import EntityStatus, Priority, RecurrencePattern, Visibility
from core.models.validation_rules import (
    validate_email,
    validate_future_date,
    validate_recurrence_end_after_start,
    validate_time_after,
    validate_url_when_online,
)


class EventType(str):
    """Event types as string literals for API."""

    MEETING = "MEETING"
    CONFERENCE = "CONFERENCE"
    WORKSHOP = "WORKSHOP"
    DEADLINE = "DEADLINE"
    REMINDER = "REMINDER"
    PERSONAL = "PERSONAL"
    WORK = "WORK"
    SOCIAL = "SOCIAL"
    LEARNING = "LEARNING"
    HEALTH = "HEALTH"


class EventCreateRequest(BaseModel):
    """External API request for creating an event."""

    title: str = Field(min_length=1, max_length=200, description="Event title")
    description: str | None = Field(None, description="Event description")

    # Timing
    event_date: date = Field(description="Date of the event")
    start_time: time = Field(description="Start time")
    end_time: time = Field(description="End time")

    # Type and visibility
    event_type: str = Field(default=EventType.PERSONAL, description="Type of event")
    visibility: Visibility = Field(default=Visibility.PRIVATE, description="Event visibility")

    # Location
    location: str | None = Field(None, description="Event location")
    is_online: bool = Field(default=False, description="Is this an online event")
    meeting_url: str | None = Field(None, description="Online meeting URL")

    # Organization
    tags: list[str] = Field(default_factory=list, description="Event tags")
    priority: Priority = Field(default=Priority.MEDIUM, description="Event priority")

    # Attendees
    attendee_emails: list[str] = Field(default_factory=list, description="Attendee email addresses")
    max_attendees: int | None = Field(None, ge=1, description="Maximum number of attendees")

    # Recurrence
    recurrence_pattern: RecurrencePattern | None = Field(None, description="Recurrence pattern")
    recurrence_end_date: date | None = Field(None, description="End date for recurrence")

    # Reminders
    reminder_minutes: int | None = Field(
        None, ge=0, le=10080, description="Reminder time in minutes before event"
    )

    # Learning Integration (OPTIONAL)
    reinforces_habit_uid: str | None = Field(None, description="Habit this event reinforces")
    practices_knowledge_uids: list[str] = Field(
        default_factory=list, description="Knowledge practiced in event"
    )
    milestone_celebration_for_goal: str | None = Field(
        None, description="Goal milestone being celebrated"
    )
    executes_tasks: list[str] = Field(
        default_factory=list, description="Tasks to execute during event"
    )
    habit_completion_quality: int | None = Field(
        None, ge=1, le=5, description="Quality of habit completion (1-5)"
    )
    knowledge_retention_check: bool = Field(
        False, description="Is this a knowledge retention check?"
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

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    event_date: date | None = None
    start_time: time | None = None  # type: ignore[assignment]
    end_time: time | None = None
    event_type: str | None = None
    visibility: Visibility | None = None
    location: str | None = None
    is_online: bool | None = None
    meeting_url: str | None = None
    tags: list[str] | None = None
    priority: Priority | None = None
    status: EntityStatus | None = None
    reminder_minutes: int | None = Field(None, ge=0, le=10080)

    # Learning Integration Updates (OPTIONAL)
    reinforces_habit_uid: str | None = None
    practices_knowledge_uids: list[str] | None = None
    milestone_celebration_for_goal: str | None = None
    executes_tasks: list[str] | None = None
    habit_completion_quality: int | None = Field(None, ge=1, le=5)
    knowledge_retention_check: bool | None = None

    model_config = ConfigDict(
        # Pydantic V2 serializes enums, dates, and times automatically
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
    event_type: str | None = None
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


class EventStatusUpdateRequest(BaseModel):
    """Request model for updating event status."""

    event_uid: str = Field(description="UID of the event to update")
    status: EntityStatus = Field(description="New event status")
    notes: str | None = Field(None, description="Status change notes")
    cancellation_reason: str | None = Field(None, description="Reason for cancellation")

    model_config = ConfigDict(
        # Pydantic V2 serializes enums automatically
    )


class EventPostponeRequest(BaseModel):
    """Request model for postponing an event."""

    new_date: date = Field(description="New event date")
    new_start_time: time | None = Field(None, description="New start time")
    new_end_time: time | None = Field(None, description="New end time")
    reason: str | None = Field(None, description="Reason for postponement")
    notify_attendees: bool = Field(True, description="Whether to notify attendees")

    # Shared validators (DRY pattern)
    _validate_new_date = validate_future_date("new_date")

    model_config = ConfigDict(
        # Pydantic V2 serializes dates and times automatically
    )


class EventAttendeeRequest(BaseModel):
    """Request model for adding attendees to an event."""

    email: str = Field(description="Attendee email address")
    name: str | None = Field(None, description="Attendee name")
    role: str | None = Field(None, description="Attendee role")
    required: bool = Field(True, description="Whether attendance is required")

    # Shared validators (DRY pattern)
    _validate_email = validate_email("email")


class AttendeeUpdateRequest(BaseModel):
    """Request model for updating attendee response."""

    response: str = Field(description="Attendee response: accepted, declined, maybe")
    notes: str | None = Field(None, description="Response notes")

    @field_validator("response")
    @classmethod
    def validate_response(cls, v) -> Any:
        """Ensure response is valid."""
        valid_responses = ["accepted", "declined", "maybe", "pending"]
        if v.lower() not in valid_responses:
            raise ValueError(f"Response must be one of: {', '.join(valid_responses)}")
        return v.lower()


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

    user_uid: str = Field(description="User identifier")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum results to return")


class AddAttendeeRequest(BaseModel):
    """Request for adding an attendee to an event."""

    event_uid: str = Field(description="UID of the event")
    user_uid: str = Field(description="UID of the user to add as attendee")
    role: str = Field(
        default="attendee", description="Attendee role (attendee, organizer, speaker)"
    )
    send_notification: bool = Field(default=True, description="Whether to notify the attendee")


class RemoveAttendeeRequest(BaseModel):
    """Request for removing an attendee from an event."""

    event_uid: str = Field(description="UID of the event")
    user_uid: str = Field(description="UID of the user to remove")
    send_notification: bool = Field(default=True, description="Whether to notify the attendee")


class CheckConflictsRequest(BaseModel):
    """Request for checking event conflicts."""

    event_uid: str = Field(description="UID of the event to check for conflicts")


class CalendarEventsRequest(BaseModel):
    """Request for retrieving calendar events."""

    user_uid: str = Field(description="User identifier")
    start_date: date | None = Field(None, description="Start of date range")
    end_date: date | None = Field(None, description="End of date range")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum results")


class EventHistoryRequest(BaseModel):
    """Request for retrieving event history."""

    user_uid: str = Field(description="User identifier")
    days_back: int = Field(default=90, ge=1, le=365, description="Number of days of history")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum results")


class EventsInRangeRequest(BaseModel):
    """Request for retrieving events in a date range."""

    start_date: date = Field(description="Start of date range")
    end_date: date = Field(description="End of date range")
    user_uid: str | None = Field(None, description="Optional user filter")
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
