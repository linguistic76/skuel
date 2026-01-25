"""
Habit DTO (Tier 2 - Transfer)
==============================

Mutable data transfer object for Habit operations.
Used internally by services for data manipulation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from core.models.activity_dto_mixin import ActivityDTOMixin
from core.models.shared_enums import Priority, RecurrencePattern

from ..habit.habit import HabitCategory, HabitDifficulty, HabitPolarity, HabitStatus


@dataclass
class HabitDTO(ActivityDTOMixin):
    """
    Mutable data transfer object for Habit.

    Used by services to:
    - Create new habits
    - Update existing habits
    - Transfer data between layers
    """

    # Class variable for UID generation (ActivityDTOMixin)
    _uid_prefix: ClassVar[str] = "habit"

    # Identity
    uid: str
    user_uid: str  # REQUIRED - habit ownership
    name: str
    description: str | None = None

    # Behavior Definition
    polarity: HabitPolarity = HabitPolarity.BUILD
    category: HabitCategory = HabitCategory.OTHER
    difficulty: HabitDifficulty = HabitDifficulty.MODERATE

    # Schedule & Recurrence
    recurrence_pattern: RecurrencePattern = RecurrencePattern.DAILY
    target_days_per_week: int = 7
    preferred_time: str | None = None
    duration_minutes: int = 15

    # Reminders
    reminder_time: str | None = None  # HH:MM format
    reminder_days: list[str] = field(default_factory=list)  # Days of week
    reminder_enabled: bool = False

    # Curriculum Spine Integration (NEW - habit ↔ ls ↔ lp)
    source_learning_step_uid: str | None = None  # ls: UID if habit generated from curriculum
    source_learning_path_uid: str | None = None  # lp: UID for path-level habits
    curriculum_practice_type: str | None = (
        None  # 'daily_review', 'weekly_practice', 'skill_building'
    )

    # Progress Tracking
    current_streak: int = 0
    best_streak: int = 0
    total_completions: int = 0
    total_attempts: int = 0
    success_rate: float = 0.0
    last_completed: datetime | None = None

    # Behavioral Science
    cue: str | None = None
    routine: str | None = None
    reward: str | None = None

    # Atomic Habits Integration (Identity-Based Habits)
    # James Clear: "Every action you take is a vote for the type of person you wish to become."
    reinforces_identity: str | None = None
    identity_votes_cast: int = 0
    is_identity_habit: bool = False

    # Status
    status: HabitStatus = HabitStatus.ACTIVE
    priority: Priority = Priority.MEDIUM

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Tags (mutable list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(
        default_factory=dict
    )  # Rich context storage (graph neighborhoods, etc.)

    # ==========================================================================
    # FACTORY METHODS
    # ==========================================================================

    @classmethod
    def create(
        cls,
        user_uid: str,
        name: str,
        category: HabitCategory = HabitCategory.OTHER,
        difficulty: HabitDifficulty = HabitDifficulty.MODERATE,
        recurrence_pattern: RecurrencePattern = RecurrencePattern.DAILY,
        duration_minutes: int = 15,
        **kwargs: Any,
    ) -> "HabitDTO":
        """
        Factory method to create new HabitDTO with defaults.

        Args:
            user_uid: User UID (REQUIRED - fail-fast philosophy),
            name: Habit name,
            category: Habit category,
            difficulty: Difficulty level,
            recurrence_pattern: How often to perform,
            duration_minutes: Expected duration
            **kwargs: Additional fields

        Returns:
            New HabitDTO instance
        """
        return cls._create_activity_dto(
            user_uid=user_uid,
            name=name,
            category=category,
            difficulty=difficulty,
            recurrence_pattern=recurrence_pattern,
            duration_minutes=duration_minutes,
            **kwargs,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HabitDTO":
        """
        Create DTO from dictionary.

        Args:
            data: Dictionary with habit data

        Returns:
            HabitDTO instance
        """
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "polarity": HabitPolarity,
                "category": HabitCategory,
                "difficulty": HabitDifficulty,
                "status": HabitStatus,
                "priority": Priority,
                "recurrence_pattern": RecurrencePattern,
            },
            datetime_fields=[
                "created_at",
                "updated_at",
                "started_at",
                "completed_at",
                "last_completed",
            ],
            list_fields=["tags", "reminder_days"],
            dict_fields=["metadata"],
        )

    # ==========================================================================
    # UPDATE METHODS
    # ==========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
        """
        Update DTO fields from dictionary.

        Args:
            updates: Dictionary of fields to update
        """
        from core.models.dto_helpers import update_from_dict

        update_from_dict(
            self,
            updates,
            enum_mappings={
                "polarity": HabitPolarity,
                "category": HabitCategory,
                "difficulty": HabitDifficulty,
                "status": HabitStatus,
                "priority": Priority,
                "recurrence_pattern": RecurrencePattern,
            },
            skip_none=False,
        )

    def record_completion(self, _notes: str | None = None) -> None:
        """
        Record a habit completion, updating streaks and statistics.

        Args:
            notes: Optional completion notes
        """
        self.total_completions += 1
        self.total_attempts += 1

        # Update streak
        if self.is_continuing_streak():
            self.current_streak += 1
        else:
            self.current_streak = 1

        # Update best streak
        if self.current_streak > self.best_streak:
            self.best_streak = self.current_streak

        # Update success rate
        self.success_rate = self.total_completions / self.total_attempts

        # Update last completed
        self.last_completed = datetime.now()
        self.updated_at = datetime.now()

    def record_skip(self, _reason: str | None = None) -> None:
        """
        Record a skipped habit session.

        Args:
            reason: Optional reason for skipping
        """
        self.total_attempts += 1
        self.current_streak = 0  # Break the streak

        # Update success rate
        self.success_rate = self.total_completions / self.total_attempts
        self.updated_at = datetime.now()

    # ==========================================================================
    # HELPER METHODS
    # ==========================================================================

    def is_continuing_streak(self) -> bool:
        """Check if completing now would continue the streak."""
        if not self.last_completed:
            return True  # First completion starts a streak

        days_since = (datetime.now() - self.last_completed).days

        if self.recurrence_pattern == RecurrencePattern.DAILY:
            return days_since <= 1
        elif self.recurrence_pattern == RecurrencePattern.WEEKLY:
            return days_since <= 7
        else:
            return days_since <= 30

    # ==========================================================================
    # CONVERSION METHODS
    # ==========================================================================

    def to_dict(self) -> dict[str, Any]:
        """
        Convert DTO to dictionary for storage.

        Returns:
            Dictionary representation
        """
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=[
                "polarity",
                "category",
                "difficulty",
                "status",
                "priority",
                "recurrence_pattern",
            ],
            datetime_fields=[
                "created_at",
                "updated_at",
                "started_at",
                "completed_at",
                "last_completed",
            ],
        )
