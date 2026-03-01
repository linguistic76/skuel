"""
Principle Request Models
=========================

Pydantic models for the Principle Activity Domain API boundaries.

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from core.models.enums import Priority
from core.models.enums.principle_enums import (
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.request_base import CreateRequestBase


# =============================================================================
# NESTED REQUEST MODELS (used by create requests)
# =============================================================================


class PrincipleExpressionRequest(BaseModel):
    """Request model for creating an expression within a Principle entity."""

    context: str = Field(min_length=1, max_length=500, description="Life situation")
    behavior: str = Field(min_length=1, max_length=500, description="Expected behavior")
    example: str | None = Field(None, max_length=500, description="Concrete example")


# =============================================================================
# CREATE / UPDATE / FILTER REQUESTS
# =============================================================================


class PrincipleCreateRequest(CreateRequestBase):
    """Create a Principle entity (knowledge about what you believe)."""

    title: str = Field(min_length=1, max_length=100, description="Principle title")
    statement: str = Field(min_length=1, max_length=500, description="Core statement")
    description: str | None = Field(None, max_length=1000, description="Full description")

    # Classification
    category: PrincipleCategory = Field(default=PrincipleCategory.PERSONAL, description="Category")
    source: PrincipleSource = Field(default=PrincipleSource.PERSONAL, description="Source")
    strength: PrincipleStrength = Field(default=PrincipleStrength.MODERATE, description="Strength")

    # Origin
    tradition: str | None = Field(None, max_length=100, description="Tradition/school of thought")
    original_source: str | None = Field(None, max_length=200, description="Original source text")
    personal_interpretation: str | None = Field(
        None, max_length=1000, description="Personal interpretation"
    )
    why_important: str | None = Field(
        None, max_length=1000, description="Why this principle matters"
    )
    origin_story: str | None = Field(
        None, max_length=2000, description="How you came to this principle"
    )

    # Behavioral expression
    key_behaviors: list[str] = Field(
        default_factory=list, max_length=10, description="Key behaviors"
    )
    decision_criteria: list[str] = Field(
        default_factory=list, max_length=10, description="Decision criteria"
    )
    expressions: list[PrincipleExpressionRequest] = Field(
        default_factory=list, description="Context expressions"
    )

    # Organization
    priority: Priority = Field(default=Priority.MEDIUM, description="Principle priority")
    tags: list[str] = Field(default_factory=list, max_length=20, description="Tags")


class AlignmentAssessmentRequest(BaseModel):
    """Request to assess alignment with a principle."""

    alignment_level: AlignmentLevel = Field(...)
    evidence: str = Field(..., min_length=1, max_length=1000)
    reflection: str | None = Field(None, max_length=1000)
    assessed_date: date | None = Field(default_factory=date.today)


class PrincipleLinkRequest(BaseModel):
    """Request to link a principle to goals/habits/knowledge."""

    link_type: str = Field(..., pattern="^(goal|habit|knowledge|principle)$")
    uid: str = Field(..., min_length=1)
    bidirectional: bool = Field(False, description="Create reverse link")


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


# =============================================================================
# RESULT TYPES
# =============================================================================


@dataclass(frozen=True)
class PrincipleAlignmentAssessmentResult:
    """
    Dual-track principle alignment result.

    Captures BOTH user self-assessment AND system-calculated alignment,
    enabling gap analysis between perception and measured reality.
    """

    principle_uid: str

    # USER-DECLARED (stored in alignment_history)
    user_assessment: Any  # AlignmentAssessment

    # SYSTEM-CALCULATED (computed from goals/habits/choices)
    system_alignment: AlignmentLevel
    system_score: float  # 0.0-1.0 numeric score
    system_evidence: tuple[str, ...]

    # GAP ANALYSIS
    perception_gap: float  # Absolute difference between user vs system (0.0-1.0)
    gap_direction: str  # "user_higher" | "system_higher" | "aligned"

    # INSIGHTS
    insights: tuple[str, ...]
    recommendations: tuple[str, ...]

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
