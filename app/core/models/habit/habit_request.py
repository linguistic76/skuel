"""
Habit Request Models (Tier 1 - External)
=========================================

Pydantic models for external API requests.
Handles validation and serialization at system boundaries.

Uses shared validators from validation_rules.py for DRY compliance.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.models.enums import Priority, RecurrencePattern, TimeOfDay
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty, HabitPolarity
from core.models.habit.habit_update_intent import HabitUpdateIntent
from core.models.sentinels import UNSET, Unset
from core.models.validation_rules import (
    validate_habit_duration_by_difficulty,
    validate_habit_target_days_by_pattern,
    validate_required_string,
)


class HabitCreateRequest(BaseModel):
    """
    External request for creating a habit.
    Validates input from API/UI layer.

    Field names mirror the ``Habit`` domain model 1:1 so ``FormGenerator.from_instance``
    auto-prefills the edit form and the create service can copy fields without a
    rename table. See: feedback_userctx_single_source_of_truth on the One Path
    Forward principle.
    """

    # Required fields
    title: str = Field(..., min_length=1, max_length=200, description="Habit title")

    # Optional with defaults
    description: str | None = Field(
        default=None, max_length=1000, description="Detailed description of the habit"
    )
    polarity: HabitPolarity = Field(
        default=HabitPolarity.BUILD,
        description="Whether to 'build' (establish) or 'break' (eliminate) this habit",
    )
    habit_category: HabitCategory = Field(
        default=HabitCategory.OTHER,
        description="Category: health, learning, productivity, social, creative, mindfulness, financial, or other",
    )
    habit_difficulty: HabitDifficulty = Field(
        default=HabitDifficulty.MODERATE,
        description="Difficulty level: trivial, easy, moderate, challenging, or heroic",
    )

    # Schedule
    recurrence_pattern: RecurrencePattern = Field(
        default=RecurrencePattern.DAILY, description="How often: daily, weekly, monthly, or custom"
    )
    target_days_per_week: int = Field(
        default=7, ge=1, le=7, description="Target days per week (1-7)"
    )
    preferred_time: TimeOfDay | None = Field(
        default=None,
        description=(
            "Time-of-day slot: early_morning, morning, afternoon, evening, night, "
            "late_night, anytime — or null for no declared slot"
        ),
    )
    duration_minutes: int | None = Field(
        default=None, ge=1, le=480, description="Expected duration in minutes per occurrence"
    )

    # Learning Integration
    linked_knowledge_uids: list[str] = Field(
        default_factory=list, description="List of KnowledgeUnit UIDs this habit reinforces"
    )
    linked_goal_uids: list[str] = Field(
        default_factory=list, description="List of Goal UIDs this habit supports"
    )
    linked_principle_uids: list[str] = Field(
        default_factory=list, description="List of Principle UIDs this habit embodies"
    )
    prerequisite_habit_uids: list[str] = Field(
        default_factory=list, description="List of Habit UIDs that should be established first"
    )

    # Behavioral Science
    cue: str | None = Field(default=None, max_length=500, description="Trigger/cue")
    routine: str | None = Field(default=None, max_length=1000, description="Specific actions")
    reward: str | None = Field(default=None, max_length=500, description="Immediate reward")

    # Identity (Atomic Habits)
    reinforces_identity: str | None = Field(
        default=None,
        max_length=200,
        description="Identity this habit reinforces, e.g., 'I am a writer'",
    )
    is_identity_habit: bool = Field(
        default=False, description="True if primary purpose is identity reinforcement"
    )

    # Organization
    priority: Priority = Field(Priority.MEDIUM)
    tags: list[str] = Field(default_factory=list, max_length=20)

    # Shared validators
    _validate_title = validate_required_string("title")
    _validate_duration = validate_habit_duration_by_difficulty()
    _validate_target_days = validate_habit_target_days_by_pattern()

    model_config = ConfigDict(
        use_enum_values=False,  # Keep enums as objects
        json_schema_extra={
            "example": {
                "title": "Morning Meditation",
                "description": "10 minutes of mindfulness meditation",
                "habit_category": "mindfulness",
                "habit_difficulty": "easy",
                "recurrence_pattern": "daily",
                "target_days_per_week": 7,
                "preferred_time": "morning",
                "duration_minutes": 10,
                "cue": "After morning coffee",
                "routine": "Sit in quiet room, focus on breath",
                "reward": "Feel calm and centered",
                "priority": "high",
                "tags": ["wellness", "mental-health"],
            }
        },
    )


class HabitUpdateRequest(BaseModel):
    """
    External request for updating a habit.
    All fields are optional for partial updates.

    Field names mirror the ``Habit`` domain model 1:1 (see HabitCreateRequest).
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)

    # Behavior can be modified
    polarity: HabitPolarity | None = None
    habit_category: HabitCategory | None = None
    habit_difficulty: HabitDifficulty | None = None

    # Schedule can be adjusted
    recurrence_pattern: RecurrencePattern | None = None
    target_days_per_week: int | None = Field(default=None, ge=1, le=7)
    preferred_time: TimeOfDay | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=480)

    # Links can be updated
    linked_knowledge_uids: list[str] | None = None
    linked_goal_uids: list[str] | None = None
    linked_principle_uids: list[str] | None = None
    prerequisite_habit_uids: list[str] | None = None

    # Behavioral elements can be refined
    cue: str | None = Field(default=None, max_length=500)
    routine: str | None = Field(default=None, max_length=1000)
    reward: str | None = Field(default=None, max_length=500)

    # Status and priority can change
    status: EntityStatus | None = None
    priority: Priority | None = None
    tags: list[str] | None = Field(default=None, max_length=20)

    model_config = ConfigDict(
        use_enum_values=False,
        json_schema_extra={
            "example": {
                "duration_minutes": 15,
                "habit_difficulty": "moderate",
                "routine": "Updated routine with more detail",
            }
        },
    )

    def to_intent(self) -> HabitUpdateIntent:
        """Build the typed ``HabitUpdateIntent`` (ADR-066) from explicitly-set fields.

        Only fields the caller actually provided (``model_fields_set``) become non-``UNSET``,
        so the intent carries a true partial patch: an absent field is left untouched, a
        field explicitly set to ``None`` is an explicit clear. Enum fields (polarity,
        habit_category, habit_difficulty, recurrence_pattern, preferred_time, status,
        priority) are lowered to their string value to match the persistence boundary.

        The four cross-domain UID fields (``linked_knowledge_uids`` / ``linked_goal_uids`` /
        ``linked_principle_uids`` / ``prerequisite_habit_uids``) are graph edges, not node
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

        return HabitUpdateIntent(
            title=when_set("title", self.title),
            description=when_set("description", self.description),
            polarity=when_set(
                "polarity", self.polarity.value if self.polarity is not None else None
            ),
            habit_category=when_set(
                "habit_category",
                self.habit_category.value if self.habit_category is not None else None,
            ),
            habit_difficulty=when_set(
                "habit_difficulty",
                self.habit_difficulty.value if self.habit_difficulty is not None else None,
            ),
            recurrence_pattern=when_set(
                "recurrence_pattern",
                self.recurrence_pattern.value if self.recurrence_pattern is not None else None,
            ),
            target_days_per_week=when_set("target_days_per_week", self.target_days_per_week),
            preferred_time=when_set(
                "preferred_time",
                self.preferred_time.value if self.preferred_time is not None else None,
            ),
            duration_minutes=when_set("duration_minutes", self.duration_minutes),
            cue=when_set("cue", self.cue),
            routine=when_set("routine", self.routine),
            reward=when_set("reward", self.reward),
            status=when_set("status", self.status.value if self.status is not None else None),
            priority=when_set(
                "priority", self.priority.value if self.priority is not None else None
            ),
            tags=when_set("tags", self.tags),
        )


class HabitCompletionRequest(BaseModel):
    """
    Request to record a habit completion.
    """

    completed_at: datetime | None = Field(default_factory=datetime.now)
    notes: str | None = Field(default=None, max_length=500, description="Completion notes")
    quality: int | None = Field(default=None, ge=1, le=5, description="Quality rating 1-5")
    duration_actual: int | None = Field(
        default=None, ge=0, description="Actual duration in minutes"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "notes": "Felt great today, extended session",
                "quality": 5,
                "duration_actual": 12,
            }
        }
    )


class HabitSkipRequest(BaseModel):
    """
    Request to record skipping a habit.
    """

    skipped_at: datetime | None = Field(default_factory=datetime.now)
    reason: str | None = Field(default=None, max_length=500, description="Reason for skipping")
    planned_skip: bool = Field(default=False, description="Was this planned/intentional?")

    model_config = ConfigDict(
        json_schema_extra={"example": {"reason": "Sick today", "planned_skip": False}}
    )


class HabitFilterRequest(BaseModel):
    """
    Request for filtering habits.
    """

    category: HabitCategory | None = None
    status: EntityStatus | None = None
    priority: Priority | None = None
    difficulty: HabitDifficulty | None = None
    polarity: HabitPolarity | None = None

    # Learning filters
    has_knowledge_links: bool | None = None
    has_goal_links: bool | None = None
    supports_learning: bool | None = None

    # Progress filters
    min_streak: int | None = Field(default=None, ge=0)
    min_success_rate: float | None = Field(default=None, ge=0, le=100)
    on_streak: bool | None = None

    # Time filters
    preferred_time: TimeOfDay | None = None
    max_duration_minutes: int | None = Field(default=None, ge=1)

    # Tag filter
    tags: list[str] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "category": "learning",
                "status": "active",
                "min_success_rate": 70.0,
                "on_streak": True,
            }
        }
    )


class HabitStatsRequest(BaseModel):
    """
    Request for habit statistics.
    """

    include_completions: bool = Field(default=True, description="Include completion history")
    include_streaks: bool = Field(default=True, description="Include streak analysis")
    include_predictions: bool = Field(default=False, description="Include success predictions")
    days_back: int = Field(default=30, ge=1, le=365, description="Days of history to analyze")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "include_completions": True,
                "include_streaks": True,
                "include_predictions": True,
                "days_back": 90,
            }
        }
    )


# =============================================================================
# OPERATION-SPECIFIC REQUEST TYPES
# =============================================================================
# These typed request objects make the API contract explicit and refactoring-safe.
# Pattern: Each service operation that takes multiple parameters gets a request type.


class TrackHabitRequest(BaseModel):
    """Request for tracking/recording a habit completion."""

    model_config = ConfigDict(populate_by_name=True)

    habit_uid: str = Field(description="UID of the habit to track")
    completion_date: str | None = Field(
        default=None,
        validation_alias="date",
        description="Date of completion (ISO format, default: today)",
    )
    value: int = Field(default=1, ge=1, le=5, description="Quality/value rating (1-5)")
    notes: str | None = Field(default=None, max_length=500, description="Optional completion notes")


class UntrackHabitRequest(BaseModel):
    """Request for removing a habit tracking entry."""

    model_config = ConfigDict(populate_by_name=True)

    habit_uid: str = Field(description="UID of the habit")
    completion_date: str | None = Field(
        default=None,
        validation_alias="date",
        description="Date to untrack (ISO format, default: today)",
    )


class PauseHabitRequest(BaseModel):
    """Request for pausing a habit temporarily."""

    habit_uid: str = Field(description="UID of the habit to pause")
    reason: str = Field(default="Paused", max_length=500, description="Reason for pausing")
    until_date: str | None = Field(
        default=None, description="Optional date to auto-resume (ISO format)"
    )


class ResumeHabitRequest(BaseModel):
    """Request for resuming a paused habit."""

    habit_uid: str = Field(description="UID of the habit to resume")


class ArchiveHabitRequest(BaseModel):
    """Request for archiving a habit."""

    habit_uid: str = Field(description="UID of the habit to archive")
    reason: str = Field(default="Archived", max_length=500, description="Reason for archiving")


class SetHabitReminderRequest(BaseModel):
    """Request for setting a habit reminder."""

    habit_uid: str = Field(description="UID of the habit")
    reminder_time: str = Field(description="Time for reminder (HH:MM format)")
    days: list[str] = Field(default_factory=list, description="Days of week for reminder")
    enabled: bool = Field(default=True, description="Whether reminder is enabled")


class DeleteHabitReminderRequest(BaseModel):
    """Request for deleting a habit reminder."""

    habit_uid: str = Field(description="UID of the habit")
    reminder_id: str = Field(description="ID of reminder to delete")


class GetHabitProgressRequest(BaseModel):
    """Request for getting habit progress statistics."""

    habit_uid: str = Field(description="UID of the habit")
    period: str = Field(default="month", description="Time period: 'week', 'month', or 'year'")


class BulkCompleteHabitsRequest(BaseModel):
    """Request for recording completions for multiple habits at once."""

    habit_uids: list[str] = Field(description="UIDs of habits to mark complete", min_length=1)


# Type literal for context-aware quality validation
ContextualQualityLiteral = Literal["poor", "fair", "good", "excellent"]


class ContextualHabitCompletionRequest(BaseModel):
    """
    Request model for completing a habit with context tracking.

    Used by: POST /api/context/habit/complete

    Fields:
        quality: Quality rating of the habit completion (poor/fair/good/excellent)
        environmental_factors: Optional environmental context (location, time, mood, etc.)
    """

    quality: ContextualQualityLiteral = Field(
        default="good",
        description="Quality rating of the habit completion",
    )
    environmental_factors: dict[str, Any] = Field(
        default_factory=dict,
        description="Environmental context (location, time_of_day, mood, obstacles, etc.)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "quality": "excellent",
                "environmental_factors": {
                    "location": "home",
                    "time_of_day": "morning",
                    "mood": "energized",
                    "obstacles": [],
                },
            }
        }
    )
