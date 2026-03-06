"""
Entity-Wide Request Models (Cross-Domain)
==========================================

Pydantic models shared across all entity types:
- EntityUpdateRequest (unified update for any EntityType)
- EntityResponse / EntityListResponse (API responses)
- Bulk operations (tags, categorize, delete)
- Schedule management (progress report generation)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, Field

from core.models.enums import (
    Domain,
    KuComplexity,
    LearningLevel,
    Priority,
    RecurrencePattern,
    SELCategory,
)
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.curriculum_enums import LpType, StepDifficulty
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty, HabitPolarity
from core.models.enums.metadata_enums import Visibility
from core.models.enums.principle_enums import PrincipleCategory, PrincipleSource, PrincipleStrength
from core.models.request_base import (
    ListResponseBase,
    ResponseBase,
    UpdateRequestBase,
)

# =============================================================================
# UPDATE REQUEST (shared across all EntityTypes)
# =============================================================================


class EntityUpdateRequest(UpdateRequestBase):
    """Update any entity type. All fields optional.

    Services validate which fields are appropriate per EntityType.
    """

    # --- COMMON ---
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    content: str | None = None
    summary: str | None = Field(None, max_length=500)
    domain: Domain | None = None
    tags: list[str] | None = None
    priority: Priority | None = None

    # --- PROCESSING ---
    status: EntityStatus | None = None
    processor_type: ProcessorType | None = None
    instructions: str | None = None
    processing_error: str | None = None
    processed_content: str | None = None

    # --- FEEDBACK ---
    feedback: str | None = None
    subject_uid: str | None = None

    # --- LEARNING METADATA ---
    complexity: KuComplexity | None = None
    learning_level: LearningLevel | None = None
    sel_category: SELCategory | None = None
    quality_score: float | None = Field(None, ge=0.0, le=1.0)
    estimated_time_minutes: int | None = Field(None, ge=1)
    difficulty_rating: float | None = Field(None, ge=0.0, le=1.0)

    # --- SHARING ---
    visibility: Visibility | None = None

    # --- SCHEDULING (Tasks, Goals, Events, Choices) ---
    due_date: date | None = None
    scheduled_date: date | None = None
    start_date: date | None = None
    target_date: date | None = None
    event_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    decision_deadline: datetime | None = None
    duration_minutes: int | None = Field(None, ge=1, le=480)
    reminder_minutes: int | None = Field(None, ge=0, le=10080)
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_date: date | None = None

    # --- PROGRESS (Goals, Tasks) ---
    progress_percentage: float | None = Field(None, ge=0.0, le=100.0)
    current_value: float | None = Field(None, ge=0)
    target_value: float | None = Field(None, ge=0)
    unit_of_measurement: str | None = Field(None, max_length=50)
    measurement_type: MeasurementType | None = None
    progress_weight: float | None = Field(None, ge=0.0)

    # --- STREAK (Habits) ---
    current_streak: int | None = Field(None, ge=0)
    longest_streak: int | None = Field(None, ge=0)
    total_completions: int | None = Field(None, ge=0)
    target_days_per_week: int | None = Field(None, ge=1, le=7)
    preferred_time: str | None = None

    # --- GOAL-SPECIFIC ---
    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    why_important: str | None = Field(None, max_length=1000)
    success_criteria: str | None = Field(None, max_length=1000)
    potential_obstacles: list[str] | None = None
    strategies: list[str] | None = None
    vision_statement: str | None = Field(None, max_length=2000)

    # --- HABIT-SPECIFIC ---
    polarity: HabitPolarity | None = None
    category: HabitCategory | None = None
    difficulty: HabitDifficulty | None = None
    cue: str | None = Field(None, max_length=500)
    routine: str | None = Field(None, max_length=1000)
    reward: str | None = Field(None, max_length=500)
    reinforces_identity: str | None = Field(None, max_length=200)
    is_identity_habit: bool | None = None

    # --- EVENT-SPECIFIC ---
    event_type: str | None = None
    location: str | None = Field(None, max_length=500)
    is_online: bool | None = None
    meeting_url: str | None = None
    attendee_emails: list[str] | None = None
    max_attendees: int | None = Field(None, ge=1)

    # --- CHOICE-SPECIFIC ---
    choice_type: ChoiceType | None = None
    decision_criteria: list[str] | None = None
    constraints: list[str] | None = None
    stakeholders: list[str] | None = None
    selected_option_uid: str | None = None
    decision_rationale: str | None = Field(None, max_length=1000)

    # --- PRINCIPLE-SPECIFIC ---
    statement: str | None = Field(None, max_length=500)
    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None
    tradition: str | None = Field(None, max_length=100)
    original_source: str | None = Field(None, max_length=200)
    personal_interpretation: str | None = Field(None, max_length=1000)
    origin_story: str | None = Field(None, max_length=2000)
    key_behaviors: list[str] | None = None

    # --- ORGANIZATION ---
    parent_uid: str | None = None
    project: str | None = Field(None, max_length=200)
    assignee: str | None = None

    # --- CURRICULUM STRUCTURE ---
    sequence: int | None = Field(None, ge=1)
    intent: str | None = None
    mastery_threshold: float | None = Field(None, ge=0.0, le=1.0)
    estimated_hours: float | None = Field(None, gt=0)
    learning_path_uid: str | None = None
    lp_goal: str | None = None
    lp_type: LpType | None = None
    difficulty_level: str | None = None
    step_difficulty: StepDifficulty | None = None
    prerequisites: list[str] | None = None
    outcomes: list[str] | None = None
    notes: str | None = None


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class EntityResponse(ResponseBase):
    """API response for any entity type.

    Contains all fields needed to display any EntityType. Fields that don't apply
    to a specific EntityType will be at their default value (None, 0, [], etc.).
    """

    uid: str
    title: str
    entity_type: EntityType
    user_uid: str | None = None
    parent_entity_uid: str | None = None
    parent_uid: str | None = None
    domain: Domain
    created_by: str | None = None

    # Content
    description: str | None = None
    content: str | None = None
    summary: str = ""
    word_count: int = 0

    # File
    original_filename: str | None = None
    file_type: str | None = None

    # Processing
    status: EntityStatus
    processor_type: ProcessorType | None = None
    processing_error: str | None = None
    priority: Priority | None = None

    # SubmissionFeedback
    feedback: str | None = None
    feedback_generated_at: datetime | None = None
    subject_uid: str | None = None

    # Learning
    complexity: KuComplexity = KuComplexity.MEDIUM
    learning_level: LearningLevel = LearningLevel.BEGINNER
    sel_category: SELCategory | None = None
    quality_score: float = 0.0
    estimated_time_minutes: int = 15
    difficulty_rating: float = 0.5
    semantic_links: list[str] = Field(default_factory=list)

    # Sharing
    visibility: Visibility = Visibility.PRIVATE

    # Substance tracking
    times_applied_in_tasks: int = 0
    times_practiced_in_events: int = 0
    times_built_into_habits: int = 0
    journal_reflections_count: int = 0
    choices_informed_count: int = 0

    # Scheduling
    due_date: date | None = None
    scheduled_date: date | None = None
    start_date: date | None = None
    target_date: date | None = None
    event_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    decision_deadline: datetime | None = None
    duration_minutes: int | None = None
    recurrence_pattern: RecurrencePattern | None = None

    # Progress
    progress_percentage: float = 0.0
    current_value: float = 0.0
    target_value: float | None = None
    unit_of_measurement: str | None = None
    measurement_type: MeasurementType | None = None

    # Streak (Habits)
    current_streak: int = 0
    longest_streak: int = 0
    total_completions: int = 0
    target_days_per_week: int | None = None

    # Goal-specific
    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    vision_statement: str | None = None
    why_important: str | None = None
    success_criteria: str | None = None

    # Habit-specific
    polarity: HabitPolarity | None = None
    category: HabitCategory | None = None
    difficulty: HabitDifficulty | None = None
    cue: str | None = None
    routine: str | None = None
    reward: str | None = None
    is_identity_habit: bool = False

    # Choice-specific
    choice_type: ChoiceType | None = None
    selected_option_uid: str | None = None
    decision_rationale: str | None = None

    # Principle-specific
    statement: str | None = None
    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None

    # Curriculum structure
    sequence: int | None = None
    intent: str | None = None
    mastery_threshold: float | None = None
    estimated_hours: float | None = None
    lp_type: LpType | None = None

    # Event-specific
    event_type: str | None = None
    location: str | None = None
    is_online: bool = False

    # Organization
    project: str | None = None
    assignee: str | None = None

    # Meta
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    # Computed
    is_user_owned: bool = False
    is_derived: bool = False
    estimated_reading_time: int = 0

    @classmethod
    def from_dto(cls, dto: Any) -> "EntityResponse":
        """Create response from DTO."""
        estimated_reading_time = max(1, dto.word_count // 200) if dto.word_count > 0 else 0

        return cls(
            # Identity
            uid=dto.uid,
            title=dto.title,
            entity_type=dto.entity_type,
            user_uid=dto.user_uid,
            parent_entity_uid=dto.parent_entity_uid,
            parent_uid=dto.parent_uid,
            domain=dto.domain,
            created_by=dto.created_by,
            # Content
            description=dto.description,
            content=dto.content,
            summary=dto.summary,
            word_count=dto.word_count,
            # File
            original_filename=dto.original_filename,
            file_type=dto.file_type,
            # Processing
            status=dto.status,
            processor_type=dto.processor_type,
            processing_error=dto.processing_error,
            priority=dto.priority,
            # SubmissionFeedback
            feedback=dto.feedback,
            feedback_generated_at=dto.feedback_generated_at,
            subject_uid=dto.subject_uid,
            # Learning
            complexity=dto.complexity,
            learning_level=dto.learning_level,
            sel_category=dto.sel_category,
            quality_score=dto.quality_score,
            estimated_time_minutes=dto.estimated_time_minutes,
            difficulty_rating=dto.difficulty_rating,
            semantic_links=dto.semantic_links,
            # Sharing
            visibility=dto.visibility,
            # Substance tracking
            times_applied_in_tasks=dto.times_applied_in_tasks,
            times_practiced_in_events=dto.times_practiced_in_events,
            times_built_into_habits=dto.times_built_into_habits,
            journal_reflections_count=dto.journal_reflections_count,
            choices_informed_count=dto.choices_informed_count,
            # Scheduling
            due_date=dto.due_date,
            scheduled_date=dto.scheduled_date,
            start_date=dto.start_date,
            target_date=dto.target_date,
            event_date=dto.event_date,
            start_time=dto.start_time,
            end_time=dto.end_time,
            decision_deadline=dto.decision_deadline,
            duration_minutes=dto.duration_minutes,
            recurrence_pattern=dto.recurrence_pattern,
            # Progress
            progress_percentage=dto.progress_percentage,
            current_value=dto.current_value,
            target_value=dto.target_value,
            unit_of_measurement=dto.unit_of_measurement,
            measurement_type=dto.measurement_type,
            # Streak
            current_streak=dto.current_streak,
            longest_streak=dto.best_streak,
            total_completions=dto.total_completions,
            target_days_per_week=dto.target_days_per_week,
            # Goal-specific
            goal_type=dto.goal_type,
            timeframe=dto.timeframe,
            vision_statement=dto.vision_statement,
            why_important=dto.why_important,
            success_criteria=dto.success_criteria,
            # Habit-specific
            polarity=dto.polarity,
            category=dto.habit_category,
            difficulty=dto.habit_difficulty,
            cue=dto.cue,
            routine=dto.routine,
            reward=dto.reward,
            is_identity_habit=dto.is_identity_habit,
            # Choice-specific
            choice_type=dto.choice_type,
            selected_option_uid=dto.selected_option_uid,
            decision_rationale=dto.decision_rationale,
            # Principle-specific
            statement=dto.statement,
            principle_category=dto.principle_category,
            principle_source=dto.principle_source,
            strength=dto.strength,
            # Curriculum structure
            sequence=dto.sequence,
            intent=dto.intent,
            mastery_threshold=dto.mastery_threshold,
            estimated_hours=dto.estimated_hours,
            lp_type=dto.path_type,
            # Event-specific
            event_type=dto.event_type,
            location=dto.location,
            is_online=dto.is_online,
            # Organization
            project=dto.project,
            assignee=dto.assignee,
            # Meta
            tags=dto.tags,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            # Computed
            is_user_owned=dto.user_uid is not None,
            is_derived=dto.parent_entity_uid is not None,
            estimated_reading_time=estimated_reading_time,
        )


class EntityListResponse(ListResponseBase):
    """Response for listing multiple entity items."""

    items: list[EntityResponse]


# =============================================================================
# ROUTE-SPECIFIC REQUEST MODELS (content management, bulk ops, progress, schedule)
# =============================================================================


class CategorizeEntityRequest(BaseModel):
    """Request to categorize an entity."""

    category: str = Field(
        ...,
        description="Category from ReportCategory constants",
        examples=["daily", "weekly", "reflection", "work"],
    )


class AddTagsRequest(BaseModel):
    """Request to add tags to an entity."""

    tags: list[str] = Field(
        ...,
        min_length=1,
        description="List of tags to add",
        examples=[["work", "priority", "review"]],
    )


class RemoveTagsRequest(BaseModel):
    """Request to remove tags from an entity."""

    tags: list[str] = Field(..., min_length=1, description="List of tags to remove")


class BulkCategorizeRequest(BaseModel):
    """Request to categorize multiple entities."""

    entity_uids: list[str] = Field(..., min_length=1, description="List of entity UIDs")
    category: str = Field(..., description="Category to assign")


class BulkTagRequest(BaseModel):
    """Request to tag multiple entities."""

    entity_uids: list[str] = Field(..., min_length=1, description="List of entity UIDs")
    tags: list[str] = Field(..., min_length=1, description="List of tags to add")


class BulkDeleteRequest(BaseModel):
    """Request to delete multiple entities."""

    entity_uids: list[str] = Field(..., min_length=1, description="List of entity UIDs to delete")
    soft_delete: bool = Field(
        default=True,
        description="If True, archive instead of permanent delete",
    )


class ProgressReportGenerateRequest(BaseModel):
    """Request model for on-demand progress entity generation."""

    time_period: str = Field(
        default="7d",
        description="Time period: 7d, 14d, 30d, or 90d",
        pattern=r"^(7d|14d|30d|90d)$",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Domains to include (empty = all activity domains)",
    )
    depth: str = Field(
        default="standard",
        description="Report depth: summary, standard, or detailed",
        pattern=r"^(summary|standard|detailed)$",
    )
    include_insights: bool = Field(
        default=True,
        description="Include active insights from InsightStore",
    )


class ScheduleCreateRequest(BaseModel):
    """Request model for creating an entity generation schedule."""

    schedule_type: str = Field(
        default="weekly",
        description="Schedule frequency: weekly, biweekly, or monthly",
        pattern=r"^(weekly|biweekly|monthly)$",
    )
    day_of_week: int = Field(
        default=0,
        ge=0,
        le=6,
        description="Day of week (0=Monday, 6=Sunday)",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Domains to include (empty = all)",
    )
    depth: str = Field(
        default="standard",
        description="Report depth: summary, standard, or detailed",
        pattern=r"^(summary|standard|detailed)$",
    )


class ScheduleUpdateRequest(BaseModel):
    """Request model for updating an entity schedule. All fields optional."""

    schedule_type: str | None = Field(
        None,
        description="Schedule frequency",
        pattern=r"^(weekly|biweekly|monthly)$",
    )
    day_of_week: int | None = Field(None, ge=0, le=6, description="Day of week")
    domains: list[str] | None = Field(None, description="Domains to include")
    depth: str | None = Field(
        None,
        description="Report depth",
        pattern=r"^(summary|standard|detailed)$",
    )
    is_active: bool | None = Field(None, description="Enable/disable schedule")
