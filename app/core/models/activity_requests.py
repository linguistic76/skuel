"""
Choice & Principle Request Models
==================================

Pydantic models for the Choice and Principle Activity Domains.

Includes nested request models and domain-specific auxiliary requests.

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from core.models.enums import (
    Domain,
    Priority,
)
from core.models.enums.choice_enums import ChoiceType
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


class ChoiceOptionRequest(BaseModel):
    """Request model for creating an option within a Choice entity."""

    title: str = Field(min_length=1, max_length=200, description="Option title")
    description: str = Field(default="", max_length=1000, description="Option description")
    feasibility_score: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_level: float = Field(default=0.5, ge=0.0, le=1.0)
    potential_impact: float = Field(default=0.5, ge=0.0, le=1.0)
    resource_requirement: float = Field(default=0.5, ge=0.0, le=1.0)
    estimated_duration: int | None = Field(None, ge=1, description="Duration in minutes")
    dependencies: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class PrincipleExpressionRequest(BaseModel):
    """Request model for creating an expression within a Principle entity."""

    context: str = Field(min_length=1, max_length=500, description="Life situation")
    behavior: str = Field(min_length=1, max_length=500, description="Expected behavior")
    example: str | None = Field(None, max_length=500, description="Concrete example")


# =============================================================================
# CREATE REQUESTS — Choice & Principle Domains
# =============================================================================


class ChoiceCreateRequest(CreateRequestBase):
    """Create a Choice entity (knowledge about decisions you make)."""

    title: str = Field(min_length=1, max_length=200, description="Choice title")
    description: str = Field(min_length=1, max_length=1000, description="Choice description")

    # Decision characteristics
    choice_type: ChoiceType = Field(default=ChoiceType.MULTIPLE, description="Choice type")
    domain: Domain = Field(default=Domain.PERSONAL, description="Domain")
    decision_deadline: datetime | None = Field(None, description="Decision deadline")
    decision_criteria: list[str] = Field(default_factory=list, description="Criteria for deciding")
    constraints: list[str] = Field(default_factory=list, description="Constraints")
    stakeholders: list[str] = Field(default_factory=list, description="Stakeholders")

    # Options
    options: list[ChoiceOptionRequest] = Field(
        default_factory=list, description="Available options"
    )

    # Organization
    priority: Priority = Field(default=Priority.MEDIUM, description="Choice priority")
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Cross-domain relationships
    informed_by_knowledge_uids: list[str] = Field(
        default_factory=list, description="KU UIDs informing this choice"
    )


class ChoiceEvaluationRequest(BaseModel):
    """Request model for evaluating choice outcomes."""

    satisfaction_score: int = Field(..., ge=1, le=5, description="Satisfaction score (1-5)")
    actual_outcome: str = Field(
        ..., min_length=1, max_length=1000, description="Actual outcome description"
    )
    lessons_learned: list[str] = Field(default_factory=list, description="Lessons learned")


class ChoiceDecisionRequest(BaseModel):
    """Request model for making a decision on a choice."""

    selected_option_uid: str = Field(..., description="UID of selected option")
    decision_rationale: str | None = Field(
        None, max_length=1000, description="Rationale for decision"
    )
    decided_at: datetime | None = Field(None, description="Decision timestamp")


class ChoiceOptionCreateRequest(BaseModel):
    """Request model for creating a choice option (standalone API endpoint)."""

    title: str = Field(..., min_length=1, max_length=200, description="Option title")
    description: str = Field(..., min_length=1, max_length=1000, description="Option description")
    feasibility_score: float = Field(0.5, ge=0.0, le=1.0, description="Feasibility score (0-1)")
    risk_level: float = Field(0.5, ge=0.0, le=1.0, description="Risk level (0-1)")
    potential_impact: float = Field(0.5, ge=0.0, le=1.0, description="Potential impact (0-1)")
    resource_requirement: float = Field(
        0.5, ge=0.0, le=1.0, description="Resource requirement (0-1)"
    )
    estimated_duration: int | None = Field(None, ge=1, description="Estimated duration in minutes")
    dependencies: list[str] = Field(default_factory=list, description="Dependency UIDs")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")


class ChoiceOptionUpdateRequest(BaseModel):
    """Request model for updating a choice option."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=1000)
    feasibility_score: float | None = Field(None, ge=0.0, le=1.0)
    risk_level: float | None = Field(None, ge=0.0, le=1.0)
    potential_impact: float | None = Field(None, ge=0.0, le=1.0)
    resource_requirement: float | None = Field(None, ge=0.0, le=1.0)
    estimated_duration: int | None = Field(None, ge=1)
    dependencies: list[str] | None = None
    tags: list[str] | None = None


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
