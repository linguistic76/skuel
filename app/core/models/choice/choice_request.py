"""
Choice Request Models (Tier 1 - External)
==========================================

Pydantic models for API validation and external interfaces.
Handles input validation and serialization for choice domain.

Uses shared validators from validation_rules.py for DRY compliance.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from core.models.choice.choice import ChoiceStatus, ChoiceType
from core.models.shared_enums import Domain, Priority
from core.models.validation_rules import (
    validate_future_date,
    validate_list_max_length,
    validate_past_date,
    validate_weights_sum_to_one,
)


def _default_user_preferences() -> Any:
    """Default user preferences for option ranking."""
    return {
        "feasibility_weight": 0.3,
        "impact_weight": 0.4,
        "risk_weight": 0.2,
        "resource_weight": 0.1,
    }


class ChoiceOptionCreateRequest(BaseModel):
    """Request model for creating choice options."""

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

    # Shared validators
    _validate_tags = validate_list_max_length("tags", max_length=10)


class ChoiceOptionUpdateRequest(BaseModel):
    """Request model for updating choice options."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=1000)
    feasibility_score: float | None = Field(None, ge=0.0, le=1.0)
    risk_level: float | None = Field(None, ge=0.0, le=1.0)
    potential_impact: float | None = Field(None, ge=0.0, le=1.0)
    resource_requirement: float | None = Field(None, ge=0.0, le=1.0)
    estimated_duration: int | None = Field(None, ge=1)
    dependencies: list[str] | None = None
    tags: list[str] | None = None

    # Shared validators
    _validate_tags = validate_list_max_length("tags", max_length=10)


class ChoiceCreateRequest(BaseModel):
    """Request model for creating choices."""

    title: str = Field(..., min_length=1, max_length=200, description="Choice title")
    description: str = Field(..., min_length=1, max_length=1000, description="Choice description")
    choice_type: ChoiceType = Field(ChoiceType.MULTIPLE, description="Type of choice")
    priority: Priority = Field(Priority.MEDIUM, description="Choice priority")
    domain: Domain = Field(Domain.PERSONAL, description="Life domain")

    decision_deadline: datetime | None = Field(None, description="Decision deadline")
    decision_criteria: list[str] = Field(default_factory=list, description="Decision criteria")
    constraints: list[str] = Field(default_factory=list, description="Constraints to consider")
    stakeholders: list[str] = Field(default_factory=list, description="Affected stakeholders")
    informed_by_knowledge_uids: list[str] = Field(
        default_factory=list, description="Knowledge units that inform this choice"
    )

    options: list[ChoiceOptionCreateRequest] = Field(
        default_factory=list, description="Initial options"
    )

    # Shared validators
    _validate_deadline = validate_future_date("decision_deadline")
    _validate_criteria = validate_list_max_length("decision_criteria", max_length=20)
    _validate_options = validate_list_max_length("options", max_length=50)


class ChoiceUpdateRequest(BaseModel):
    """Request model for updating choices."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=1000)
    choice_type: ChoiceType | None = None
    priority: Priority | None = None
    domain: Domain | None = None
    status: ChoiceStatus | None = None

    decision_deadline: datetime | None = None
    decision_criteria: list[str] | None = None
    constraints: list[str] | None = None
    stakeholders: list[str] | None = None

    # Shared validators
    _validate_deadline = validate_future_date("decision_deadline")
    _validate_criteria = validate_list_max_length("decision_criteria", max_length=20)


class ChoiceDecisionRequest(BaseModel):
    """Request model for making a decision."""

    selected_option_uid: str = Field(..., description="UID of selected option")
    decision_rationale: str | None = Field(
        None, max_length=1000, description="Rationale for decision"
    )
    decided_at: datetime | None = Field(None, description="Decision timestamp")

    # Shared validators
    _validate_decided_at = validate_past_date("decided_at")


class ChoiceEvaluationRequest(BaseModel):
    """Request model for evaluating choice outcomes."""

    satisfaction_score: int = Field(..., ge=1, le=5, description="Satisfaction score (1-5)")
    actual_outcome: str = Field(
        ..., min_length=1, max_length=1000, description="Actual outcome description"
    )
    lessons_learned: list[str] = Field(default_factory=list, description="Lessons learned")

    # Shared validators
    _validate_lessons = validate_list_max_length("lessons_learned", max_length=10)


class ChoiceFilterRequest(BaseModel):
    """Request model for filtering choices."""

    status: ChoiceStatus | None = None
    priority: Priority | None = None
    domain: Domain | None = None
    choice_type: ChoiceType | None = None
    is_overdue: bool | None = None
    has_deadline: bool | None = None

    limit: int = Field(50, ge=1, le=200, description="Maximum results")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class ChoiceAnalyticsRequest(BaseModel):
    """Request model for choice analytics."""

    start_date: datetime | None = None
    end_date: datetime | None = None
    include_patterns: bool = Field(True, description="Include decision patterns analysis")
    include_complexity: bool = Field(True, description="Include complexity distribution")

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v, info: ValidationInfo) -> Any:
        if (
            v is not None
            and info.data.get("start_date") is not None
            and v <= info.data["start_date"]
        ):
            raise ValueError("End date must be after start date")
        return v


class ChoiceOptionRankingRequest(BaseModel):
    """Request model for ranking choice options."""

    user_preferences: dict[str, float] = Field(
        default_factory=_default_user_preferences,
        description="User preference weights for option scoring",
    )

    # Shared validators
    _validate_preferences = validate_weights_sum_to_one(
        "user_preferences",
        required_keys={"feasibility_weight", "impact_weight", "risk_weight", "resource_weight"},
    )


class ChoiceInsightsRequest(BaseModel):
    """Request model for choice insights generation."""

    include_decision_patterns: bool = Field(True, description="Include decision pattern analysis")
    include_outcome_correlation: bool = Field(
        True, description="Include outcome correlation analysis"
    )
    include_improvement_suggestions: bool = Field(
        True, description="Include improvement suggestions"
    )
    time_period_days: int = Field(90, ge=7, le=365, description="Analysis time period in days")


# Response Models
class ChoiceResponse(BaseModel):
    """Response model for choice data."""

    uid: str
    title: str
    description: str
    user_uid: str
    choice_type: str
    status: str
    priority: str
    domain: str

    selected_option_uid: str | None = None
    decision_rationale: str | None = None

    decision_criteria: list[str]
    constraints: list[str]
    stakeholders: list[str]
    decision_deadline: datetime | None = None
    created_at: datetime
    decided_at: datetime | None = None
    satisfaction_score: int | None = None
    actual_outcome: str | None = None
    lessons_learned: list[str]

    # Computed fields
    complexity_score: float | None = None
    time_until_deadline_minutes: int | None = None
    is_overdue: bool = False

    model_config = ConfigDict(
        # Pydantic V2 serializes datetimes automatically
    )


class ChoiceOptionResponse(BaseModel):
    """Response model for choice options."""

    uid: str
    title: str
    description: str
    feasibility_score: float
    risk_level: float
    potential_impact: float
    resource_requirement: float
    estimated_duration: int | None = None
    dependencies: list[str]
    tags: list[str]


class ChoiceAnalyticsResponse(BaseModel):
    """Response model for choice analytics."""

    user_uid: str
    total_choices: int
    pending_choices: int
    decided_choices: int
    overdue_choices: int
    average_satisfaction: float | None = None
    average_decision_time_days: float | None = None
    most_common_priority: str | None = None
    decision_patterns: dict[str, Any]
    complexity_distribution: dict[str, int]
