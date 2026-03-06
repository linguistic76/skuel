"""
Habit - Habit Domain Model
============================

Frozen dataclass for habit entities (EntityType.HABIT).

Inherits common fields from UserOwnedEntity. Adds 31 habit-specific fields:
- Classification (3): polarity, habit_category, habit_difficulty
- Streak Tracking (6): current_streak, best_streak, total_completions,
  total_attempts, success_rate, last_completed
- Atomic Habits / Behavior Design (3): cue, routine, reward
- Identity (5): reinforces_identity, identity_votes_cast, is_identity_habit,
  target_identity, identity_evidence_required
- Lifecycle (2): started_at, completed_at
- Scheduling (6): duration_minutes, recurrence_pattern, recurrence_end_date,
  recurrence_parent_uid, target_days_per_week, preferred_time
- Reminders (3): reminder_time, reminder_days, reminder_enabled
- Cross-domain links (2): source_learning_step_uid, source_learning_path_uid
- Flags (1): curriculum_driven

Habit-specific methods: calculate_consistency_score, is_keystone, should_do_today,
get_effort_score, is_identity_based, get_atomic_habits_analysis, get_summary,
explain_existence, category, from_dto.

See: /.claude/plans/ku-decomposition-domain-types.md
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.habit.habit_dto import HabitDTO

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty, HabitPolarity
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True)
class Habit(UserOwnedEntity):
    """
    Immutable domain model for habits (EntityType.HABIT).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 31 habit-specific fields for classification, streak tracking,
    behavioral science, identity, scheduling, reminders, and cross-domain links.
    """

    def __post_init__(self) -> None:
        """Force entity_type=HABIT, then delegate to Entity for timestamps/status defaults."""
        if self.entity_type != EntityType.HABIT:
            object.__setattr__(self, "entity_type", EntityType.HABIT)
        super().__post_init__()

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    polarity: HabitPolarity | None = None  # BUILD, BREAK, NEUTRAL
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
    last_completed: datetime | None = None  # type: ignore[assignment]

    # =========================================================================
    # ATOMIC HABITS / BEHAVIOR DESIGN
    # =========================================================================
    cue: str | None = None  # Habit loop: cue
    routine: str | None = None  # Habit loop: routine
    reward: str | None = None  # Habit loop: reward

    # =========================================================================
    # IDENTITY
    # =========================================================================
    reinforces_identity: str | None = None  # "I am the type of person who..."
    identity_votes_cast: int = 0
    is_identity_habit: bool = False
    target_identity: str | None = None  # Shared with Goal
    identity_evidence_required: int = 0  # Shared with Goal

    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    started_at: datetime | None = None  # type: ignore[assignment]
    completed_at: datetime | None = None  # type: ignore[assignment]

    # =========================================================================
    # SCHEDULING
    # =========================================================================
    duration_minutes: int | None = None  # Expected duration
    recurrence_pattern: str | None = None  # RecurrencePattern enum value
    recurrence_end_date: date | None = None  # type: ignore[assignment]
    recurrence_parent_uid: str | None = None
    target_days_per_week: int | None = None  # Habit frequency
    preferred_time: str | None = None  # Preferred time of day

    # =========================================================================
    # REMINDERS
    # =========================================================================
    reminder_time: str | None = None
    reminder_days: tuple[str, ...] = ()
    reminder_enabled: bool = False

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    source_learning_step_uid: str | None = None  # HABIT -> LS
    source_learning_path_uid: str | None = None  # HABIT -> LP

    # =========================================================================
    # FLAGS
    # =========================================================================
    curriculum_driven: bool = False
    curriculum_practice_type: str | None = None  # Curriculum connection type

    # =========================================================================
    # HABIT-SPECIFIC METHODS
    # =========================================================================

    @property
    def is_active(self) -> bool:
        """Check if habit is active (status == ACTIVE)."""
        return self.status == EntityStatus.ACTIVE

    def calculate_consistency_score(self) -> float:
        """Calculate habit consistency based on streak and success rate."""
        if self.total_attempts == 0:
            return 0.0
        streak_factor = min(1.0, self.current_streak / 30.0)
        rate_factor = self.success_rate
        return streak_factor * 0.4 + rate_factor * 0.6

    @property
    def is_keystone(self) -> bool:
        """Check if this is a keystone habit (high impact)."""
        return self.is_identity_habit or self.calculate_consistency_score() >= 0.8

    def should_do_today(self) -> bool:
        """Check if a habit should be done today."""
        if not self.is_active:
            return False
        if self.last_completed:
            days_since = (datetime.now() - self.last_completed).days
            if self.target_days_per_week:
                interval = max(1, 7 // self.target_days_per_week)
                return days_since >= interval
        return True

    def get_effort_score(self) -> float:
        """Get habit effort score (0.0-1.0) based on difficulty."""
        if self.habit_difficulty:
            mapping = {
                HabitDifficulty.TRIVIAL: 0.1,
                HabitDifficulty.EASY: 0.3,
                HabitDifficulty.MODERATE: 0.5,
                HabitDifficulty.CHALLENGING: 0.7,
                HabitDifficulty.HARD: 0.9,
            }
            return mapping.get(self.habit_difficulty, 0.5)
        return 0.5

    def is_identity_based(self) -> bool:
        """Check if this is an identity-based habit."""
        return self.is_identity_habit

    def get_atomic_habits_analysis(self) -> dict[str, Any]:
        """Get Atomic Habits analysis for this habit."""
        return {
            "cue": self.cue or "Not defined",
            "routine": self.routine or "Not defined",
            "reward": self.reward or "Not defined",
            "identity": self.reinforces_identity or "Not defined",
            "has_complete_loop": bool(self.cue and self.routine and self.reward),
            "is_identity_based": self.is_identity_habit,
        }

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the habit."""
        text = self.description or self.routine or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def explain_existence(self) -> str:
        """Explain why this habit exists."""
        return self.description or self.routine or self.summary or f"habit: {self.title}"

    @property
    def category(self) -> str | None:
        """Habit category -- uses habit_category field."""
        if self.habit_category:
            return self.habit_category.value
        return self.domain.value if self.domain else None

    @property
    def is_from_learning_step(self) -> bool:
        """Check if this habit originated from a learning step."""
        return self.source_learning_step_uid is not None

    # =========================================================================
    # CONVERSION (generic -- uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | HabitDTO") -> "Habit":
        """Create Habit from an EntityDTO or HabitDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "HabitDTO":  # type: ignore[override]
        """Convert Habit to domain-specific HabitDTO."""
        import dataclasses

        from core.models.habit.habit_dto import HabitDTO

        dto_field_names = {f.name for f in dataclasses.fields(HabitDTO)}
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            if f.name.startswith("_"):
                continue
            if f.name not in dto_field_names:
                continue
            value = getattr(self, f.name)
            if isinstance(value, tuple):
                value = list(value)
            kwargs[f.name] = value
        return HabitDTO(**kwargs)

    def __str__(self) -> str:
        return f"Habit(uid={self.uid}, title='{self.title}', streak={self.current_streak})"

    def __repr__(self) -> str:
        return (
            f"Habit(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, polarity={self.polarity}, "
            f"current_streak={self.current_streak}, user_uid={self.user_uid})"
        )
