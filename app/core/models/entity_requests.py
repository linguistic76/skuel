"""
Entity-Wide Request Models (Cross-Domain)
==========================================

Pydantic models shared across all entity types:
- Bulk operations (tags, categorize, delete)
- Schedule management (progress report generation)
- Route-specific link / hierarchy / review requests

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from typing import Any

from pydantic import BaseModel, Field

from core.models.enums.relationship_enums import KnowledgeRelevance, ProficiencyLevel

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
        description=(
            "The report-period token: a trailing window (7d, 14d, 30d, 90d) or a "
            "calendar period (2026-W37, 2026-09); resolved by core/utils/report_periods.py"
        ),
        pattern=r"^(7d|14d|30d|90d|\d{4}-(0[1-9]|1[0-2])|\d{4}-W(0[1-9]|[1-4]\d|5[0-3]))$",
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


# =============================================================================
# ACTIVITY FEEDBACK / REVIEW REQUEST MODELS
# =============================================================================


class ActivityFeedbackSubmitRequest(BaseModel):
    """Admin submits written activity feedback for a user."""

    subject_uid: str = Field(..., description="UID of the user being reviewed")
    feedback_text: str = Field(..., min_length=1, description="Feedback text")
    time_period: str = Field(default="7d", description="Time period covered")
    domains: list[str] | None = Field(default=None, description="Activity domains to cover")
    snapshot_context: dict[str, Any] | None = Field(
        default=None, description="Snapshot context from prior review"
    )


class AnnotationSaveRequest(BaseModel):
    """Save user annotation or revision to an owned ActivityReport."""

    uid: str = Field(..., min_length=1, description="ActivityReport UID")
    annotation_mode: str = Field(default="", description="additive or revision")
    user_annotation: str | None = Field(default=None, description="Commentary text")
    user_revision: str | None = Field(default=None, description="Replacement text")


class AnnotationFormRequest(BaseModel):
    """The report detail page's notes form: one text field, a mode that says what it is."""

    uid: str = Field(..., min_length=1, description="ActivityReport UID")
    annotation_mode: str = Field(..., pattern=r"^(additive|revision)$")
    annotation_text: str | None = Field(default=None, description="The note or the replacement")

    def to_save_request(self) -> AnnotationSaveRequest:
        """Route the single text field to the field the chosen mode stores."""
        additive = self.annotation_mode == "additive"
        return AnnotationSaveRequest(
            uid=self.uid,
            annotation_mode=self.annotation_mode,
            user_annotation=self.annotation_text if additive else None,
            user_revision=None if additive else self.annotation_text,
        )


class ActivityReviewRequest(BaseModel):
    """User requests an activity review from an admin."""

    time_period: str = Field(default="7d", description="Time period to review")
    domains: list[str] | None = Field(default=None, description="Domains to review")
    message: str | None = Field(default=None, max_length=1000, description="Optional message")


class CalendarQuickCreateRequest(BaseModel):
    """Quick create a calendar item."""

    type: str = Field(..., description="Calendar item type")
    title: str = Field(..., min_length=1, description="Item title")
    start_time: str = Field(..., description="Start time (ISO format)")
    extras: dict[str, Any] = Field(default_factory=dict, description="Additional fields")


class ChangeUserRoleRequest(BaseModel):
    """Request to change a user's role."""

    role: str = Field(..., min_length=1, description="New role name")


class DeactivateUserRequest(BaseModel):
    """Request to deactivate a user account — the body is optional, so every field is."""

    reason: str = Field(default="", description="Reason recorded with the deactivation")


class SmartDismissRequest(BaseModel):
    """Request to smart-dismiss insights matching a filter."""

    filter_type: str = Field(..., description="Filter type: impact, domain, or type")
    filter_value: str = Field(..., description="Filter value to match")


class RemoveHierarchyChildRequest(BaseModel):
    """Remove a parent-child hierarchy relationship.

    Shared by all 6 Activity Domains (tasks, goals, habits, events, choices, principles).
    """

    parent_uid: str = Field(..., min_length=1, description="Parent entity UID")
    child_uid: str = Field(..., min_length=1, description="Child entity UID")


class AddHierarchyChildRequest(BaseModel):
    """Add a parent-child hierarchy relationship.

    Shared by all 6 Activity Domains (tasks, goals, habits, events, choices, principles).
    progress_weight is only used by Tasks, Goals, and Habits; other domains ignore it.
    """

    parent_uid: str = Field(..., min_length=1, description="Parent entity UID")
    child_uid: str = Field(..., min_length=1, description="Child entity UID")
    progress_weight: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Weight of child's contribution to parent progress"
    )


# ============================================================================
# CROSS-DOMAIN LINK REQUESTS — Theme D (motivational web)
# ============================================================================


class LinkTaskToGoalRequest(BaseModel):
    """Link a task to the goal it contributes to (CONTRIBUTES_TO_GOAL)."""

    task_uid: str = Field(..., min_length=1)
    goal_uid: str = Field(..., min_length=1)
    contribution_percentage: float = Field(default=0.1, ge=0.0, le=1.0)
    milestone_uid: str | None = None


class LinkGoalToKnowledgeRequest(BaseModel):
    """Link a goal to required knowledge/skill (REQUIRES_KNOWLEDGE)."""

    goal_uid: str = Field(..., min_length=1)
    knowledge_uid: str = Field(..., min_length=1)
    proficiency_required: ProficiencyLevel = ProficiencyLevel.INTERMEDIATE
    priority: int = Field(default=1, ge=1)


class LinkGoalToPrincipleRequest(BaseModel):
    """Link a goal to a guiding principle/value (GUIDED_BY_PRINCIPLE)."""

    goal_uid: str = Field(..., min_length=1)
    principle_uid: str = Field(..., min_length=1)
    alignment_strength: float = Field(default=1.0, ge=0.0, le=1.0)


class LinkHabitToKnowledgeRequest(BaseModel):
    """Link a habit to the knowledge/skill it develops (REINFORCES_KNOWLEDGE)."""

    habit_uid: str = Field(..., min_length=1)
    knowledge_uid: str = Field(..., min_length=1)
    skill_level: ProficiencyLevel = ProficiencyLevel.BEGINNER
    proficiency_gain_rate: float = Field(default=0.1, ge=0.0, le=1.0)


class LinkHabitToPrincipleRequest(BaseModel):
    """Link a habit to the principle/value it embodies (EMBODIES_PRINCIPLE)."""

    habit_uid: str = Field(..., min_length=1)
    principle_uid: str = Field(..., min_length=1)
    embodiment_strength: float = Field(default=1.0, ge=0.0, le=1.0)


class LinkEventToGoalRequest(BaseModel):
    """Link an event to the goal it contributes to (CONTRIBUTES_TO_GOAL)."""

    event_uid: str = Field(..., min_length=1)
    goal_uid: str = Field(..., min_length=1)
    contribution_weight: float = Field(default=1.0, ge=0.0, le=1.0)


class LinkChoiceToGoalRequest(BaseModel):
    """Link a choice to the goal it affects/advances (AFFECTS_GOAL)."""

    choice_uid: str = Field(..., min_length=1)
    goal_uid: str = Field(..., min_length=1)
    contribution_score: float = Field(default=0.5, ge=0.0, le=1.0)


class LinkChoiceToPrincipleRequest(BaseModel):
    """Link a choice to the principle it is informed by (INFORMED_BY_PRINCIPLE)."""

    choice_uid: str = Field(..., min_length=1)
    principle_uid: str = Field(..., min_length=1)
    alignment_score: float = Field(default=0.5, ge=0.0, le=1.0)


class LinkPrincipleToKnowledgeRequest(BaseModel):
    """Link a principle to the knowledge it is grounded in (GROUNDED_IN_KNOWLEDGE)."""

    principle_uid: str = Field(..., min_length=1)
    knowledge_uid: str = Field(..., min_length=1)
    relevance: KnowledgeRelevance = KnowledgeRelevance.FUNDAMENTAL
