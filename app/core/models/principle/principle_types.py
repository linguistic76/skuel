"""
Principle Business Logic Types
===============================

Frozen dataclass types used by the principles alignment and reflection services.
These are principle-domain-specific business logic types that do NOT belong
in the unified Ku model.

Types:
- PrincipleExpression: How a principle manifests in specific contexts
- AlignmentAssessment: Assessment of how well actions align with a principle
- PrincipleConflict: Conflict between two principles
- PrincipleAlignment: Alignment between a principle and a goal/habit
- PrincipleDecision: Decision evaluated through the lens of principles

Extracted from principle.py during Ku unification (February 2026).
"""

from dataclasses import dataclass
from datetime import date, datetime
from operator import itemgetter

from core.models.enums.ku_enums import AlignmentLevel


@dataclass(frozen=True)
class PrincipleExpression:
    """How a principle manifests in specific contexts."""

    context: str  # Where it applies (work, family, etc.)
    behavior: str  # How it's expressed
    example: str | None = None  # Concrete example


@dataclass(frozen=True)
class AlignmentAssessment:
    """Assessment of how well current actions align with principle."""

    assessed_date: date
    alignment_level: AlignmentLevel
    evidence: str  # What was observed
    reflection: str | None = None


@dataclass(frozen=True)
class PrincipleConflict:
    """
    Represents a conflict between principles.

    Conflicts arise when two principles suggest different actions
    in the same situation. This model helps track and resolve such tensions.
    """

    conflicting_principle_uid: str  # UID of the conflicting principle
    conflict_description: str  # Description of the conflict
    resolution_strategy: str  # How to resolve when both apply
    priority_in_conflict: int  # Which takes precedence (1 = this principle, 2 = other)

    # Context
    conflict_contexts: tuple[str, ...] = ()  # Situations where conflict arises,
    resolution_examples: tuple[str, ...] = ()  # Examples of successful resolution

    # Tracking
    identified_date: date | None = None  # type: ignore[assignment]
    last_encountered: date | None = None  # type: ignore[assignment]
    resolution_effectiveness: float = 0.5  # 0-1, how well strategy works

    def is_high_priority_conflict(self) -> bool:
        """Check if this principle takes priority in the conflict."""
        return self.priority_in_conflict == 1

    def needs_resolution_update(self) -> bool:
        """Check if resolution strategy needs updating."""
        return self.resolution_effectiveness < 0.7


@dataclass(frozen=True)
class PrincipleAlignment:
    """
    Represents alignment between a principle and a goal/habit.

    This is the key integration point for motivation tracking,
    showing how principles guide specific actions and outcomes.
    """

    principle_uid: str  # UID of the principle
    entity_uid: str  # UID of goal or habit
    entity_type: str  # "goal" or "habit"

    # Alignment assessment
    alignment_level: AlignmentLevel
    alignment_score: float  # 0-1 numeric score

    # Influence description
    influence_description: str  # How principle influences this entity
    influence_weight: float = 1.0  # Strength of influence (0-1)

    # Specific manifestations
    manifestations: tuple[str, ...] = ()  # How principle shows up
    supporting_behaviors: tuple[str, ...] = ()  # Specific behaviors

    # Gaps and tensions
    alignment_gaps: tuple[str, ...] = ()  # Where alignment is weak
    potential_improvements: tuple[str, ...] = ()  # How to strengthen

    # Tracking
    assessed_date: datetime = None  # type: ignore[assignment]
    assessor: str | None = None  # Who made the assessment

    def __post_init__(self) -> None:
        """Set default datetime."""
        if self.assessed_date is None:
            object.__setattr__(self, "assessed_date", datetime.now())

    def is_well_aligned(self) -> bool:
        """Check if alignment is strong."""
        return self.alignment_level in [AlignmentLevel.ALIGNED, AlignmentLevel.MOSTLY_ALIGNED]

    def has_gaps(self) -> bool:
        """Check if there are identified gaps."""
        return len(self.alignment_gaps) > 0

    def strengthen_alignment(self) -> list[str]:
        """
        Generate suggestions to strengthen alignment.

        Returns:
            List of actionable suggestions
        """
        suggestions = []

        # Based on alignment level
        if self.alignment_level == AlignmentLevel.PARTIAL:
            suggestions.extend(
                [
                    "Review and clarify how this supports your principle",
                    "Add specific practices that embody the principle",
                    "Consider adjusting approach to better reflect values",
                ]
            )
        elif self.alignment_level == AlignmentLevel.MOSTLY_ALIGNED:
            suggestions.extend(
                [
                    "Identify and address the remaining gaps",
                    "Make the principle more explicit in your approach",
                    "Strengthen the connecting behaviors",
                ]
            )
        elif self.alignment_level == AlignmentLevel.MISALIGNED:
            suggestions.extend(
                [
                    "Reconsider if this aligns with your values",
                    "Modify the approach to better reflect principles",
                    "Consider if this conflicts with core beliefs",
                ]
            )

        # Add specific improvements if identified
        suggestions.extend(self.potential_improvements)

        return suggestions[:5]  # Return top 5 suggestions


@dataclass(frozen=True)
class PrincipleDecision:
    """
    A decision evaluated through the lens of principles.

    This model captures principle-based decision making,
    helping track how values guide choices and outcomes.
    """

    decision_description: str  # What decision is being made
    options: tuple[str, ...]  # Available options

    # Principle evaluations
    principle_scores: dict[str, dict[str, float]]  # {option: {principle_uid: score}}

    # Recommendation
    recommended_option: str  # Best option based on principles
    recommendation_reason: str  # Why this option aligns best
    recommendation_confidence: float = 0.8  # 0-1 confidence in recommendation

    # Conflicts and tensions
    conflicts: tuple[PrincipleConflict, ...] = ()  # Identified conflicts,
    value_tensions: tuple[str, ...] = ()  # Competing values
    tradeoffs: tuple[str, ...] = ()  # What is sacrificed

    # Decision context
    context: str = ""  # Situation/background,
    importance: str = "medium"  # "high", "medium", "low"
    urgency: str = "normal"  # "urgent", "normal", "flexible"
    stakes: str = "moderate"  # "high", "moderate", "low"

    # Tracking
    timestamp: datetime = None  # type: ignore[assignment]
    decision_maker: str | None = None
    actual_choice: str | None = None  # What was actually chosen,
    outcome_assessment: str | None = None  # How it turned out

    def __post_init__(self) -> None:
        """Set default datetime."""
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    def get_principle_ranking(self) -> list[tuple[str, float]]:
        """
        Rank options by principle alignment.

        Returns:
            List of (option, average_score) tuples sorted by score
        """
        option_scores = []

        for option in self.options:
            if option in self.principle_scores:
                scores = list(self.principle_scores[option].values())
                avg_score = sum(scores) / len(scores) if scores else 0.0
            else:
                avg_score = 0.0
            option_scores.append((option, avg_score))

        return sorted(option_scores, key=itemgetter(1), reverse=True)

    def has_clear_winner(self, threshold: float = 0.2) -> bool:
        """
        Check if there's a clear best option.

        Args:
            threshold: Minimum gap between top options

        Returns:
            True if top option is clearly better
        """
        rankings = self.get_principle_ranking()
        if len(rankings) < 2:
            return True

        top_score = rankings[0][1]
        second_score = rankings[1][1]
        return (top_score - second_score) >= threshold

    def get_conflicting_principles(self) -> list[str]:
        """Get list of principles that conflict in this decision."""
        return [conflict.conflicting_principle_uid for conflict in self.conflicts]

    def was_recommendation_followed(self) -> bool | None:
        """Check if the recommendation was actually followed."""
        if not self.actual_choice:
            return None
        return self.actual_choice == self.recommended_option
