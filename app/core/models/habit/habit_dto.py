"""
HabitDTO - Habit-Specific DTO (Tier 2 - Transfer)
===================================================

Extends UserOwnedDTO with 31 habit-specific fields matching the Habit
frozen dataclass (Tier 3): classification, streak tracking, atomic habits,
identity, lifecycle, scheduling, reminders, cross-domain links, and flags.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── HabitDTO(UserOwnedDTO) +31 habit-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import date, datetime

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty, HabitPolarity
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class HabitDTO(UserOwnedDTO):
    """
    Mutable DTO for habits (EntityType.HABIT).

    Extends UserOwnedDTO with 31 habit-specific fields:
    - Classification (3): polarity, habit_category, habit_difficulty
    - Streak (6): current_streak, best_streak, total_completions, total_attempts, success_rate, last_completed
    - Atomic (3): cue, routine, reward
    - Identity (5): reinforces_identity, identity_votes_cast, is_identity_habit, target_identity, identity_evidence_required
    - Lifecycle (2): started_at, completed_at
    - Scheduling (6): duration_minutes, recurrence_pattern, recurrence_end_date, recurrence_parent_uid, target_days_per_week, preferred_time
    - Reminders (3): reminder_time, reminder_days, reminder_enabled
    - Cross-domain links (2): source_learning_step_uid, source_learning_path_uid
    - Flags (2): curriculum_driven, curriculum_practice_type
    """

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    polarity: HabitPolarity | None = None
    habit_category: HabitCategory | None = None
    habit_difficulty: HabitDifficulty | None = None

    # =========================================================================
    # STREAK TRACKING
    # =========================================================================
    current_streak: int = 0
    best_streak: int = 0
    total_completions: int = 0
    total_attempts: int = 0
    success_rate: float = 0.0
    last_completed: datetime | None = None

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
    identity_votes_cast: int = 0
    is_identity_habit: bool = False
    target_identity: str | None = None
    identity_evidence_required: int = 0

    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # =========================================================================
    # SCHEDULING
    # =========================================================================
    duration_minutes: int | None = None
    recurrence_pattern: str | None = None
    recurrence_end_date: date | None = None
    recurrence_parent_uid: str | None = None
    target_days_per_week: int | None = None
    preferred_time: str | None = None

    # =========================================================================
    # REMINDERS
    # =========================================================================
    reminder_time: str | None = None
    reminder_days: list[str] = field(default_factory=list)
    reminder_enabled: bool = False

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    source_learning_step_uid: str | None = None
    source_learning_path_uid: str | None = None

    # =========================================================================
    # FLAGS
    # =========================================================================
    curriculum_driven: bool = False
    curriculum_practice_type: str | None = None

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def create_habit(cls, user_uid: str, title: str, **kwargs: Any) -> HabitDTO:
        """Create a HabitDTO with generated UID and correct defaults."""
        from core.utils.uid_generator import UIDGenerator

        uid = kwargs.pop("uid", None)
        if not uid:
            if title:
                uid = UIDGenerator.generate_uid("habit", title)
            else:
                uid = UIDGenerator.generate_random_uid("habit")

        kwargs.setdefault("status", EntityStatus.DRAFT)
        kwargs.setdefault("visibility", Visibility.PRIVATE)

        return cls(
            uid=uid,
            title=title,
            entity_type=EntityType.HABIT,
            user_uid=user_uid,
            **kwargs,
        )

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including habit-specific fields."""
        from core.models.dto_helpers import convert_dates_to_iso, convert_datetimes_to_iso
        from core.ports import get_enum_value

        data = super().to_dict()

        data.update(
            {
                # Classification
                "polarity": get_enum_value(self.polarity),
                "habit_category": get_enum_value(self.habit_category),
                "habit_difficulty": get_enum_value(self.habit_difficulty),
                # Streak
                "current_streak": self.current_streak,
                "best_streak": self.best_streak,
                "total_completions": self.total_completions,
                "total_attempts": self.total_attempts,
                "success_rate": self.success_rate,
                "last_completed": self.last_completed,
                # Atomic
                "cue": self.cue,
                "routine": self.routine,
                "reward": self.reward,
                # Identity
                "reinforces_identity": self.reinforces_identity,
                "identity_votes_cast": self.identity_votes_cast,
                "is_identity_habit": self.is_identity_habit,
                "target_identity": self.target_identity,
                "identity_evidence_required": self.identity_evidence_required,
                # Lifecycle
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                # Scheduling
                "duration_minutes": self.duration_minutes,
                "recurrence_pattern": self.recurrence_pattern,
                "recurrence_end_date": self.recurrence_end_date,
                "recurrence_parent_uid": self.recurrence_parent_uid,
                "target_days_per_week": self.target_days_per_week,
                "preferred_time": self.preferred_time,
                # Reminders
                "reminder_time": self.reminder_time,
                "reminder_days": list(self.reminder_days) if self.reminder_days else [],
                "reminder_enabled": self.reminder_enabled,
                # Cross-domain links
                "source_learning_step_uid": self.source_learning_step_uid,
                "source_learning_path_uid": self.source_learning_path_uid,
                # Flags
                "curriculum_driven": self.curriculum_driven,
                "curriculum_practice_type": self.curriculum_practice_type,
            }
        )

        convert_dates_to_iso(data, ["recurrence_end_date"])
        convert_datetimes_to_iso(data, ["last_completed", "started_at", "completed_at"])

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HabitDTO:
        """Create HabitDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "polarity": HabitPolarity,
                "habit_category": HabitCategory,
                "habit_difficulty": HabitDifficulty,
            },
            date_fields=["recurrence_end_date"],
            datetime_fields=[
                "created_at",
                "updated_at",
                "last_completed",
                "started_at",
                "completed_at",
            ],
            list_fields=["tags", "reminder_days"],
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
                # Habit-specific fields
                "polarity",
                "habit_category",
                "habit_difficulty",
                "current_streak",
                "best_streak",
                "total_completions",
                "total_attempts",
                "success_rate",
                "last_completed",
                "cue",
                "routine",
                "reward",
                "reinforces_identity",
                "identity_votes_cast",
                "is_identity_habit",
                "target_identity",
                "identity_evidence_required",
                "started_at",
                "completed_at",
                "duration_minutes",
                "recurrence_pattern",
                "recurrence_end_date",
                "recurrence_parent_uid",
                "target_days_per_week",
                "preferred_time",
                "reminder_time",
                "reminder_days",
                "reminder_enabled",
                "source_learning_step_uid",
                "source_learning_path_uid",
                "curriculum_driven",
                "curriculum_practice_type",
            },
            enum_mappings={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "polarity": HabitPolarity,
                "habit_category": HabitCategory,
                "habit_difficulty": HabitDifficulty,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, HabitDTO):
            return False
        return self.uid == other.uid
