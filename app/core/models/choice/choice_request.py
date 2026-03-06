"""
Choice Request Models
======================

Pydantic models for the Choice Activity Domain API boundaries.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from datetime import datetime

from pydantic import BaseModel, Field

from core.models.enums import Domain, Priority
from core.models.enums.choice_enums import ChoiceType
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


# =============================================================================
# CREATE / UPDATE REQUESTS
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
