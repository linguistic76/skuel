"""
Event - Event Domain Model
==============================

Frozen dataclass for event entities (EntityType.EVENT).

Inherits common fields from UserOwnedEntity. Adds 26 event-specific fields:
- Scheduling (4): event_date, start_time, end_time, duration_minutes
- Event Logistics (4): event_type, location, is_online, meeting_url
- Recurrence (3): recurrence_pattern, recurrence_end_date, recurrence_parent_uid
- Reminders (2): reminder_minutes, reminder_sent
- Attendees (2): attendee_emails, max_attendees
- Cross-domain links (1): source_path_step_uid (Habit link is the REINFORCES_HABIT edge)
- Curriculum/milestone integration (3): is_milestone_event, milestone_type,
  curriculum_week (goal-celebration linkage is the CELEBRATES_GOAL graph edge)
- Quality tracking (4): habit_completion_quality, knowledge_retention_check,
  recurrence_maintains_habit, skip_breaks_habit_streak

Event-specific methods: start_datetime, end_datetime, overlaps_with, is_past,
get_summary, explain_existence, category, is_from_path_step, from_dto.

See: /.claude/plans/ku-decomposition-domain-types.md
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.event.event_dto import EventDTO

from core.models.enums.activity_enums import EngagementState
from core.models.enums.entity_enums import EntityType
from core.models.enums.scheduling_enums import RecurrencePattern
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True, kw_only=True)
class Event(UserOwnedEntity):
    """
    Immutable domain model for events (EntityType.EVENT).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 26 event-specific fields for scheduling, logistics, attendees,
    recurrence, reminders, cross-domain links, milestones, and quality tracking.
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.EVENT, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=EVENT, then delegate to Entity for timestamps/status defaults."""
        if self.entity_type != EntityType.EVENT:
            raise ValueError(
                f"Event constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        super().__post_init__()

    # =========================================================================
    # SCHEDULING
    # =========================================================================
    event_date: date | None = None
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
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_date: date | None = None
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
    source_path_step_uid: str | None = None  # EVENT -> PS
    # DERIVED FROM EDGE — never a node property. The Event↔Habit link is the graph edge
    # (Event)-[:REINFORCES_HABIT]->(Habit), the single source of truth; the mapper's
    # RELATIONSHIP_SKIP_FIELDS keeps this field out of the node. It is populated at fetch
    # time (scoring, analytics, grouping) from the edge via enrich_events_with_habit_links
    # so pure readers can use it.
    #
    # Absence from EventDTO used to be the whole argument for "never written", and it was
    # not enough: the generated CRUD route converts the request and persists the ENTITY,
    # so ``POST /api/events/create`` wrote this as a property no reader consults while
    # writing no edge. ``EventsService.create_event`` — the request door — writes the edge
    # and is unaffected. (Measured with Tasks' identical defect; see task.py.)
    reinforces_habit_uid: str | None = None  # DERIVED — see note above
    # DERIVED FROM EDGE — never persisted. The Event→Goal link is the graph edge
    # (Event)-[:CONTRIBUTES_TO_GOAL]->(Goal); populated at fetch time via
    # enrich_events_with_goal_links for scoring. The edge is the single source of truth.
    contributes_to_goal_uid: str | None = None  # DERIVED — see note above

    # =========================================================================
    # CURRICULUM / MILESTONE INTEGRATION
    # =========================================================================
    # Event -> Goal milestone linkage lives in the graph as
    # (Event)-[:CELEBRATES_GOAL]->(Goal). Use EventsService.get_celebrated_goal().
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
    # PS+ACTIVITY LIFECYCLE
    # =========================================================================
    # Back-reference is (Event)-[:SPAWNED_FROM]->(EventTemplate).
    engagement_state: EngagementState | None = None  # None = standalone instance

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

    def overlaps_with(self, other: "Event") -> bool:
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

    def is_today(self) -> bool:
        """Check if event date is today."""
        if self.event_date:
            return self.event_date == date.today()
        return False

    def is_upcoming(self) -> bool:
        """Check if event is in the future and not completed."""
        if self.status and self.status.value == "completed":
            return False
        return not self.is_past()

    @property
    def category(self) -> str | None:
        """Event category -- uses domain field (events have no special category)."""
        return self.domain.value if self.domain else None

    @property
    def is_from_path_step(self) -> bool:
        """Check if this event originated from a path step."""
        return self.source_path_step_uid is not None

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
    # CONVERSION (generic -- uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | EventDTO") -> "Event":
        """Create Event from an EntityDTO or EventDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "EventDTO":
        """Convert Event to domain-specific EventDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.event.event_dto import EventDTO

        return domain_to_dto(self, EventDTO)

    def __str__(self) -> str:
        return f"Event(uid={self.uid}, title='{self.title}', date={self.event_date})"

    def __repr__(self) -> str:
        return (
            f"Event(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, event_date={self.event_date}, "
            f"event_type={self.event_type}, user_uid={self.user_uid})"
        )
