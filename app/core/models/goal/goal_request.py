"""
Goal Request Models (Tier 1 - External)
========================================

Pydantic models for external API requests.
Handles validation and serialization at system boundaries.

Uses shared validation rules from core.models.validation_rules for DRY compliance.
"""

from datetime import date
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from core.models.enums import Domain, EntityStatus, Priority
from core.models.enums.goal_enums import (
    GoalTimeframe,
    GoalType,
    HabitEssentiality,
    MeasurementType,
)
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.models.sentinels import UNSET, Unset
from core.models.validation_rules import (
    validate_date_after,
    validate_future_date,
    validate_required_string,
    validate_timeframe_date_alignment,
)
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone, today_in_current_zone


class GoalCreateRequest(BaseModel):
    """
    External request for creating a goal.
    Validates input from API/UI layer.
    """

    # Required fields
    title: str = Field(..., min_length=1, max_length=200, description="Goal title")

    # Optional with defaults
    description: str | None = Field(default=None, max_length=2000)
    vision_statement: str | None = Field(
        default=None, max_length=1000, description="Long-term vision"
    )

    # Classification
    goal_type: GoalType = Field(GoalType.OUTCOME)
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")
    timeframe: GoalTimeframe = Field(GoalTimeframe.QUARTERLY)

    # Measurement
    measurement_type: MeasurementType = Field(MeasurementType.PERCENTAGE)
    target_value: float | None = Field(default=None, ge=0, description="Target value to achieve")
    unit_of_measurement: str | None = Field(default=None, max_length=50)

    # Timeline
    start_date: date | None = Field(default_factory=today_in_current_zone)
    target_date: date | None = Field(default=None, description="Target completion date")

    # Learning Integration
    required_knowledge_uids: list[str] = Field(default_factory=list)
    supporting_habit_uids: list[str] = Field(default_factory=list)
    supporting_principle_uids: list[str] = Field(default_factory=list)

    # Hierarchical Relationships (2026-01-30 - Hierarchical Pattern)
    parent_goal_uid: str | None = Field(
        default=None, description="Parent goal UID for subgoal decomposition"
    )
    progress_weight: float = Field(
        default=1.0,
        ge=0.0,
        description="Contribution weight to parent goal progress (default: 1.0 = equal weight)",
    )

    # Motivation
    why_important: str | None = Field(default=None, max_length=1000)
    success_criteria: str | None = Field(default=None, max_length=1000)
    potential_obstacles: list[str] = Field(default_factory=list, max_length=10)
    strategies: list[str] = Field(default_factory=list, max_length=10)

    # Organization
    priority: Priority = Field(Priority.MEDIUM)
    tags: list[str] = Field(default_factory=list, max_length=20)

    # Shared validators (DRY pattern)
    _validate_title = validate_required_string("title")

    @model_validator(mode="after")
    def validate_target_date(self, info: ValidationInfo) -> GoalCreateRequest:
        """Validate target date is in the future and after start date.

        The future check honors the ingestion validation context
        (``allow_past_dates`` — historical vault notes legitimately carry
        past target dates; see validate_future_date, G10/Arc E).
        """
        allow_past = bool(info.context and info.context.get("allow_past_dates"))
        if not allow_past and self.target_date and self.target_date < today_in(current_zone()):
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

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    vision_statement: str | None = Field(default=None, max_length=1000)

    # Classification can be modified
    goal_type: GoalType | None = None
    domain: Domain | None = None
    timeframe: GoalTimeframe | None = None

    # Measurement can be adjusted
    measurement_type: MeasurementType | None = None
    target_value: float | None = Field(default=None, ge=0)
    unit_of_measurement: str | None = Field(default=None, max_length=50)

    # Timeline can be extended
    target_date: date | None = None

    # Links can be updated
    required_knowledge_uids: list[str] | None = None
    supporting_habit_uids: list[str] | None = None
    supporting_principle_uids: list[str] | None = None

    # Motivation can be refined
    why_important: str | None = Field(default=None, max_length=1000)
    success_criteria: str | None = Field(default=None, max_length=1000)
    potential_obstacles: list[str] | None = Field(default=None, max_length=10)
    strategies: list[str] | None = Field(default=None, max_length=10)

    # Status and priority can change
    status: EntityStatus | None = None
    priority: Priority | None = None
    tags: list[str] | None = Field(default=None, max_length=20)

    model_config = ConfigDict(use_enum_values=False)

    def to_intent(self) -> GoalUpdateIntent:
        """Build the typed ``GoalUpdateIntent`` (ADR-066) from explicitly-set fields.

        Only fields the caller actually provided (``model_fields_set``) become non-``UNSET``,
        so the intent carries a true partial patch: an absent field is left untouched, a
        field explicitly set to ``None`` is an explicit clear. Enum fields (goal_type,
        domain, timeframe, measurement_type, status, priority) are lowered to their string
        value to match the persistence boundary.

        The three cross-domain UID fields (``required_knowledge_uids`` /
        ``supporting_habit_uids`` / ``supporting_principle_uids``) are graph edges, not node
        columns, so they are intentionally not carried — writing them as properties would
        leak junk denormalized fields onto the node (the edges are synced on the
        create-with-context path, not this property-update path).
        """
        set_fields = self.model_fields_set

        def when_set[T](name: str, value: T) -> T | Unset:
            """Carry ``value`` only if the caller set this field; else ``UNSET``.

            Generic so the intent fields stay fully typed (no ``Any``): the return is
            ``<declared field type> | Unset``, exactly what each intent field expects.
            """
            return value if name in set_fields else UNSET

        return GoalUpdateIntent(
            title=when_set("title", self.title),
            description=when_set("description", self.description),
            vision_statement=when_set("vision_statement", self.vision_statement),
            goal_type=when_set(
                "goal_type", self.goal_type.value if self.goal_type is not None else None
            ),
            domain=when_set("domain", self.domain.value if self.domain is not None else None),
            timeframe=when_set(
                "timeframe", self.timeframe.value if self.timeframe is not None else None
            ),
            measurement_type=when_set(
                "measurement_type",
                self.measurement_type.value if self.measurement_type is not None else None,
            ),
            target_value=when_set("target_value", self.target_value),
            unit_of_measurement=when_set("unit_of_measurement", self.unit_of_measurement),
            target_date=when_set("target_date", self.target_date),
            why_important=when_set("why_important", self.why_important),
            success_criteria=when_set("success_criteria", self.success_criteria),
            potential_obstacles=when_set("potential_obstacles", self.potential_obstacles),
            strategies=when_set("strategies", self.strategies),
            status=when_set("status", self.status.value if self.status is not None else None),
            priority=when_set(
                "priority", self.priority.value if self.priority is not None else None
            ),
            tags=when_set("tags", self.tags),
        )


#: The longest progress note the form takes: a remark beside a figure, a few
#: sentences, the same bound as a milestone's description. Every note stays on the
#: goal's history, one JSON property appended to for the goal's life, so it is bounded.
PROGRESS_NOTE_MAX_LENGTH = 500


class GoalProgressUpdateRequest(BaseModel):
    """
    The figure a learner enters for a goal (``POST /api/goals/{uid}/progress``).

    What ``progress`` means is the goal's measurement type's to say: a value in the
    goal's own unit on a numeric goal, the percentage (0-100) otherwise. The service
    holds that rule, and refuses a goal whose figure is derived.
    """

    new_value: float = Field(
        ..., ge=0, allow_inf_nan=False, validation_alias="progress", description="The figure"
    )
    update_date: str | None = Field(
        default=None,
        max_length=40,
        validation_alias="date",
        description="When the progress happened (ISO date or datetime), when it is not now",
    )
    note: str = Field(
        default="",
        max_length=PROGRESS_NOTE_MAX_LENGTH,
        description="The learner's note on this entry; blank is no note",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"progress": 75.5, "note": "Finished chapter three"}},
    )

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, v: object) -> object:
        """A note is held without its surrounding space; one of spaces alone is none.
        Stripped before the length check, so padding never counts against it."""
        if v is None:
            return ""
        return v.strip() if isinstance(v, str) else v


class MilestoneCreateRequest(BaseModel):
    """
    One milestone added to a goal (``POST /api/goals/{uid}/milestones``).
    """

    title: str = Field(..., min_length=1, max_length=200)
    target_date: date | None = Field(default=None, description="Target date for milestone")
    description: str | None = Field(default=None, max_length=500)

    # Shared validators (DRY pattern)
    _validate_target_date = validate_future_date("target_date")

    @field_validator("title")
    @classmethod
    def title_has_text(cls, v: str) -> str:
        """A title of spaces alone names nothing."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("A milestone needs a title")
        return stripped

    @field_validator("target_date", mode="before")
    @classmethod
    def blank_date_is_none(cls, v: object) -> object:
        """An HTML form sends an unset date as an empty string."""
        return None if isinstance(v, str) and not v.strip() else v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Complete first module",
                "target_date": "2027-04-15",
                "description": "Finish all videos and assignments in Module 1",
            }
        }
    )


class MilestoneUidRequest(BaseModel):
    """
    The milestone of a goal a door acts on: marked reached
    (``POST /api/goals/{uid}/milestones/complete``) or reopened
    (``POST /api/goals/{uid}/milestones/reopen``).
    """

    milestone_uid: str = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(
        json_schema_extra={"example": {"milestone_uid": "milestone_3f9a0c41d2e87b65"}}
    )


class GoalFilterRequest(BaseModel):
    """
    Request for filtering goals.
    """

    # Classification filters
    goal_type: GoalType | None = None
    domain: Domain | None = None
    timeframe: GoalTimeframe | None = None
    status: EntityStatus | None = None
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
    min_progress: float | None = Field(default=None, ge=0, le=100)
    max_progress: float | None = Field(default=None, ge=0, le=100)
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


# ==========================================================================
# ATOMIC HABITS REQUEST MODELS
# ==========================================================================


class HabitSystemUpdateRequest(BaseModel):
    """
    A goal's whole habit system, replaced (``POST /api/goals/{uid}/habits/system``).

    The four lists together are every habit the goal keeps, each at the tier its list
    names; a habit the goal has and no list names is unlinked, and a tier left out is
    empty, so an empty body unlinks every habit. Every habit must be one of the goal
    owner's own. A habit named in two tiers is refused (400).
    """

    essential_habit_uids: list[str] = Field(
        default_factory=list, description="Habits the goal is impossible without"
    )
    critical_habit_uids: list[str] = Field(
        default_factory=list, description="Habits the goal is very difficult without"
    )
    supporting_habit_uids: list[str] = Field(
        default_factory=list, description="Habits that make the goal easier"
    )
    optional_habit_uids: list[str] = Field(
        default_factory=list, description="Habits that help the goal a little"
    )

    @model_validator(mode="after")
    def validate_no_duplicates(self) -> HabitSystemUpdateRequest:
        """Refuse a habit named in more than one tier."""
        seen: set[str] = set()
        duplicates: set[str] = set()
        for habit_uid in self._named():
            if habit_uid in seen:
                duplicates.add(habit_uid)
            seen.add(habit_uid)
        if duplicates:
            raise ValueError(
                f"Habits cannot appear in multiple essentiality levels: {sorted(duplicates)}"
            )
        return self

    def _named(self) -> list[str]:
        return [
            *self.essential_habit_uids,
            *self.critical_habit_uids,
            *self.supporting_habit_uids,
            *self.optional_habit_uids,
        ]

    def tiers(self) -> dict[str, HabitEssentiality]:
        """Each habit the system keeps, at its tier."""
        return {
            **dict.fromkeys(self.essential_habit_uids, HabitEssentiality.ESSENTIAL),
            **dict.fromkeys(self.critical_habit_uids, HabitEssentiality.CRITICAL),
            **dict.fromkeys(self.supporting_habit_uids, HabitEssentiality.SUPPORTING),
            **dict.fromkeys(self.optional_habit_uids, HabitEssentiality.OPTIONAL),
        }

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "essential_habit_uids": ["habit_9c4e2b7a1d6f0835"],
                "critical_habit_uids": ["habit_2a7f5c0e8d4b1963"],
                "supporting_habit_uids": ["habit_c3e81f4a6b2d9075", "habit_7b0d3e9c5a1f8264"],
                "optional_habit_uids": ["habit_e4a9c62f0b7d1358"],
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
        default=50,
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
        default=True, description="Include success rate analysis for each habit"
    )
    include_recommendations: bool = Field(
        default=True, description="Include actionable recommendations for system improvement"
    )
    include_velocity_metrics: bool = Field(
        default=True, description="Include habit velocity calculations"
    )

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
    Move a habit already linked to a goal to another tier
    (``POST /api/goals/{uid}/habits/essentiality``).
    """

    habit_uid: str = Field(..., min_length=1, max_length=100, description="The linked habit")
    new_essentiality: HabitEssentiality = Field(..., description="The tier it moves to")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"habit_uid": "habit_9c4e2b7a1d6f0835", "new_essentiality": "essential"}
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


class GoalHabitLinkRequest(BaseModel):
    """
    Link one of the caller's habits to their goal, at a tier
    (``POST /api/goals/{uid}/habits``). A habit already linked takes the tier given.
    """

    habit_uid: str = Field(..., min_length=1, max_length=100, description="The habit to link")
    essentiality: HabitEssentiality = Field(
        default=HabitEssentiality.SUPPORTING, description="The tier it is linked at"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"habit_uid": "habit_9c4e2b7a1d6f0835", "essentiality": "critical"}
        }
    )


class GoalHabitUidRequest(BaseModel):
    """The habit a goal door unlinks (``POST /api/goals/{uid}/habits/unlink``)."""

    habit_uid: str = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(
        json_schema_extra={"example": {"habit_uid": "habit_9c4e2b7a1d6f0835"}}
    )
