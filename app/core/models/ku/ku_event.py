"""
EventKu - Event Domain Model
==============================

Frozen dataclass for event entities (KuType.EVENT).

Inherits ~48 common fields from KuBase. Adds 26 event-specific fields:
- Scheduling (4): event_date, start_time, end_time, duration_minutes
- Event Logistics (4): event_type, location, is_online, meeting_url
- Recurrence (3): recurrence_pattern, recurrence_end_date, recurrence_parent_uid
- Reminders (2): reminder_minutes, reminder_sent
- Attendees (2): attendee_emails, max_attendees
- Cross-domain links (3): reinforces_habit_uid, source_learning_step_uid,
  source_learning_path_uid
- Curriculum/milestone integration (4): milestone_celebration_for_goal,
  is_milestone_event, milestone_type, curriculum_week
- Quality tracking (4): habit_completion_quality, knowledge_retention_check,
  recurrence_maintains_habit, skip_breaks_habit_streak

Event-specific methods: start_datetime, end_datetime, overlaps_with, is_past,
get_summary, explain_existence, category, is_from_learning_step, from_dto.

See: /.claude/plans/ku-decomposition-domain-types.md (Phase 4)
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO

from core.models.enums.ku_enums import KuType
from core.models.ku.ku_base import KuBase


@dataclass(frozen=True)
class EventKu(KuBase):
    """
    Immutable domain model for events (KuType.EVENT).

    Inherits ~48 common fields from KuBase (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 26 event-specific fields for scheduling, logistics, attendees,
    recurrence, reminders, cross-domain links, milestones, and quality tracking.
    """

    def __post_init__(self) -> None:
        """Force ku_type=EVENT, then delegate to KuBase for timestamps/status defaults."""
        if self.ku_type != KuType.EVENT:
            object.__setattr__(self, "ku_type", KuType.EVENT)
        super().__post_init__()

    # =========================================================================
    # SCHEDULING
    # =========================================================================
    event_date: date | None = None  # type: ignore[assignment]
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = None  # Expected duration

    # =========================================================================
    # EVENT LOGISTICS
    # =========================================================================
    event_type: str | None = None  # e.g., "PERSONAL", "MEETING"
    location: str | None = None
    is_online: bool = False
    meeting_url: str | None = None

    # =========================================================================
    # RECURRENCE
    # =========================================================================
    recurrence_pattern: str | None = None  # RecurrencePattern enum value
    recurrence_end_date: date | None = None  # type: ignore[assignment]
    recurrence_parent_uid: str | None = None

    # =========================================================================
    # REMINDERS
    # =========================================================================
    reminder_minutes: int | None = None  # Reminder lead time
    reminder_sent: bool = False

    # =========================================================================
    # ATTENDEES
    # =========================================================================
    attendee_emails: tuple[str, ...] = ()
    max_attendees: int | None = None

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    reinforces_habit_uid: str | None = None  # EVENT -> HABIT
    source_learning_step_uid: str | None = None  # EVENT -> LS
    source_learning_path_uid: str | None = None  # EVENT -> LP

    # =========================================================================
    # CURRICULUM / MILESTONE INTEGRATION
    # =========================================================================
    milestone_celebration_for_goal: str | None = None  # EVENT -> GOAL milestone
    is_milestone_event: bool = False
    milestone_type: str | None = None
    curriculum_week: int | None = None

    # =========================================================================
    # QUALITY TRACKING
    # =========================================================================
    habit_completion_quality: int | None = None
    knowledge_retention_check: bool = False
    recurrence_maintains_habit: bool = False
    skip_breaks_habit_streak: bool = False

    # =========================================================================
    # EVENT-SPECIFIC METHODS
    # =========================================================================

    def start_datetime(self) -> datetime | None:
        """Get event start as datetime."""
        if self.event_date and self.start_time:
            return datetime.combine(self.event_date, self.start_time)
        return None

    def end_datetime(self) -> datetime | None:
        """Get event end as datetime."""
        if self.event_date and self.end_time:
            return datetime.combine(self.event_date, self.end_time)
        if self.event_date and self.start_time and self.duration_minutes:
            start = datetime.combine(self.event_date, self.start_time)
            return start + timedelta(minutes=self.duration_minutes)
        return None

    def overlaps_with(self, other: "EventKu") -> bool:
        """Check if two events overlap in time."""
        my_start = self.start_datetime()
        my_end = self.end_datetime()
        other_start = other.start_datetime()
        other_end = other.end_datetime()
        if not all([my_start, my_end, other_start, other_end]):
            return False
        return my_start < other_end and other_start < my_end  # type: ignore[operator]

    def is_past(self) -> bool:
        """Check if event date is in the past."""
        if self.event_date:
            return self.event_date < date.today()
        return False

    @property
    def category(self) -> str | None:
        """Event category -- uses domain field (events have no special category)."""
        return self.domain.value if self.domain else None

    @property
    def is_from_learning_step(self) -> bool:
        """Check if this event originated from a learning step."""
        return self.source_learning_step_uid is not None

    @property
    def fulfills_learning_step(self) -> bool:
        """Check if this event fulfills a learning step."""
        return self.source_learning_step_uid is not None

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the event."""
        text = self.description or self.content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def explain_existence(self) -> str:
        """Explain why this event exists."""
        return self.description or self.summary or f"event: {self.title}"

    # =========================================================================
    # CONVERSION (generic -- uses KuBase._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "EventKu":
        """Create EventKu from a KuDTO."""
        return cls._from_dto(dto)

    def __str__(self) -> str:
        return f"EventKu(uid={self.uid}, title='{self.title}', date={self.event_date})"

    def __repr__(self) -> str:
        return (
            f"EventKu(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, event_date={self.event_date}, "
            f"event_type={self.event_type}, user_uid={self.user_uid})"
        )
