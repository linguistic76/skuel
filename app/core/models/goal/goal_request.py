"""
Goal Request Models (Tier 1 - External)
========================================

Pydantic models for external API requests.
Handles validation and serialization at system boundaries.

Uses shared validation rules from core.models.validation_rules for DRY compliance.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.models.enums import Domain, Priority
from core.models.validation_rules import (
    validate_date_after,
    validate_future_date,
    validate_required_string,
    validate_timeframe_date_alignment,
)

from ..goal.goal import GoalStatus, GoalTimeframe, GoalType, HabitEssentiality, MeasurementType


class GoalCreateRequest(BaseModel):
    """
    External request for creating a goal.
    Validates input from API/UI layer.
    """

    # Required fields
    title: str = Field(..., min_length=1, max_length=200, description="Goal title")

    # Optional with defaults
    description: str | None = Field(None, max_length=2000)
    vision_statement: str | None = Field(None, max_length=1000, description="Long-term vision")

    # Classification
    goal_type: GoalType = Field(GoalType.OUTCOME)
    domain: Domain = Field(Domain.KNOWLEDGE, description="Knowledge domain")
    timeframe: GoalTimeframe = Field(GoalTimeframe.QUARTERLY)

    # Measurement
    measurement_type: MeasurementType = Field(MeasurementType.PERCENTAGE)
    target_value: float | None = Field(None, ge=0, description="Target value to achieve")
    unit_of_measurement: str | None = Field(None, max_length=50)

    # Timeline
    start_date: date | None = Field(default_factory=date.today)
    target_date: date | None = Field(None, description="Target completion date")

    # Learning Integration
    required_knowledge_uids: list[str] = Field(default_factory=list)
    supporting_habit_uids: list[str] = Field(default_factory=list)
    guiding_principle_uids: list[str] = Field(default_factory=list)

    # Hierarchical Relationships (2026-01-30 - Hierarchical Pattern)
    parent_goal_uid: str | None = Field(
        None, description="Parent goal UID for subgoal decomposition"
    )
    progress_weight: float = Field(
        default=1.0,
        ge=0.0,
        description="Contribution weight to parent goal progress (default: 1.0 = equal weight)",
    )

    # Motivation
    why_important: str | None = Field(None, max_length=1000)
    success_criteria: str | None = Field(None, max_length=1000)
    potential_obstacles: list[str] = Field(default_factory=list, max_length=10)
    strategies: list[str] = Field(default_factory=list, max_length=10)

    # Organization
    priority: Priority = Field(Priority.MEDIUM)
    tags: list[str] = Field(default_factory=list, max_length=20)

    # Shared validators (DRY pattern)
    _validate_title = validate_required_string("title")

    @model_validator(mode="after")
    def validate_target_date(self):
        """Validate target date is in the future and after start date."""
        if self.target_date and self.target_date < date.today():
            raise ValueError("Target date must be in the future")

        # Use shared validator helper for date ordering
        # allow_equal=True: Same-day goals are valid (e.g., daily goals)
        return validate_date_after("target_date", "start_date", allow_equal=True)(self)

    @model_validator(mode="after")
    def validate_target_value(self):
        """Validate target value based on measurement type."""
        if self.measurement_type == MeasurementType.PERCENTAGE:
            if self.target_value and (self.target_value < 0 or self.target_value > 100):
                raise ValueError("Percentage target must be between 0 and 100")
        elif self.measurement_type == MeasurementType.BINARY:
            if self.target_value and self.target_value not in [0, 1]:
                raise ValueError("Binary target must be 0 or 1")
        elif self.measurement_type == MeasurementType.NUMERIC and not self.target_value:
            raise ValueError("Numeric measurement requires a target value")

        return self

    @model_validator(mode="after")
    def validate_timeframe_alignment(self):
        """Validate timeframe aligns with dates if provided."""
        # Use shared validator helper for timeframe alignment
        return validate_timeframe_date_alignment()(self)

    model_config = ConfigDict(
        use_enum_values=False,
        json_schema_extra={
            "example": {
                "title": "Complete Machine Learning Course",
                "description": "Finish Andrew Ng's ML course on Coursera",
                "goal_type": "learning",
                "domain": "tech",
                "timeframe": "quarterly",
                "measurement_type": "percentage",
                "target_value": 100,
                "target_date": "2024-06-30",
                "required_knowledge_uids": ["ku_ml_basics", "ku_python"],
                "supporting_habit_uids": ["habit_daily_study"],
                "why_important": "Essential for career transition to data science",
                "success_criteria": "Complete all assignments with 80%+ scores",
                "priority": "high",
                "tags": ["learning", "career", "data-science"],
            }
        },
    )


class GoalUpdateRequest(BaseModel):
    """
    External request for updating a goal.
    All fields are optional for partial updates.
    """

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    vision_statement: str | None = Field(None, max_length=1000)

    # Classification can be modified
    goal_type: GoalType | None = None
    domain: Domain | None = None
    timeframe: GoalTimeframe | None = None

    # Measurement can be adjusted
    measurement_type: MeasurementType | None = None
    target_value: float | None = Field(None, ge=0)
    unit_of_measurement: str | None = Field(None, max_length=50)

    # Timeline can be extended
    target_date: date | None = None

    # Links can be updated
    required_knowledge_uids: list[str] | None = None
    supporting_habit_uids: list[str] | None = None
    guiding_principle_uids: list[str] | None = None

    # Motivation can be refined
    why_important: str | None = Field(None, max_length=1000)
    success_criteria: str | None = Field(None, max_length=1000)
    potential_obstacles: list[str] | None = Field(None, max_length=10)
    strategies: list[str] | None = Field(None, max_length=10)

    # Status and priority can change
    status: GoalStatus | None = None
    priority: Priority | None = None
    tags: list[str] | None = Field(None, max_length=20)

    model_config = ConfigDict(use_enum_values=False)


class GoalProgressUpdateRequest(BaseModel):
    """
    Request to update goal progress.
    """

    new_value: float = Field(..., description="New progress value")
    notes: str | None = Field(None, max_length=500, description="Progress notes")

    @field_validator("new_value")
    @classmethod
    def validate_progress(cls, v) -> Any:
        """Validate progress is non-negative."""
        if v < 0:
            raise ValueError("Progress value cannot be negative")
        return v

    model_config = ConfigDict(
        json_schema_extra={"example": {"new_value": 75.5, "notes": "Completed 3 more chapters"}}
    )


class MilestoneCreateRequest(BaseModel):
    """
    Request to add a milestone to a goal.
    """

    title: str = Field(..., min_length=1, max_length=200)
    target_date: date = Field(..., description="Target date for milestone")
    description: str | None = Field(None, max_length=500)
    target_value: float | None = Field(None, ge=0)
    required_knowledge_uids: list[str] = Field(default_factory=list)

    # Shared validators (DRY pattern)
    _validate_target_date = validate_future_date("target_date")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Complete first module",
                "target_date": "2024-04-15",
                "description": "Finish all videos and assignments in Module 1",
                "target_value": 25.0,
            }
        }
    )


class MilestoneCompleteRequest(BaseModel):
    """
    Request to mark a milestone as complete.
    """

    milestone_uid: str = Field(..., description="Milestone UID to complete")
    achieved_date: date | None = Field(default_factory=date.today)
    notes: str | None = Field(None, max_length=500)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "milestone_uid": "milestone_abc123",
                "notes": "Scored 95% on module assessment",
            }
        }
    )


class GoalFilterRequest(BaseModel):
    """
    Request for filtering goals.
    """

    # Classification filters
    goal_type: GoalType | None = None
    domain: Domain | None = None
    timeframe: GoalTimeframe | None = None
    status: GoalStatus | None = None
    priority: Priority | None = None

    # Learning filters
    is_learning_goal: bool | None = None
    has_knowledge_requirements: bool | None = None
    has_supporting_habits: bool | None = None
    is_principle_driven: bool | None = None

    # Hierarchy filters
    is_parent: bool | None = None
    is_sub_goal: bool | None = None
    parent_goal_uid: str | None = None

    # Progress filters
    min_progress: float | None = Field(None, ge=0, le=100)
    max_progress: float | None = Field(None, ge=0, le=100)
    is_overdue: bool | None = None

    # Date filters
    target_date_before: date | None = None
    target_date_after: date | None = None

    # Tag filter
    tags: list[str] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "domain": "tech",
                "status": "active",
                "is_learning_goal": True,
                "min_progress": 25.0,
            }
        }
    )


class GoalAnalyticsRequest(BaseModel):
    """
    Request for goal analytics.
    """

    include_progress_history: bool = Field(True)
    include_milestone_analysis: bool = Field(True)
    include_habit_correlation: bool = Field(False)
    include_predictions: bool = Field(False)
    days_back: int = Field(30, ge=1, le=365)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "include_progress_history": True,
                "include_milestone_analysis": True,
                "include_habit_correlation": True,
                "days_back": 90,
            }
        }
    )


# ==========================================================================
# ATOMIC HABITS REQUEST MODELS
# ==========================================================================


class HabitSystemUpdateRequest(BaseModel):
    """
    Request to update a goal's habit system.
    Implements James Clear's Atomic Habits philosophy.
    """

    essential_habit_uids: list[str] | None = Field(
        None, description="Habits that are ESSENTIAL - goal is impossible without these"
    )
    critical_habit_uids: list[str] | None = Field(
        None, description="Habits that are CRITICAL - goal is very difficult without these"
    )
    supporting_habit_uids: list[str] | None = Field(
        None, description="Habits that are SUPPORTING - goal is easier with these"
    )
    optional_habit_uids: list[str] | None = Field(
        None, description="Habits that are OPTIONAL - tangentially helpful"
    )

    @model_validator(mode="after")
    def validate_no_duplicates(self):
        """Ensure no habit appears in multiple essentiality levels."""
        # Collect all habit UIDs from each essentiality level
        habit_fields = {
            "essential": self.essential_habit_uids or [],
            "critical": self.critical_habit_uids or [],
            "supporting": self.supporting_habit_uids or [],
            "optional": self.optional_habit_uids or [],
        }

        # Check for duplicates across levels
        all_habits = []
        for habits in habit_fields.values():
            all_habits.extend(habits)

        # Find duplicates
        seen = set()
        duplicates = set()
        for habit in all_habits:
            if habit in seen:
                duplicates.add(habit)
            seen.add(habit)

        if duplicates:
            raise ValueError(f"Habits cannot appear in multiple essentiality levels: {duplicates}")

        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "essential_habit_uids": ["habit:daily-practice"],
                "critical_habit_uids": ["habit:weekly-review"],
                "supporting_habit_uids": ["habit:morning-routine", "habit:evening-reflection"],
                "optional_habit_uids": ["habit:monthly-assessment"],
            }
        }
    )


class IdentityBasedGoalRequest(BaseModel):
    """
    Request to configure a goal with identity-based motivation.
    James Clear: Focus on who you become, not what you achieve.
    """

    target_identity: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Target identity (e.g., 'I am a writer', 'I am a runner')",
    )
    identity_evidence_required: int = Field(
        50,
        ge=1,
        le=200,
        description="Number of habit completions required to establish identity (default 50 based on research)",
    )

    @field_validator("target_identity")
    @classmethod
    def validate_identity_format(cls, v) -> Any:
        """Ensure identity statement is in 'I am X' format."""
        v = v.strip()
        if not v.lower().startswith("i am "):
            raise ValueError("Identity statement should start with 'I am' (e.g., 'I am a writer')")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "target_identity": "I am a consistent learner",
                "identity_evidence_required": 50,
            }
        }
    )


class SystemHealthCheckRequest(BaseModel):
    """
    Request to diagnose goal's habit system health.
    Returns actionable insights about system strength and weaknesses.
    """

    include_habit_success_rates: bool = Field(
        True, description="Include success rate analysis for each habit"
    )
    include_recommendations: bool = Field(
        True, description="Include actionable recommendations for system improvement"
    )
    include_velocity_metrics: bool = Field(True, description="Include habit velocity calculations")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "include_habit_success_rates": True,
                "include_recommendations": True,
                "include_velocity_metrics": True,
            }
        }
    )


class HabitEssentialityChangeRequest(BaseModel):
    """
    Request to change a habit's essentiality level for a goal.
    """

    habit_uid: str = Field(..., description="UID of habit to reclassify")
    new_essentiality: HabitEssentiality = Field(..., description="New essentiality level")
    reason: str | None = Field(None, max_length=500, description="Optional reason for the change")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "habit_uid": "habit:daily-practice",
                "new_essentiality": "essential",
                "reason": "Realized this habit is absolutely critical for goal achievement",
            }
        }
    )


class ContextualGoalTaskGenerationRequest(BaseModel):
    """
    Request model for generating tasks from a goal with context awareness.

    Used by: POST /api/context/goal/tasks

    Fields:
        context_preferences: Preferences for task generation (e.g., time_available, difficulty)
        auto_create: Whether to create tasks immediately (True) or return templates (False)
    """

    context_preferences: dict[str, Any] = Field(
        default_factory=dict,
        description="Preferences for task generation (time_available, difficulty_preference, etc.)",
    )
    auto_create: bool = Field(
        default=True,
        description="If True, create tasks immediately; if False, return task templates",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "context_preferences": {
                    "time_available_minutes": 180,
                    "difficulty_preference": "moderate",
                    "focus_area": "learning",
                },
                "auto_create": True,
            }
        }
    )
