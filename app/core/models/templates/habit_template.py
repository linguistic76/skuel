"""
HabitTemplate — PS-Owned Habit Spawn Blueprint
==============================================

Frozen dataclass for habit templates (EntityType.HABIT_TEMPLATE). PS-owned
via ``HAS_HABIT_TEMPLATE``. Spawns a Habit instance when the owning PS is
engaged.

Excludes per-user state (current_streak, best_streak, total_completions,
total_attempts, success_rate, last_completed, started_at, completed_at,
identity_votes_cast). HabitTemplate is Layer 0 in the spawn order — no
cross-template references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty, HabitPolarity
from core.models.enums.scheduling_enums import TimeOfDay
from core.models.templates.relative_offset import RelativeOffset

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.templates.habit_template_dto import HabitTemplateDTO


@dataclass(frozen=True, kw_only=True)
class HabitTemplate(Entity):
    """Immutable domain model for habit templates (EntityType.HABIT_TEMPLATE)."""

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.HABIT_TEMPLATE, kw_only=True)

    def __post_init__(self) -> None:
        if self.entity_type != EntityType.HABIT_TEMPLATE:
            raise ValueError(
                f"HabitTemplate constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        super().__post_init__()

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    polarity: HabitPolarity | None = None
    habit_category: HabitCategory | None = None
    habit_difficulty: HabitDifficulty | None = None

    # =========================================================================
    # ATOMIC HABITS / BEHAVIOR DESIGN
    # =========================================================================
    cue: str | None = None
    routine: str | None = None
    reward: str | None = None

    # =========================================================================
    # IDENTITY
    # =========================================================================
    reinforces_identity: str | None = None
    is_identity_habit: bool = False
    target_identity: str | None = None
    identity_evidence_required: int = 0

    # =========================================================================
    # SCHEDULING (engagement-relative)
    # =========================================================================
    duration_minutes: int | None = None
    recurrence_pattern: str | None = None
    recurrence_end_offset: RelativeOffset | None = None
    target_days_per_week: int | None = None
    preferred_time: TimeOfDay | None = None

    # =========================================================================
    # REMINDERS (template-authored defaults)
    # =========================================================================
    reminder_time: str | None = None
    reminder_days: tuple[str, ...] = ()
    reminder_enabled: bool = False

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: EntityDTO | HabitTemplateDTO) -> HabitTemplate:
        return cls._from_dto(dto)

    def to_dto(self) -> HabitTemplateDTO:
        from core.models.dto_helpers import domain_to_dto
        from core.models.templates.habit_template_dto import HabitTemplateDTO

        return domain_to_dto(self, HabitTemplateDTO)

    def __str__(self) -> str:
        return f"HabitTemplate(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"HabitTemplate(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, polarity={self.polarity})"
        )
