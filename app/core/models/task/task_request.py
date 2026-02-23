"""
Task Request Models (Tier 1 - External)
========================================

Pydantic models for task API boundaries - validation and serialization.

Uses:
- Shared validation rules from core.models.validation_rules for DRY compliance
- Base classes from core.models.request_base for consistent configuration
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from core.models.enums import EntityStatus, Priority, RecurrencePattern
from core.models.request_base import (
    CreateRequestBase,
    FilterRequestBase,
    ListResponseBase,
    RequestBase,
    ResponseBase,
    UpdateRequestBase,
)
from core.models.validation_rules import (
    validate_future_date,
    validate_recurrence_end_after_start,
)


class TaskCreateRequest(CreateRequestBase):
    """External API request for creating a task."""

    title: str = Field(min_length=1, max_length=200, description="Task title")
    description: str | None = Field(None, description="Detailed description")

    # Scheduling
    due_date: date | None = Field(None, description="Due date")
    scheduled_date: date | None = Field(None, description="Scheduled work date")
    duration_minutes: int = Field(default=30, ge=5, le=480, description="Estimated duration")

    # Priority and status
    priority: Priority = Field(default=Priority.MEDIUM, description="Task priority")
    status: EntityStatus = Field(default=EntityStatus.DRAFT, description="Initial status")

    # Organization
    project: str | None = Field(None, description="Associated project")
    assignee: str | None = Field(None, description="Person assigned to this task")
    tags: list[str] = Field(default_factory=list, description="Task tags")

    # Hierarchical Relationships (2026-01-30 - Hierarchical Pattern)
    parent_uid: str | None = Field(None, description="Parent task UID for subtask decomposition")
    progress_weight: float = Field(
        default=1.0,
        ge=0.0,
        description="Contribution weight to parent progress (default: 1.0 = equal weight)",
    )

    # Recurrence
    recurrence_pattern: RecurrencePattern | None = Field(None, description="Recurrence pattern")
    recurrence_end_date: date | None = Field(None, description="End date for recurrence")

    # Learning Integration (OPTIONAL)
    fulfills_goal_uid: str | None = Field(None, description="Goal this task fulfills")
    reinforces_habit_uid: str | None = Field(None, description="Habit this task reinforces")
    applies_knowledge_uids: list[str] = Field(
        default_factory=list, description="Knowledge being applied"
    )
    aligned_principle_uids: list[str] = Field(
        default_factory=list, description="Aligned principles"
    )
    goal_progress_contribution: float = Field(
        0.0, ge=0.0, le=1.0, description="Goal progress contribution (0-1)"
    )
    knowledge_mastery_check: bool = Field(False, description="Is this a knowledge validation task?")
    habit_streak_maintainer: bool = Field(False, description="Does this maintain a habit streak?")
    prerequisite_knowledge_uids: list[str] = Field(
        default_factory=list, description="Required knowledge"
    )
    prerequisite_task_uids: list[str] = Field(default_factory=list, description="Required tasks")

    # Knowledge Suggestions (from UI)
    suggested_knowledge_uids: list[str] = Field(
        default_factory=list, description="AI-suggested knowledge connections"
    )

    # Shared validators (DRY pattern)
    _validate_dates = validate_future_date("due_date", "scheduled_date")
    _validate_recurrence_end = validate_recurrence_end_after_start(
        "recurrence_end_date", "due_date"
    )


class TaskUpdateRequest(UpdateRequestBase):
    """External API request for updating a task."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    due_date: date | None = None
    scheduled_date: date | None = None  # type: ignore[assignment]
    duration_minutes: int | None = Field(None, ge=5, le=480)
    priority: Priority | None = None
    status: EntityStatus | None = None
    project: str | None = None
    assignee: str | None = None
    tags: list[str] | None = None
    actual_minutes: int | None = Field(None, ge=0, description="Actual time spent")
    completion_date: date | None = None

    # Learning Integration Updates (OPTIONAL)
    fulfills_goal_uid: str | None = None
    reinforces_habit_uid: str | None = None
    applies_knowledge_uids: list[str] | None = None
    aligned_principle_uids: list[str] | None = None
    goal_progress_contribution: float | None = Field(None, ge=0.0, le=1.0)
    knowledge_mastery_check: bool | None = None
    habit_streak_maintainer: bool | None = None
    prerequisite_knowledge_uids: list[str] | None = None
    prerequisite_task_uids: list[str] | None = None


class TaskResponse(ResponseBase):
    """External API response for a task."""

    uid: str
    title: str
    description: str | None

    # Dates and timing
    due_date: date | None
    scheduled_date: date | None
    completion_date: date | None
    created_at: datetime
    updated_at: datetime

    # Duration
    duration_minutes: int
    actual_minutes: int | None

    # Status and priority
    status: EntityStatus
    priority: Priority

    # Organization
    project: str | None
    assignee: str | None
    tags: list[str]
    parent_uid: str | None
    subtask_uids: list[str]

    # Recurrence
    recurrence_pattern: RecurrencePattern | None
    recurrence_end_date: date | None
    recurrence_parent_uid: str | None

    # Learning Integration
    fulfills_goal_uid: str | None
    reinforces_habit_uid: str | None
    applies_knowledge_uids: list[str]
    aligned_principle_uids: list[str]
    goal_progress_contribution: float
    knowledge_mastery_check: bool
    habit_streak_maintainer: bool
    prerequisite_knowledge_uids: list[str]
    prerequisite_task_uids: list[str]
    enables_task_uids: list[str]
    scheduled_event_uid: str | None
    completion_updates_goal: bool
    completion_triggers_tasks: list[str]
    completion_unlocks_knowledge: list[str]

    # Computed fields
    is_overdue: bool
    is_recurring: bool
    is_parent: bool
    is_subtask: bool
    is_learning_task: bool
    is_habit_task: bool
    is_milestone_task: bool
    has_prerequisites: bool
    days_until_due: int | None
    progress_percentage: float
    learning_alignment_score: float
    impact_score: float


class TaskFilterRequest(FilterRequestBase):
    """Request model for filtering tasks."""

    status: EntityStatus | None = None
    priority: Priority | None = None
    project: str | None = None
    tags: list[str] | None = None
    due_date_from: date | None = None  # type: ignore[assignment]
    due_date_to: date | None = None
    assigned_to: str | None = None
    overdue_only: bool = False
    completed_only: bool = False


class TaskAssignmentRequest(RequestBase):
    """Request model for assigning tasks."""

    assigned_to: str = Field(min_length=1, description="User to assign task to")
    notes: str | None = Field(None, description="Assignment notes")
    due_date: date | None = Field(None, description="Override due date for assignment")

    # Shared validators (DRY pattern)
    _validate_due_date = validate_future_date("due_date")


class TaskStatusUpdateRequest(RequestBase):
    """Request model for updating task status."""

    status: EntityStatus = Field(description="New task status")
    notes: str | None = Field(None, description="Status change notes")
    completion_date: date | None = Field(None, description="Completion date if marking complete")
    actual_minutes: int | None = Field(None, ge=0, description="Actual time spent")

    @field_validator("completion_date")
    @classmethod
    def validate_completion_date(cls, v, info: ValidationInfo) -> Any:
        """Ensure completion date is provided when status is COMPLETED."""
        if info.data.get("status") == EntityStatus.COMPLETED and not v:
            v = date.today()  # Default to today if not provided
        return v


class ContextualTaskCompletionRequest(BaseModel):
    """
    Request model for completing a task with context awareness.

    Used by: POST /api/context/task/complete

    Fields:
        context: Context data about the completion (knowledge applied, time, quality)
        reflection: Optional reflection notes on the completion experience
    """

    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Context data (knowledge_applied, time_invested_minutes, quality)",
    )
    reflection: str = Field(
        default="",
        max_length=2000,
        description="Reflection notes on task completion",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "context": {
                    "knowledge_applied": ["ku.python", "ku.async-patterns"],
                    "time_invested_minutes": 120,
                    "quality": "good",
                },
                "reflection": "Learned about async context managers while implementing this feature.",
            }
        }
    )


class TaskListResponse(ListResponseBase):
    """Response for listing multiple tasks."""

    items: list[TaskResponse]

    # Summary statistics
    total_overdue: int
    total_today: int
    total_this_week: int
