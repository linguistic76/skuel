"""
EventTemplate — PS-Owned Event Spawn Blueprint
==============================================

Frozen dataclass for event templates (EntityType.EVENT_TEMPLATE). PS-owned
via ``HAS_EVENT_TEMPLATE``. Spawns an Event instance when the owning PS is
engaged.

EventTemplate is Layer 2 in spawn order — depends on HabitTemplate
(``reinforces_habit_template_uid``) and GoalTemplate
(``milestone_celebration_for_goal_template_uid``).

Excludes per-user state (reminder_sent, attendee_emails — those are
per-engagement). ``start_time``/``end_time`` are kept as time-of-day; only
the date component becomes engagement-relative via ``event_offset``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.templates.relative_offset import RelativeOffset

if TYPE_CHECKING:
    from datetime import time

    from core.models.entity_dto import EntityDTO
    from core.models.templates.event_template_dto import EventTemplateDTO


@dataclass(frozen=True, kw_only=True)
class EventTemplate(Entity):
    """Immutable domain model for event templates (EntityType.EVENT_TEMPLATE)."""

    def __post_init__(self) -> None:
        if self.entity_type != EntityType.EVENT_TEMPLATE:
            object.__setattr__(self, "entity_type", EntityType.EVENT_TEMPLATE)
        super().__post_init__()

    # =========================================================================
    # SCHEDULING (engagement-relative date + absolute time-of-day)
    # =========================================================================
    event_offset: RelativeOffset | None = None
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = None

    # =========================================================================
    # EVENT LOGISTICS
    # =========================================================================
    event_type: str | None = None
    location: str | None = None
    is_online: bool = False
    meeting_url: str | None = None

    # =========================================================================
    # RECURRENCE
    # =========================================================================
    recurrence_pattern: str | None = None
    recurrence_end_offset: RelativeOffset | None = None

    # =========================================================================
    # REMINDERS (template-authored default lead time)
    # =========================================================================
    reminder_minutes: int | None = None

    # =========================================================================
    # ATTENDEES (template caps; instance fills emails)
    # =========================================================================
    max_attendees: int | None = None

    # =========================================================================
    # CROSS-TEMPLATE REFERENCES
    # =========================================================================
    reinforces_habit_template_uid: str | None = None
    milestone_celebration_for_goal_template_uid: str | None = None

    # =========================================================================
    # MILESTONE / CURRICULUM INTEGRATION
    # =========================================================================
    is_milestone_event: bool = False
    milestone_type: str | None = None
    curriculum_week: int | None = None

    # =========================================================================
    # QUALITY TRACKING (template-authored defaults)
    # =========================================================================
    knowledge_retention_check: bool = False
    recurrence_maintains_habit: bool = False
    skip_breaks_habit_streak: bool = False

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: EntityDTO | EventTemplateDTO) -> EventTemplate:
        return cls._from_dto(dto)

    def to_dto(self) -> EventTemplateDTO:
        from core.models.dto_helpers import domain_to_dto
        from core.models.templates.event_template_dto import EventTemplateDTO

        return domain_to_dto(self, EventTemplateDTO)

    def __str__(self) -> str:
        return f"EventTemplate(uid={self.uid}, title='{self.title}', offset={self.event_offset})"

    def __repr__(self) -> str:
        return (
            f"EventTemplate(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, event_offset={self.event_offset})"
        )
