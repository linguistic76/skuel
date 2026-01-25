"""
Dual-Track Assessment Result Model
==================================

Generic model for dual-track assessment results.

Captures both user self-assessment (vision) and system measurement (action),
enabling gap analysis between perception and reality.

This implements SKUEL's core philosophy:
"The user's vision is understood via the words they use to communicate,
the UserContext is determined via user's actions."

Created: January 2026
ADR: ADR-030 (Dual-Track Assessment Pattern)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, TypeVar

# Generic type var for level enum (AlignmentLevel, ConfidenceLevel, etc.)
L = TypeVar("L", bound=Enum)


@dataclass(frozen=True)
class DualTrackResult(Generic[L]):
    """
    Generic dual-track assessment result.

    Captures both user self-assessment and system measurement,
    enabling gap analysis between perception and reality.

    Type Parameter:
        L: Level enum type (AlignmentLevel, ConfidenceLevel, MasteryLevel, etc.)

    Attributes:
        entity_uid: UID of the assessed entity
        entity_type: EntityType value (e.g., "principle", "goal", "habit")

        # USER-DECLARED (Vision)
        user_level: User's self-reported level
        user_score: Normalized score 0.0-1.0
        user_evidence: User's evidence for their assessment
        user_reflection: Optional reflection

        # SYSTEM-CALCULATED (Action)
        system_level: System-measured level
        system_score: Normalized score 0.0-1.0
        system_evidence: Evidence from system measurement

        # GAP ANALYSIS (Insight)
        perception_gap: Absolute difference (0.0-1.0)
        gap_direction: "user_higher" | "system_higher" | "aligned"

        # GENERATED INSIGHTS
        insights: Tuple of insight strings
        recommendations: Tuple of recommendation strings

    Example:
        >>> from core.models.principle.principle import AlignmentLevel
        >>> result = DualTrackResult[AlignmentLevel](
        ...     entity_uid="principle.integrity",
        ...     entity_type="principle",
        ...     user_level=AlignmentLevel.ALIGNED,
        ...     user_score=1.0,
        ...     user_evidence="I always act with integrity",
        ...     user_reflection="This is my core value",
        ...     system_level=AlignmentLevel.MOSTLY_ALIGNED,
        ...     system_score=0.75,
        ...     system_evidence=("Goal 'Be Honest' embodies this",),
        ...     perception_gap=0.25,
        ...     gap_direction="user_higher",
        ...     insights=("Self-assessment is higher than measured behavior",),
        ...     recommendations=("Track specific instances of integrity",),
        ... )
        >>> result.has_perception_gap()
        True
    """

    # Entity identification
    entity_uid: str
    entity_type: str

    # USER-DECLARED (Vision)
    user_level: L
    user_score: float  # 0.0-1.0 normalized
    user_evidence: str
    user_reflection: str | None

    # SYSTEM-CALCULATED (Action)
    system_level: L
    system_score: float  # 0.0-1.0 normalized
    system_evidence: tuple[str, ...]

    # GAP ANALYSIS (Insight)
    perception_gap: float  # Absolute difference (0.0-1.0)
    gap_direction: str  # "user_higher" | "system_higher" | "aligned"

    # GENERATED INSIGHTS
    insights: tuple[str, ...]
    recommendations: tuple[str, ...]

    def has_perception_gap(self, threshold: float = 0.15) -> bool:
        """
        Check if gap exceeds threshold.

        Args:
            threshold: Gap threshold (default 0.15 = 15%)

        Returns:
            True if perception gap >= threshold
        """
        return self.perception_gap >= threshold

    def is_self_aware(self) -> bool:
        """
        Check if user perception matches system measurement.

        Returns:
            True if gap_direction is "aligned"
        """
        return self.gap_direction == "aligned"

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for API responses.

        Returns:
            Dict with all fields, handling enum conversion
        """
        # Handle level enums - extract .value for Enum types
        user_level_value = (
            self.user_level.value if isinstance(self.user_level, Enum) else self.user_level
        )
        system_level_value = (
            self.system_level.value if isinstance(self.system_level, Enum) else self.system_level
        )

        return {
            "entity_uid": self.entity_uid,
            "entity_type": self.entity_type,
            "user_level": user_level_value,
            "user_score": self.user_score,
            "user_evidence": self.user_evidence,
            "user_reflection": self.user_reflection,
            "system_level": system_level_value,
            "system_score": self.system_score,
            "system_evidence": list(self.system_evidence),
            "perception_gap": self.perception_gap,
            "gap_direction": self.gap_direction,
            "insights": list(self.insights),
            "recommendations": list(self.recommendations),
            # Convenience fields
            "has_perception_gap": self.has_perception_gap(),
            "is_self_aware": self.is_self_aware(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], level_class: type[L]) -> "DualTrackResult[L]":
        """
        Create from dictionary.

        Args:
            data: Dictionary with DualTrackResult fields
            level_class: The enum class for level conversion

        Returns:
            DualTrackResult instance
        """
        # Convert level values to enum if they're strings
        user_level = data["user_level"]
        system_level = data["system_level"]

        if isinstance(user_level, str):
            user_level = level_class(user_level)
        if isinstance(system_level, str):
            system_level = level_class(system_level)

        return cls(
            entity_uid=data["entity_uid"],
            entity_type=data["entity_type"],
            user_level=user_level,
            user_score=data["user_score"],
            user_evidence=data["user_evidence"],
            user_reflection=data.get("user_reflection"),
            system_level=system_level,
            system_score=data["system_score"],
            system_evidence=tuple(data.get("system_evidence", [])),
            perception_gap=data["perception_gap"],
            gap_direction=data["gap_direction"],
            insights=tuple(data.get("insights", [])),
            recommendations=tuple(data.get("recommendations", [])),
        )
