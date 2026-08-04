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
- Cross-domain links (1): source_path_step_uid
- Flags (1): curriculum_practice_type

Habit-specific methods: calculate_consistency_score, is_keystone, should_do_today,
get_effort_score, is_identity_based, predict_goal_impact, get_atomic_habits_analysis,
get_summary, explain_existence, category, from_dto.

See: /.claude/plans/ku-decomposition-domain-types.md
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.habit.habit_dto import HabitDTO

from core.models.enums.activity_enums import EngagementState
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty, HabitPolarity
from core.models.enums.scheduling_enums import RecurrencePattern, TimeOfDay
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True, kw_only=True)
class Habit(UserOwnedEntity):
    """
    Immutable domain model for habits (EntityType.HABIT).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 31 habit-specific fields for classification, streak tracking,
    behavioral science, identity, scheduling, reminders, and cross-domain links.
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.HABIT, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=HABIT, then delegate to Entity for timestamps/status defaults."""
        if self.entity_type != EntityType.HABIT:
            raise ValueError(
                f"Habit constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
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
    last_completed: datetime | None = None

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
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # =========================================================================
    # SCHEDULING
    # =========================================================================
    duration_minutes: int | None = None  # Expected duration
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_date: date | None = None
    recurrence_parent_uid: str | None = None
    target_days_per_week: int | None = None  # Habit frequency
    # Habitual time is a fuzzy slot, never a clock time (habit-rhythm arc M3);
    # consumers needing an hour derive it from TimeOfDay.get_representative_time().
    preferred_time: TimeOfDay | None = None

    # =========================================================================
    # REMINDERS
    # =========================================================================
    reminder_time: str | None = None
    reminder_days: tuple[str, ...] = ()
    reminder_enabled: bool = False

    # =========================================================================
    # DUAL-TRACK PERCEPTION-GAP CHECK-INS (ADR-030)
    # =========================================================================
    # Append-only log of self-rated-vs-measured consistency snapshots, written
    # by the dual-track store_callback. tuple[dict] round-trips through
    # neo4j_mapper as a JSON property with no _from_dto rehydration.
    # See: core/models/shared/dual_track.py.
    dual_track_checkins: tuple[dict, ...] = ()

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    source_path_step_uid: str | None = None  # HABIT -> PS

    # =========================================================================
    # FLAGS
    # =========================================================================
    curriculum_practice_type: str | None = None  # Curriculum connection type

    # =========================================================================
    # PS+ACTIVITY LIFECYCLE
    # =========================================================================
    # Back-reference is (Habit)-[:SPAWNED_FROM]->(HabitTemplate).
    engagement_state: EngagementState | None = None  # None = standalone instance

    # =========================================================================
    # DERIVED FROM EDGE — never persisted.
    # (Habit)-[:SUPPORTS_GOAL]->(Goal); populated at fetch time via
    # enrich_habits_with_goal_links for scoring.
    # =========================================================================
    supports_goal_uid: str | None = None  # DERIVED

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

    def predict_goal_impact(self) -> float:
        """Predict this habit's impact on linked goals (0.0-1.0)."""
        consistency = self.calculate_consistency_score()
        effort = self.get_effort_score()
        return min(1.0, (consistency * 0.7) + (effort * 0.3))

    def get_atomic_habits_analysis(self) -> dict[str, Any]:
        """Get Atomic Habits analysis for this habit.

        Returns nested structure with four categories:
        - identity: Identity reinforcement metrics
        - behavioral_design: Cue/routine/reward completeness
        - habit_quality: Streak, completion, and success metrics
        - system_contribution: Goal system integration
        """
        has_cue = bool(self.cue)
        has_routine = bool(self.routine)
        has_reward = bool(self.reward)
        design_elements = sum([has_cue, has_routine, has_reward])

        votes_to_establishment = max(0, 50 - self.identity_votes_cast)
        identity_strength = (
            min(1.0, self.identity_votes_cast / 50) if self.is_identity_habit else 0.0
        )

        return {
            "identity": {
                "is_identity_based": self.is_identity_habit,
                "identity_strength": identity_strength,
                "votes_cast": self.identity_votes_cast,
                "votes_to_establishment": votes_to_establishment,
                "reinforces_identity": self.reinforces_identity or "Not defined",
            },
            "behavioral_design": {
                "has_cue": has_cue,
                "has_routine": has_routine,
                "has_reward": has_reward,
                "design_completeness": design_elements / 3.0,
            },
            "habit_quality": {
                "current_streak": self.current_streak,
                "best_streak": self.best_streak,
                "is_on_streak": self.current_streak > 0,
                "total_completions": self.total_completions,
                "success_rate": self.success_rate,
            },
            "system_contribution": {
                # GRAPH-NATIVE: conservative placeholder — HabitsPatternService
                # overwrites from live SUPPORTS_GOAL edges before pattern extraction
                "part_of_system": False,
                "consistency_score": self.calculate_consistency_score(),
                # GRAPH-NATIVE: placeholder — filled by HabitsPatternService (graph truth)
                "supports_goal_count": 0,
            },
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
    def is_from_path_step(self) -> bool:
        """Check if this habit originated from a path step."""
        return self.source_path_step_uid is not None

    # =========================================================================
    # CONVERSION (generic -- uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | HabitDTO") -> "Habit":
        """Create Habit from an EntityDTO or HabitDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "HabitDTO":
        """Convert Habit to domain-specific HabitDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.habit.habit_dto import HabitDTO

        return domain_to_dto(self, HabitDTO)

    def __str__(self) -> str:
        return f"Habit(uid={self.uid}, title='{self.title}', streak={self.current_streak})"

    def __repr__(self) -> str:
        return (
            f"Habit(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, polarity={self.polarity}, "
            f"current_streak={self.current_streak}, user_uid={self.user_uid})"
        )
