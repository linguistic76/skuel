"""
Event DTO (Tier 2 - Transfer)
==============================

Mutable data transfer object for event data between layers.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, ClassVar

from core.models.activity_dto_mixin import ActivityDTOMixin
from core.models.shared_enums import ActivityStatus, Priority, RecurrencePattern, Visibility


@dataclass
class EventDTO(ActivityDTOMixin):
    """
    Mutable data transfer object for events.

    Used for:
    - Moving data between service and repository
    - Database operations
    - Inter-service communication
    """

    # Class variable for UID generation (ActivityDTOMixin)
    _uid_prefix: ClassVar[str] = "event"

    # Identity
    uid: str
    user_uid: str  # REQUIRED - event ownership
    title: str
    description: str | None = None

    # Timing (required)
    event_date: date = None  # type: ignore[assignment]
    start_time: time = None  # type: ignore[assignment]
    end_time: time = None

    # Type and status
    event_type: str = "PERSONAL"
    status: ActivityStatus = ActivityStatus.SCHEDULED
    visibility: Visibility = Visibility.PRIVATE
    priority: Priority = Priority.MEDIUM

    # Location
    location: str | None = None
    is_online: bool = False
    meeting_url: str | None = None

    # Organization
    tags: list[str] = field(default_factory=list)

    # Attendees
    attendee_emails: list[str] = field(default_factory=list)
    max_attendees: int | None = None

    # Recurrence
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_date: date | None = None
    recurrence_parent_uid: str | None = None

    # Reminders
    reminder_minutes: int | None = None
    reminder_sent: bool = False

    # Learning Integration (NEW)
    reinforces_habit_uid: str | None = None
    supports_goal_uid: str | None = None  # GRAPH RELATIONSHIP: Event supports/advances a goal
    milestone_celebration_for_goal: str | None = (
        None  # GRAPH RELATIONSHIP: Event celebrates goal achievement
    )

    # Curriculum Integration (NEW - for educational events)
    source_learning_step_uid: str | None = None  # ls: UID if event comes from curriculum
    source_learning_path_uid: str | None = None  # lp: UID for path-level events
    learning_path_uid: str | None = None  # Alias for source_learning_path_uid (convenience)
    is_milestone_event: bool = False  # True for curriculum milestones
    milestone_type: str | None = None  # 'step_completion', 'path_checkpoint', 'path_completion'
    curriculum_week: int | None = None  # Week in curriculum sequence

    # Quality Tracking (NEW)
    habit_completion_quality: int | None = None  # 1-5,
    knowledge_retention_check: bool = False

    # Recurrence (ENHANCED)
    recurrence_maintains_habit: bool = True
    skip_breaks_habit_streak: bool = True

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Additional data
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        user_uid: str,
        title: str,
        event_date: date,
        start_time: time,
        end_time: time,
        event_type: str = "PERSONAL",
        description: str | None = None,
        location: str | None = None,
        is_online: bool = False,
        meeting_url: str | None = None,
        tags: list[str] | None = None,
        attendee_emails: list[str] | None = None,
        max_attendees: int | None = None,
        priority: Priority = Priority.MEDIUM,
        recurrence_pattern: RecurrencePattern | None = None,
        recurrence_end_date: date | None = None,
        reminder_minutes: int | None = None,
        reinforces_habit_uid: str | None = None,
        milestone_celebration_for_goal: str | None = None,
    ) -> "EventDTO":
        """
        Factory method to create new EventDTO with generated UID.

        Args:
            user_uid: User UID (REQUIRED - fail-fast philosophy),
            title: Event title,
            event_date: Date of event,
            start_time: Start time,
            end_time: End time,
            event_type: Type of event,
            location: Location of event,
            is_online: Whether event is online,
            tags: Event tags

        Returns:
            EventDTO with generated UID
        """
        return cls._create_activity_dto(
            user_uid=user_uid,
            title=title,
            description=description,
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            event_type=event_type,
            priority=priority,
            location=location,
            is_online=is_online,
            meeting_url=meeting_url,
            tags=tags or [],
            attendee_emails=attendee_emails or [],
            max_attendees=max_attendees,
            recurrence_pattern=recurrence_pattern,
            recurrence_end_date=recurrence_end_date,
            reminder_minutes=reminder_minutes,
            reinforces_habit_uid=reinforces_habit_uid,
            milestone_celebration_for_goal=milestone_celebration_for_goal,
        )

    def update_from(self, updates: dict) -> None:
        """Update fields from dictionary."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(self, updates)

    def cancel(self) -> None:
        """Cancel the event."""
        self.status = ActivityStatus.CANCELLED
        self.updated_at = datetime.now()

    def complete(self) -> None:
        """Mark event as completed."""
        self.status = ActivityStatus.COMPLETED
        self.updated_at = datetime.now()

    def add_attendee(self, email: str) -> bool:
        """
        Add an attendee.

        Returns:
            True if added, False if already exists or event is full
        """
        if email in self.attendee_emails:
            return False

        if self.max_attendees and len(self.attendee_emails) >= self.max_attendees:
            return False

        self.attendee_emails.append(email)
        self.updated_at = datetime.now()
        return True

    def remove_attendee(self, email: str) -> bool:
        """
        Remove an attendee.

        Returns:
            True if removed, False if not found
        """
        if email in self.attendee_emails:
            self.attendee_emails.remove(email)
            self.updated_at = datetime.now()
            return True
        return False

    def mark_reminder_sent(self) -> None:
        """Mark reminder as sent."""
        self.reminder_sent = True
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """Convert to dictionary for database operations."""
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=["status", "visibility", "priority", "recurrence_pattern"],
            date_fields=["event_date", "recurrence_end_date"],
            datetime_fields=["created_at", "updated_at"],
            time_fields=["start_time", "end_time"],
        )

    @classmethod
    def from_dict(cls, data: dict) -> "EventDTO":
        """Create DTO from dictionary."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "status": ActivityStatus,
                "visibility": Visibility,
                "priority": Priority,
                "recurrence_pattern": RecurrencePattern,
            },
            date_fields=["event_date", "recurrence_end_date"],
            datetime_fields=["created_at", "updated_at"],
            time_fields=["start_time", "end_time"],
            list_fields=["tags", "attendee_emails"],
        )
