"""
GoalKu - Goal Domain Model
============================

Frozen dataclass for goal entities (KuType.GOAL).

Inherits ~48 common fields from KuBase. Adds 24 goal-specific fields:
- Classification (3): goal_type, timeframe, measurement_type
- Measurement (3): target_value, current_value, unit_of_measurement
- Timeline (3): start_date, target_date, achieved_date
- Progress (4): milestones, progress_percentage, last_progress_update, progress_history
- Motivation (4): vision_statement, why_important, success_criteria, potential_obstacles, strategies
- Cross-domain links (3): source_learning_path_uid, inspired_by_choice_uid, selected_choice_option_uid
- Identity (2): target_identity, identity_evidence_required
- Flags (1): curriculum_driven

Goal-specific methods: calculate_progress, is_on_track, expected_progress_percentage,
diagnose_system_health, calculate_system_strength, calculate_habit_velocity,
is_overdue, is_achieved, days_remaining, get_summary, explain_existence.

See: /.claude/plans/ku-decomposition-domain-types.md (Phase 2)
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO

from core.models.enums.ku_enums import (
    GoalTimeframe,
    GoalType,
    KuStatus,
    KuType,
    MeasurementType,
)
from core.models.ku.ku_base import KuBase
from core.models.ku.ku_nested_types import Milestone


@dataclass(frozen=True)
class GoalKu(KuBase):
    """
    Immutable domain model for goals (KuType.GOAL).

    Inherits ~48 common fields from KuBase (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 24 goal-specific fields for classification, measurement, timeline,
    progress tracking, motivation, cross-domain links, and identity.
    """

    def __post_init__(self) -> None:
        """Force ku_type=GOAL, then delegate to KuBase for timestamps/status defaults."""
        if self.ku_type != KuType.GOAL:
            object.__setattr__(self, "ku_type", KuType.GOAL)
        super().__post_init__()

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    measurement_type: MeasurementType | None = None

    # =========================================================================
    # MEASUREMENT
    # =========================================================================
    target_value: float | None = None
    current_value: float = 0.0
    unit_of_measurement: str | None = None

    # =========================================================================
    # TIMELINE
    # =========================================================================
    start_date: date | None = None  # type: ignore[assignment]
    target_date: date | None = None  # type: ignore[assignment]
    achieved_date: date | None = None  # type: ignore[assignment]

    # =========================================================================
    # PROGRESS
    # =========================================================================
    milestones: tuple[Milestone, ...] = ()
    progress_percentage: float = 0.0
    last_progress_update: datetime | None = None  # type: ignore[assignment]
    progress_history: tuple[dict, ...] = ()  # type: ignore[assignment]

    # =========================================================================
    # MOTIVATION
    # =========================================================================
    vision_statement: str | None = None  # Goal vision
    why_important: str | None = None  # Why this goal matters
    success_criteria: str | None = None
    potential_obstacles: tuple[str, ...] = ()
    strategies: tuple[str, ...] = ()

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    fulfills_goal_uid: str | None = None  # SUB-GOAL -> PARENT GOAL
    source_learning_path_uid: str | None = None  # GOAL -> LP
    inspired_by_choice_uid: str | None = None  # GOAL <- CHOICE
    selected_choice_option_uid: str | None = None  # GOAL <- CHOICE option

    # =========================================================================
    # IDENTITY
    # =========================================================================
    target_identity: str | None = None  # "I am the type of person who..."
    identity_evidence_required: int = 0  # Evidence needed for identity

    # =========================================================================
    # FLAGS
    # =========================================================================
    curriculum_driven: bool = False  # Derived from curriculum

    # =========================================================================
    # GOAL-SPECIFIC METHODS
    # =========================================================================

    def calculate_progress(self) -> float:
        """Calculate goal progress (0.0-1.0)."""
        if self.measurement_type == MeasurementType.PERCENTAGE:
            return min(1.0, self.progress_percentage / 100.0)
        if self.target_value and self.target_value > 0:
            return min(1.0, self.current_value / self.target_value)
        return self.progress_percentage / 100.0 if self.progress_percentage else 0.0

    def get_days_remaining(self) -> int | None:
        """Days until target_date."""
        if not self.target_date:
            return None
        delta = self.target_date - date.today()
        return delta.days

    def days_remaining(self) -> int:
        """Days until target_date (0 if none set or past)."""
        result = self.get_days_remaining()
        return max(0, result) if result is not None else 0

    def expected_progress_percentage(self) -> float:
        """Expected progress based on elapsed time vs total timeline."""
        if not self.start_date or not self.target_date:
            return 0.0
        total = (self.target_date - self.start_date).days
        if total <= 0:
            return 100.0
        elapsed = (date.today() - self.start_date).days
        return min(100.0, max(0.0, (elapsed / total) * 100.0))

    def is_on_track(self) -> bool:
        """Check if progress >= expected progress."""
        expected = self.expected_progress_percentage()
        return self.progress_percentage >= expected if expected > 0 else True

    def is_overdue(self) -> bool:
        """Check if past target_date without completion."""
        if self.is_completed:
            return False
        remaining = self.get_days_remaining()
        return remaining is not None and remaining < 0

    def is_achieved(self) -> bool:
        """Check if goal is achieved (completed status)."""
        return self.status == KuStatus.COMPLETED

    @property
    def is_active(self) -> bool:
        """Check if goal is active (status == ACTIVE)."""
        return self.status == KuStatus.ACTIVE

    def is_past(self) -> bool:
        """Check if target date is in the past."""
        if self.target_date:
            return self.target_date < date.today()
        return False

    def calculate_system_strength(
        self, habit_success_rates: dict[str, float] | None = None
    ) -> float:
        """Calculate goal system strength based on supporting habits."""
        if not habit_success_rates:
            return 0.0
        avg_rate = sum(habit_success_rates.values()) / len(habit_success_rates)
        return min(1.0, avg_rate)

    def calculate_habit_velocity(
        self, habit_completion_counts: dict[str, int] | None = None
    ) -> float:
        """Calculate velocity of habit completion toward goal."""
        if not habit_completion_counts:
            return 0.0
        total = sum(habit_completion_counts.values())
        return min(1.0, total / max(1, len(habit_completion_counts) * 30))

    def diagnose_system_health(
        self, habit_success_rates: dict[str, float] | None = None
    ) -> dict[str, Any]:
        """Diagnose the health of a goal's habit system."""
        strength = self.calculate_system_strength(habit_success_rates)
        return {
            "system_strength": strength,
            "health": "strong" if strength >= 0.7 else "moderate" if strength >= 0.4 else "weak",
            "habit_count": len(habit_success_rates) if habit_success_rates else 0,
        }

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the goal."""
        text = self.description or self.vision_statement or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def explain_existence(self) -> str:
        """Explain why this goal exists."""
        return self.why_important or self.description or self.summary or f"goal: {self.title}"

    @property
    def parent_goal_uid(self) -> str | None:
        """Alias for fulfills_goal_uid (sub-goal → parent goal)."""
        return self.fulfills_goal_uid

    @property
    def category(self) -> str | None:
        """Goal category — uses domain field."""
        return self.domain.value if self.domain else None

    # =========================================================================
    # CONVERSION (generic — uses KuBase._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "GoalKu":
        """Create GoalKu from a KuDTO."""
        return cls._from_dto(dto)

    def __str__(self) -> str:
        return f"GoalKu(uid={self.uid}, title='{self.title}', target={self.target_date})"

    def __repr__(self) -> str:
        return (
            f"GoalKu(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, goal_type={self.goal_type}, "
            f"target_date={self.target_date}, user_uid={self.user_uid})"
        )
