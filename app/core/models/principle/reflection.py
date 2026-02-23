"""
Principle Reflection Domain Model (Tier 3 - Core)
==================================================

Immutable domain model with business logic for principle reflections.
This is the core business entity that captures moments of alignment assessment
with rich context about triggers and insights.

Architecture:
- Follows HabitCompletion pattern (frozen dataclass with business logic)
- Graph-connected: Links to triggering entities (goals, habits, events, choices)
- Quality scoring: 0-1 based on evidence depth, notes, and trigger context
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from core.models.enums.principle_enums import AlignmentLevel

if TYPE_CHECKING:
    from .reflection_dto import PrincipleReflectionDTO


@dataclass(frozen=True)
class PrincipleReflection:
    """
    Immutable domain model for principle reflections.

    A reflection captures a moment of alignment assessment with rich context
    about what triggered the reflection and any insights gained.

    Graph Relationships (stored as Neo4j edges):
    - (Reflection)-[:REFLECTS_ON]->(Principle)
    - (User)-[:MADE_REFLECTION]->(Reflection)
    - (Reflection)-[:TRIGGERED_BY]->(Goal|Habit|Event|Choice)
    - (Reflection)-[:REVEALS_CONFLICT]->(Principle)
    """

    # Identity (required fields first)
    uid: str
    principle_uid: str
    user_uid: str
    reflection_date: date
    created_at: datetime
    updated_at: datetime

    # Assessment (required)
    alignment_level: AlignmentLevel
    evidence: str  # What was observed (required)

    # Reflection details (optional)
    reflection_notes: str | None = None

    # Quality metrics
    reflection_quality_score: float = 0.0  # 0-1 based on depth

    # Trigger context (what prompted this reflection)
    trigger_type: str | None = None  # "goal", "habit", "event", "choice", "manual"
    trigger_uid: str | None = None  # UID of triggering entity
    trigger_context: str | None = None  # Description of triggering situation

    # Metadata
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Validate and set defaults after creation."""
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

        # Validate alignment level
        if not isinstance(self.alignment_level, AlignmentLevel):
            raise ValueError(
                f"alignment_level must be AlignmentLevel, got {type(self.alignment_level)}"
            )

        # Validate quality score
        if not (0.0 <= self.reflection_quality_score <= 1.0):
            raise ValueError("reflection_quality_score must be between 0.0 and 1.0")

        # Validate trigger_type if provided
        valid_triggers = {"goal", "habit", "event", "choice", "manual", None}
        if self.trigger_type not in valid_triggers:
            raise ValueError(f"trigger_type must be one of {valid_triggers}")

    # ========================================================================
    # FACTORY METHODS
    # ========================================================================

    @classmethod
    def from_dto(cls, dto: "PrincipleReflectionDTO") -> "PrincipleReflection":
        """Create domain model from DTO."""
        return cls(
            uid=dto.uid,
            principle_uid=dto.principle_uid,
            user_uid=dto.user_uid,
            reflection_date=dto.reflection_date,
            alignment_level=dto.alignment_level,
            evidence=dto.evidence,
            reflection_notes=dto.reflection_notes,
            reflection_quality_score=dto.reflection_quality_score,
            trigger_type=dto.trigger_type,
            trigger_uid=dto.trigger_uid,
            trigger_context=dto.trigger_context,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            metadata=dto.metadata or {},
        )

    def to_dto(self) -> "PrincipleReflectionDTO":
        """Convert to DTO for transfer operations."""
        from .reflection_dto import PrincipleReflectionDTO

        return PrincipleReflectionDTO(
            uid=self.uid,
            principle_uid=self.principle_uid,
            user_uid=self.user_uid,
            reflection_date=self.reflection_date,
            alignment_level=self.alignment_level,
            evidence=self.evidence,
            reflection_notes=self.reflection_notes,
            reflection_quality_score=self.reflection_quality_score,
            trigger_type=self.trigger_type,
            trigger_uid=self.trigger_uid,
            trigger_context=self.trigger_context,
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=self.metadata or {},
        )

    # ========================================================================
    # ALIGNMENT ANALYSIS
    # ========================================================================

    def is_positive_alignment(self) -> bool:
        """Check if this reflection indicates positive alignment."""
        return self.alignment_level in [AlignmentLevel.ALIGNED, AlignmentLevel.MOSTLY_ALIGNED]

    def is_negative_alignment(self) -> bool:
        """Check if this reflection indicates misalignment."""
        return self.alignment_level == AlignmentLevel.MISALIGNED

    def is_partial_alignment(self) -> bool:
        """Check if alignment is partial (room for improvement)."""
        return self.alignment_level == AlignmentLevel.PARTIAL

    def alignment_score(self) -> int:
        """
        Get numeric alignment score (0-4) for trend analysis.

        Returns:
            0 (unknown) to 4 (fully aligned)
        """
        scores = {
            AlignmentLevel.ALIGNED: 4,
            AlignmentLevel.MOSTLY_ALIGNED: 3,
            AlignmentLevel.PARTIAL: 2,
            AlignmentLevel.MISALIGNED: 1,
            AlignmentLevel.UNKNOWN: 0,
        }
        return scores.get(self.alignment_level, 0)

    # ========================================================================
    # TRIGGER CONTEXT
    # ========================================================================

    def has_trigger(self) -> bool:
        """Check if this reflection was triggered by a specific entity."""
        return self.trigger_type is not None and self.trigger_type != "manual"

    def was_triggered_by_goal(self) -> bool:
        """Check if reflection was triggered by a goal."""
        return self.trigger_type == "goal"

    def was_triggered_by_habit(self) -> bool:
        """Check if reflection was triggered by a habit."""
        return self.trigger_type == "habit"

    def was_triggered_by_event(self) -> bool:
        """Check if reflection was triggered by an event."""
        return self.trigger_type == "event"

    def was_triggered_by_choice(self) -> bool:
        """Check if reflection was triggered by a choice."""
        return self.trigger_type == "choice"

    def get_trigger_description(self) -> str:
        """Get human-readable description of what triggered this reflection."""
        if not self.has_trigger():
            return "Manual reflection"

        type_labels = {
            "goal": "Goal",
            "habit": "Habit",
            "event": "Event",
            "choice": "Choice",
        }
        label = type_labels.get(self.trigger_type, "Entity")

        if self.trigger_context:
            return f"{label}: {self.trigger_context}"
        elif self.trigger_uid:
            return f"{label} ({self.trigger_uid})"
        else:
            return f"Triggered by {label}"

    # ========================================================================
    # QUALITY ASSESSMENT
    # ========================================================================

    def quality_level(self) -> str:
        """
        Get quality level based on reflection quality score.

        Returns:
            "deep" (>= 0.7), "moderate" (>= 0.4), or "shallow" (< 0.4)
        """
        if self.reflection_quality_score >= 0.7:
            return "deep"
        elif self.reflection_quality_score >= 0.4:
            return "moderate"
        else:
            return "shallow"

    def is_deep_reflection(self) -> bool:
        """Check if this is a deep, high-quality reflection."""
        return self.reflection_quality_score >= 0.7

    def has_meaningful_notes(self) -> bool:
        """Check if reflection has substantive notes."""
        if not self.reflection_notes:
            return False
        cleaned = self.reflection_notes.strip()
        return len(cleaned) > 20 and len(cleaned.split()) > 3

    def has_substantial_evidence(self) -> bool:
        """Check if evidence is substantial."""
        cleaned = self.evidence.strip()
        return len(cleaned) > 30 and len(cleaned.split()) > 5

    # ========================================================================
    # TEMPORAL ANALYSIS
    # ========================================================================

    def days_since_reflection(self) -> int:
        """Calculate days since this reflection was recorded."""
        return (date.today() - self.reflection_date).days

    def was_recent(self, days: int = 7) -> bool:
        """Check if reflection was within the last N days."""
        return self.days_since_reflection() <= days

    def reflection_time_of_day(self) -> str:
        """Get time of day when reflection was created."""
        hour = self.created_at.hour

        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    # ========================================================================
    # COMPARISON
    # ========================================================================

    def is_better_than(self, other: "PrincipleReflection") -> bool:
        """
        Compare this reflection to another reflection.

        Comparison based on alignment score first, then quality score.
        """
        if self.alignment_score() != other.alignment_score():
            return self.alignment_score() > other.alignment_score()
        return self.reflection_quality_score > other.reflection_quality_score

    # ========================================================================
    # STRING REPRESENTATIONS
    # ========================================================================

    def __str__(self) -> str:
        """Human-readable string representation."""
        alignment = self.alignment_level.value.replace("_", " ").title()
        quality = self.quality_level()
        return f"Reflection on {self.reflection_date} - {alignment} ({quality} quality)"

    def __repr__(self) -> str:
        """Technical string representation."""
        return (
            f"PrincipleReflection(uid='{self.uid}', "
            f"principle_uid='{self.principle_uid}', "
            f"alignment={self.alignment_level.value})"
        )
