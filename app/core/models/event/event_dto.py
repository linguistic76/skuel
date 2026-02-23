"""
EventDTO - Event-Specific DTO (Tier 2 - Transfer)
===================================================

Extends UserOwnedDTO with 26 event-specific fields matching the Event
frozen dataclass (Tier 3): scheduling, logistics, recurrence, reminders,
attendees, cross-domain links, milestones, and quality tracking.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── EventDTO(UserOwnedDTO) +26 event-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from typing import Any

from core.models.enums import Domain
from core.models.enums.ku_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class EventDTO(UserOwnedDTO):
    """
    Mutable DTO for events (EntityType.EVENT).

    Extends UserOwnedDTO with 26 event-specific fields:
    - Scheduling (4): event_date, start_time, end_time, duration_minutes
    - Logistics (4): event_type, location, is_online, meeting_url
    - Recurrence (3): recurrence_pattern, recurrence_end_date, recurrence_parent_uid
    - Reminders (2): reminder_minutes, reminder_sent
    - Attendees (2): attendee_emails, max_attendees
    - Cross-domain links (3): reinforces_habit_uid, source_learning_step_uid, source_learning_path_uid
    - Milestones (4): milestone_celebration_for_goal, is_milestone_event, milestone_type, curriculum_week
    - Quality (4): habit_completion_quality, knowledge_retention_check, recurrence_maintains_habit, skip_breaks_habit_streak
    """

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
    # RECURRENCE
    # =========================================================================
    recurrence_pattern: str | None = None
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
    reinforces_habit_uid: str | None = None
    source_learning_step_uid: str | None = None
    source_learning_path_uid: str | None = None

    # =========================================================================
    # MILESTONE INTEGRATION
    # =========================================================================
    milestone_celebration_for_goal: str | None = None
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
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def create_event(cls, user_uid: str, title: str, **kwargs: Any) -> EventDTO:
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
            ku_type=EntityType.EVENT,
            user_uid=user_uid,
            **kwargs,
        )

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including event-specific fields."""
        from core.models.dto_helpers import convert_dates_to_iso, serialize_time

        data = super().to_dict()

        data.update(
            {
                # Scheduling
                "event_date": self.event_date,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "duration_minutes": self.duration_minutes,
                # Logistics
                "event_type": self.event_type,
                "location": self.location,
                "is_online": self.is_online,
                "meeting_url": self.meeting_url,
                # Recurrence
                "recurrence_pattern": self.recurrence_pattern,
                "recurrence_end_date": self.recurrence_end_date,
                "recurrence_parent_uid": self.recurrence_parent_uid,
                # Reminders
                "reminder_minutes": self.reminder_minutes,
                "reminder_sent": self.reminder_sent,
                # Attendees
                "attendee_emails": list(self.attendee_emails) if self.attendee_emails else [],
                "max_attendees": self.max_attendees,
                # Cross-domain links
                "reinforces_habit_uid": self.reinforces_habit_uid,
                "source_learning_step_uid": self.source_learning_step_uid,
                "source_learning_path_uid": self.source_learning_path_uid,
                # Milestones
                "milestone_celebration_for_goal": self.milestone_celebration_for_goal,
                "is_milestone_event": self.is_milestone_event,
                "milestone_type": self.milestone_type,
                "curriculum_week": self.curriculum_week,
                # Quality
                "habit_completion_quality": self.habit_completion_quality,
                "knowledge_retention_check": self.knowledge_retention_check,
                "recurrence_maintains_habit": self.recurrence_maintains_habit,
                "skip_breaks_habit_streak": self.skip_breaks_habit_streak,
            }
        )

        convert_dates_to_iso(data, ["event_date", "recurrence_end_date"])
        data["start_time"] = serialize_time(data.get("start_time"))
        data["end_time"] = serialize_time(data.get("end_time"))

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventDTO:
        """Create EventDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
            },
            date_fields=["event_date", "recurrence_end_date"],
            datetime_fields=["created_at", "updated_at"],
            time_fields=["start_time", "end_time"],
            list_fields=["tags", "attendee_emails"],
            dict_fields=["metadata"],
            deprecated_fields=["prerequisites", "enables", "related_to", "name"],
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
                "title", "content", "summary", "description", "word_count",
                "domain", "status", "tags", "metadata",
                # UserOwnedDTO fields
                "priority", "visibility",
                # Event-specific fields
                "event_date", "start_time", "end_time", "duration_minutes",
                "event_type", "location", "is_online", "meeting_url",
                "recurrence_pattern", "recurrence_end_date", "recurrence_parent_uid",
                "reminder_minutes", "reminder_sent",
                "attendee_emails", "max_attendees",
                "reinforces_habit_uid", "source_learning_step_uid", "source_learning_path_uid",
                "milestone_celebration_for_goal", "is_milestone_event",
                "milestone_type", "curriculum_week",
                "habit_completion_quality", "knowledge_retention_check",
                "recurrence_maintains_habit", "skip_breaks_habit_streak",
            },
            enum_mappings={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, EventDTO):
            return False
        return self.uid == other.uid
