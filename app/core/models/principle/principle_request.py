"""
Principle Request Models (Tier 1 - External)
=============================================

Pydantic models for external API requests.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.models.shared_enums import Priority

from ..principle.principle import (
    AlignmentAssessment,
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)


class PrincipleCreateRequest(BaseModel):
    """External request for creating a principle."""

    # Required fields
    name: str = Field(..., min_length=1, max_length=100, description="Principle name")
    statement: str = Field(..., min_length=1, max_length=500, description="Full statement")

    # Optional fields
    description: str | None = Field(
        None, max_length=1000, description="Detailed explanation of the principle"
    )
    category: PrincipleCategory = Field(
        PrincipleCategory.PERSONAL,
        description="Category: personal, social, professional, ethical, or philosophical",
    )
    source: PrincipleSource = Field(
        PrincipleSource.PERSONAL,
        description="Origin: philosophical, religious, cultural, personal, scientific, mentor, or literature",
    )
    strength: PrincipleStrength = Field(
        PrincipleStrength.MODERATE, description="How foundational: core, supporting, or contextual"
    )

    # Context
    tradition: str | None = Field(None, max_length=100)
    original_source: str | None = Field(None, max_length=200)
    personal_interpretation: str | None = Field(None, max_length=1000)

    # Personal meaning
    why_important: str | None = Field(None, max_length=1000)
    origin_story: str | None = Field(None, max_length=2000)

    # Behaviors
    key_behaviors: list[str] = Field(default_factory=list, max_length=10)
    decision_criteria: list[str] = Field(default_factory=list, max_length=10)

    # Organization
    priority: Priority = Field(Priority.MEDIUM)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("name", "statement")
    @classmethod
    def validate_not_empty(cls, v) -> Any:
        if not v or v.strip() == "":
            raise ValueError("Field cannot be empty")
        return v.strip()

    model_config = ConfigDict(
        use_enum_values=False,
        json_schema_extra={
            "example": {
                "name": "Continuous Learning",
                "statement": "I commit to learning something new every day",
                "category": "intellectual",
                "strength": "core",
                "why_important": "Growth mindset is essential for adaptation",
                "key_behaviors": ["Read daily", "Ask questions", "Seek feedback"],
                "priority": "high",
            }
        },
    )


class PrincipleUpdateRequest(BaseModel):
    """External request for updating a principle."""

    name: str | None = Field(None, min_length=1, max_length=100)
    statement: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = Field(None, max_length=1000)

    category: PrincipleCategory | None = None
    source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None
    tradition: str | None = Field(None, max_length=100)
    original_source: str | None = Field(None, max_length=200)
    personal_interpretation: str | None = Field(None, max_length=1000)

    why_important: str | None = Field(None, max_length=1000)
    evolution_notes: str | None = Field(None, max_length=1000)

    key_behaviors: list[str] | None = Field(None, max_length=10)
    decision_criteria: list[str] | None = Field(None, max_length=10)

    is_active: bool | None = None
    priority: Priority | None = None
    tags: list[str] | None = Field(None, max_length=20)

    model_config = ConfigDict(use_enum_values=False)


class PrincipleExpressionRequest(BaseModel):
    """Request to add an expression to a principle."""

    context: str = Field(..., min_length=1, max_length=100)
    behavior: str = Field(..., min_length=1, max_length=500)
    example: str | None = Field(None, max_length=500)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "context": "Work meetings",
                "behavior": "Listen fully before responding",
                "example": "In design review, heard all feedback before proposing solutions",
            }
        }
    )


class AlignmentAssessmentRequest(BaseModel):
    """Request to assess alignment with a principle."""

    alignment_level: AlignmentLevel = Field(...)
    evidence: str = Field(..., min_length=1, max_length=1000)
    reflection: str | None = Field(None, max_length=1000)
    assessed_date: date | None = Field(default_factory=date.today)

    model_config = ConfigDict(
        use_enum_values=False,
        json_schema_extra={
            "example": {
                "alignment_level": "mostly_aligned",
                "evidence": "Completed daily reading habit 6 out of 7 days",
                "reflection": "Need to protect morning time better on weekends",
            }
        },
    )


class PrincipleLinkRequest(BaseModel):
    """Request to link a principle to goals/habits/knowledge."""

    link_type: str = Field(..., pattern="^(goal|habit|knowledge|principle)$")
    uid: str = Field(..., min_length=1)
    bidirectional: bool = Field(False, description="Create reverse link")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"link_type": "habit", "uid": "habit_daily_reading", "bidirectional": True}
        }
    )


@dataclass(frozen=True)
class PrincipleAlignmentAssessmentResult:
    """
    Dual-track principle alignment result.

    This model captures BOTH user self-assessment AND system-calculated alignment,
    enabling gap analysis between perception and measured reality.

    Follows SKUEL's core insight: "The user's vision is understood via the words
    they use to communicate, the UserContext is determined via user's actions."

    Similar pattern to LifePath's WordActionAlignment.
    """

    principle_uid: str

    # USER-DECLARED (stored in alignment_history)
    user_assessment: AlignmentAssessment  # What user said about their alignment

    # SYSTEM-CALCULATED (computed from goals/habits/choices)
    system_alignment: AlignmentLevel  # What system measured
    system_score: float  # 0.0-1.0 numeric score
    system_evidence: tuple[str, ...]  # Goals/habits/choices expressing principle

    # GAP ANALYSIS
    perception_gap: float  # Absolute difference between user vs system (0.0-1.0)
    gap_direction: str  # "user_higher" | "system_higher" | "aligned"

    # INSIGHTS
    insights: tuple[str, ...]  # Observations about the gap
    recommendations: tuple[str, ...]  # How to close the gap

    def has_perception_gap(self) -> bool:
        """Check if there's a meaningful gap between perception and reality."""
        return self.perception_gap >= 0.15

    def is_self_aware(self) -> bool:
        """Check if user's self-perception matches system measurement."""
        return self.gap_direction == "aligned"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "principle_uid": self.principle_uid,
            "user_assessment": {
                "assessed_date": self.user_assessment.assessed_date.isoformat(),
                "alignment_level": self.user_assessment.alignment_level.value,
                "evidence": self.user_assessment.evidence,
                "reflection": self.user_assessment.reflection,
            },
            "system_alignment": self.system_alignment.value,
            "system_score": self.system_score,
            "system_evidence": list(self.system_evidence),
            "perception_gap": self.perception_gap,
            "gap_direction": self.gap_direction,
            "insights": list(self.insights),
            "recommendations": list(self.recommendations),
            "has_perception_gap": self.has_perception_gap(),
            "is_self_aware": self.is_self_aware(),
        }


class PrincipleFilterRequest(BaseModel):
    """Request for filtering principles."""

    category: PrincipleCategory | None = None
    source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None
    current_alignment: AlignmentLevel | None = None

    is_active: bool | None = None
    is_core: bool | None = None
    supports_learning: bool | None = None
    has_conflicts: bool | None = None

    priority: Priority | None = None
    tags: list[str] | None = None
    needs_review: bool | None = None
    well_aligned: bool | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "category": "intellectual",
                "strength": "core",
                "is_active": True,
                "well_aligned": True,
            }
        }
    )
