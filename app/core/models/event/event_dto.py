"""
EventDTO - Event-Specific DTO (Tier 2 - Transfer)
===================================================

Extends UserOwnedDTO with 27 event-specific fields matching the Event
frozen dataclass (Tier 3): scheduling, logistics, lifecycle, recurrence,
reminders, attendees, cross-domain links, milestones, and quality tracking.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── EventDTO(UserOwnedDTO) +27 event-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from datetime import date, datetime, time

from core.models.enum_field_registry import enum_fields_for
from core.models.enums.activity_enums import EngagementState
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.enums.scheduling_enums import RecurrencePattern
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class EventDTO(UserOwnedDTO):
    """
    Mutable DTO for events (EntityType.EVENT).

    Extends UserOwnedDTO with 27 event-specific fields:
    - Scheduling (4): event_date, start_time, end_time, duration_minutes
    - Logistics (4): event_type, location, is_online, meeting_url
    - Lifecycle (1): completed_at
    - Recurrence (3): recurrence_pattern, recurrence_end_date, recurrence_parent_uid
    - Reminders (2): reminder_minutes, reminder_sent
    - Attendees (2): attendee_emails, max_attendees
    - Cross-domain links (1): source_path_step_uid (Habit link is the REINFORCES_HABIT edge)
    - Milestones (3): is_milestone_event, milestone_type, curriculum_week (goal-celebration is the CELEBRATES_GOAL edge)
    - Quality (4): habit_completion_quality, knowledge_retention_check, recurrence_maintains_habit, skip_breaks_habit_streak
    """

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.EVENT, kw_only=True)

    # =========================================================================
    # SCHEDULING
    # =========================================================================
    event_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = None

    # =========================================================================
    # LOGISTICS
    # =========================================================================
    event_type: str | None = None
    location: str | None = None
    is_online: bool = False
    meeting_url: str | None = None

    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    # When the event transitioned into COMPLETED; cleared on reopen.
    completed_at: datetime | None = None

    # =========================================================================
    # RECURRENCE
    # =========================================================================
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_date: date | None = None
    recurrence_parent_uid: str | None = None

    # =========================================================================
    # REMINDERS
    # =========================================================================
    reminder_minutes: int | None = None
    reminder_sent: bool = False

    # =========================================================================
    # ATTENDEES
    # =========================================================================
    attendee_emails: list[str] = field(default_factory=list)
    max_attendees: int | None = None

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    # Event↔Habit linkage is the (Event)-[:REINFORCES_HABIT]->(Habit) graph edge,
    # not a persisted property — intentionally absent from this DTO.
    source_path_step_uid: str | None = None

    # =========================================================================
    # MILESTONE INTEGRATION
    # =========================================================================
    # Goal-celebration linkage is the (Event)-[:CELEBRATES_GOAL]->(Goal) edge.
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
    engagement_state: EngagementState | None = None

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def create_event(cls, user_uid: UserUID, title: str, **kwargs: Any) -> EventDTO:
        """Create an EventDTO with generated UID and correct defaults."""
        from core.utils.uid_generator import UIDGenerator

        uid = kwargs.pop("uid", None)
        if not uid:
            if title:
                uid = UIDGenerator.generate_uid("event", title)
            else:
                uid = UIDGenerator.generate_random_uid("event")

        kwargs.setdefault("status", EntityStatus.DRAFT)
        kwargs.setdefault("visibility", Visibility.PRIVATE)

        return cls(
            uid=uid,
            title=title,
            entity_type=EntityType.EVENT,
            user_uid=user_uid,
            **kwargs,
        )

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary using generic helper."""
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=[
                "entity_type",
                "status",
                "domain",
                "visibility",
                "recurrence_pattern",
            ],
            date_fields=["event_date", "recurrence_end_date"],
            datetime_fields=["created_at", "updated_at", "completed_at"],
            time_fields=["start_time", "end_time"],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventDTO:
        """Create EventDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "visibility",
                "recurrence_pattern",
                "engagement_state",
            ),
            date_fields=["event_date", "recurrence_end_date"],
            datetime_fields=["created_at", "updated_at", "completed_at"],
            time_fields=["start_time", "end_time"],
            list_fields=["tags", "attendee_emails"],
            dict_fields=["metadata"],
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update DTO fields from a dictionary."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(
            self,
            updates,
            allowed_fields={
                # EntityDTO fields
                "title",
                "content",
                "summary",
                "description",
                "word_count",
                "domain",
                "status",
                "tags",
                "metadata",
                # UserOwnedDTO fields
                "priority",
                "visibility",
                # Event-specific fields
                "event_date",
                "start_time",
                "end_time",
                "duration_minutes",
                "event_type",
                "location",
                "is_online",
                "meeting_url",
                "completed_at",
                "recurrence_pattern",
                "recurrence_end_date",
                "recurrence_parent_uid",
                "reminder_minutes",
                "reminder_sent",
                "attendee_emails",
                "max_attendees",
                "source_path_step_uid",
                "is_milestone_event",
                "milestone_type",
                "curriculum_week",
                "habit_completion_quality",
                "knowledge_retention_check",
                "recurrence_maintains_habit",
                "skip_breaks_habit_streak",
                "engagement_state",
            },
            enum_mappings=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "visibility",
                "engagement_state",
            ),
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, EventDTO):
            return False
        return self.uid == other.uid
