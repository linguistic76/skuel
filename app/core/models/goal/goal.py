"""
Goal - Goal Domain Model
============================

Frozen dataclass for goal entities (EntityType.GOAL).

Inherits common fields from UserOwnedEntity. Adds 24 goal-specific fields:
- Classification (3): goal_type, timeframe, measurement_type
- Measurement (3): target_value, current_value, unit_of_measurement
- Timeline (3): start_date, target_date, achieved_date
- Progress (4): milestones, progress_percentage, last_progress_update, progress_history
- Motivation (4): vision_statement, why_important, success_criteria, potential_obstacles, strategies
- Cross-domain links (3): fulfills_goal_uid, source_path_step_uid, selected_choice_option_uid (Choice inspiration is a graph edge — see below)
- Identity (2): target_identity, identity_evidence_required

Goal-specific methods: calculate_progress, is_on_track, expected_progress_percentage,
diagnose_system_health, calculate_system_strength, calculate_habit_velocity,
is_overdue, is_achieved, days_remaining, get_summary, explain_existence.

See: /.claude/plans/ku-decomposition-domain-types.md
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.goal.goal_dto import GoalDTO

from core.models.enums.activity_enums import EngagementState
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.goal.milestone import Milestone
from core.models.user_owned_entity import UserOwnedEntity
from core.utils.type_converters import finite_float


@dataclass(frozen=True, kw_only=True)
class Goal(UserOwnedEntity):
    """
    Immutable domain model for goals (EntityType.GOAL).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 24 goal-specific fields for classification, measurement, timeline,
    progress tracking, motivation, cross-domain links, and identity.
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.GOAL, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=GOAL, then delegate to Entity for timestamps/status defaults."""
        if self.entity_type != EntityType.GOAL:
            raise ValueError(
                f"Goal constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        super().__post_init__()
        # Enforce deep immutability: wrap each mutable dict inside progress_history
        if self.progress_history:
            object.__setattr__(
                self,
                "progress_history",
                tuple(
                    MappingProxyType(entry) if isinstance(entry, dict) else entry
                    for entry in self.progress_history
                ),
            )

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    measurement_type: MeasurementType | None = None

    # =========================================================================
    # MEASUREMENT
    # =========================================================================
    # DOMAIN UNITS, named by unit_of_measurement — 25 of 100 miles, 3 of 10 books,
    # a 30-day streak. NOT a percent, and NOT a progress source: progress_percentage
    # below is the percent, and it is the only thing calculate_progress() reads. This
    # pair is the measurement `{current}/{target} {unit}` renders. A writer that has
    # computed a percent writes progress_percentage and leaves current_value alone;
    # only a writer holding a real measurement in target_value's unit may touch it.
    target_value: float | None = None
    current_value: float = 0.0
    unit_of_measurement: str | None = None

    # =========================================================================
    # TIMELINE
    # =========================================================================
    start_date: date | None = None
    target_date: date | None = None
    achieved_date: date | None = None

    # =========================================================================
    # PROGRESS
    # =========================================================================
    milestones: tuple[Milestone, ...] = ()
    progress_percentage: float = 0.0
    last_progress_update: datetime | None = None
    progress_history: tuple[dict, ...] = ()

    # Dual-track perception-gap check-ins (ADR-030). Append-only log of
    # self-rated-vs-measured progress snapshots, written by the dual-track
    # store_callback. tuple[dict] (not a typed record) round-trips through
    # neo4j_mapper as a JSON property with no _from_dto rehydration — same
    # shape as progress_history above. See: core/models/shared/dual_track.py.
    dual_track_checkins: tuple[dict, ...] = ()

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
    source_path_step_uid: str | None = None  # GOAL -> PS
    # Goal <- Choice linkage lives in the graph as (Goal)-[:INSPIRED_BY_CHOICE]->(Choice).
    selected_choice_option_uid: str | None = None  # GOAL <- CHOICE option

    # =========================================================================
    # IDENTITY
    # =========================================================================
    target_identity: str | None = None  # "I am the type of person who..."
    identity_evidence_required: int = 0  # Evidence needed for identity

    # =========================================================================
    # PS+ACTIVITY LIFECYCLE
    # =========================================================================
    # Back-reference is (Goal)-[:SPAWNED_FROM]->(GoalTemplate).
    engagement_state: EngagementState | None = None  # None = standalone instance

    # =========================================================================
    # GOAL-SPECIFIC METHODS
    # =========================================================================

    def calculate_progress(self) -> float:
        """Calculate goal progress (0.0-1.0) from ``progress_percentage``.

        ``progress_percentage`` (0-100) is the *only* progress field — every writer in
        ``GoalsProgressService`` maintains it and ``complete_goal`` settles it at 100.
        ``current_value``/``target_value`` are the domain-unit measurement (see the
        MEASUREMENT block above) and are deliberately not consulted: reading them when
        the percent is 0 cannot tell a goal whose progress was never recorded from one
        explicitly reset to 0%, and ``progress_percentage`` has no unset state to
        distinguish the two. A goal that wants to show progress carries the percent;
        the measurement pair is what ``{current}/{target} {unit}`` renders.

        Uninterpretable stored values read as no progress rather than raising. This
        method has no ``Result`` channel and is called while rendering every goal card,
        list and sort, so a raise takes down the whole page; the one caller that *can*
        report — ``VisualizationService.format_goal_gantt`` — reads the raw field and
        fails loudly, so bad data still surfaces.
        """
        percent = finite_float(self.progress_percentage)
        if percent is None:
            return 0.0
        return min(1.0, max(0.0, percent / 100.0))

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
        return self.status == EntityStatus.COMPLETED

    @property
    def is_active(self) -> bool:
        """Check if goal is active (status == ACTIVE)."""
        return self.status == EntityStatus.ACTIVE

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
        """Diagnose the health of a goal's habit system.

        Returns dict with keys: system_strength, health, habit_count,
        system_exists, diagnosis, warnings, recommendations.
        """
        strength = self.calculate_system_strength(habit_success_rates)
        habit_count = len(habit_success_rates) if habit_success_rates else 0
        system_exists = habit_count > 0
        health = "strong" if strength >= 0.7 else "moderate" if strength >= 0.4 else "weak"

        # Build diagnosis text
        if not system_exists:
            diagnosis = "No supporting habits linked to this goal"
        elif health == "strong":
            diagnosis = f"Goal system is strong with {habit_count} supporting habits"
        elif health == "moderate":
            diagnosis = (
                f"Goal system needs attention — {habit_count} habits at moderate consistency"
            )
        else:
            diagnosis = f"Goal system is weak — {habit_count} habits with low consistency"

        # Build warnings
        warnings: list[str] = []
        if not system_exists:
            warnings.append(
                "No habits support this goal — progress depends entirely on manual effort"
            )
        elif habit_count < 2:
            warnings.append("Only one supporting habit — system is fragile")
        if habit_success_rates:
            low_performers = [uid for uid, rate in habit_success_rates.items() if rate < 0.3]
            if low_performers:
                warnings.append(f"{len(low_performers)} habit(s) below 30% success rate")

        # Build recommendations
        recommendations: list[str] = []
        if not system_exists:
            recommendations.append("Link at least 2-3 habits to create a supporting system")
        elif habit_count < 3:
            recommendations.append("Add more supporting habits to strengthen the system")
        if health == "weak":
            recommendations.append("Focus on making existing habits easier before adding new ones")
        if health == "moderate":
            recommendations.append("Improve consistency of weakest habits first")

        return {
            "system_strength": strength,
            "health": health,
            "habit_count": habit_count,
            "system_exists": system_exists,
            "diagnosis": diagnosis,
            "warnings": warnings,
            "recommendations": recommendations,
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
    # CONVERSION (generic — uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | GoalDTO") -> "Goal":
        """Create Goal from an EntityDTO or GoalDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "GoalDTO":
        """Convert Goal to domain-specific GoalDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.goal.goal_dto import GoalDTO

        return domain_to_dto(self, GoalDTO)

    def __str__(self) -> str:
        return f"Goal(uid={self.uid}, title='{self.title}', target={self.target_date})"

    def __repr__(self) -> str:
        return (
            f"Goal(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, goal_type={self.goal_type}, "
            f"target_date={self.target_date}, user_uid={self.user_uid})"
        )
