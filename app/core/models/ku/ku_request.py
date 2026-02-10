"""
Unified Knowledge Request Models (Tier 1 - External)
=====================================================

"Ku is the heartbeat of SKUEL."

Pydantic models for API boundaries — validation and serialization.
Four create requests (one per KuType), one update, one response.

Create requests:
    KuCurriculumCreateRequest  → Admin creates shared knowledge
    KuAssignmentCreateRequest  → Student submits work
    KuAiReportCreateRequest    → System creates AI-derived analysis
    KuFeedbackCreateRequest    → Teacher provides feedback

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from core.models.enums import Domain, KuComplexity, LearningLevel, SELCategory
from core.models.enums.ku_enums import KuStatus, KuType, ProcessorType
from core.models.enums.metadata_enums import Visibility
from core.models.request_base import (
    CreateRequestBase,
    ListResponseBase,
    ResponseBase,
    UpdateRequestBase,
)

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO


# =============================================================================
# CREATE REQUESTS (one per KuType)
# =============================================================================


class KuCurriculumCreateRequest(CreateRequestBase):
    """Create admin-authored curriculum knowledge (CURRICULUM type)."""

    title: str = Field(min_length=1, max_length=200, description="Title of the knowledge unit")
    domain: Domain = Field(description="Knowledge domain")

    # Content
    content: str | None = Field(None, description="Body text")
    summary: str | None = Field(None, max_length=500, description="Brief summary")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")

    # Learning metadata
    complexity: KuComplexity = Field(default=KuComplexity.MEDIUM, description="Difficulty level")
    sel_category: SELCategory | None = Field(None, description="SEL category lens")
    learning_level: LearningLevel = Field(
        default=LearningLevel.BEGINNER, description="Target learning level"
    )
    estimated_time_minutes: int = Field(default=15, ge=1, description="Estimated completion time")
    difficulty_rating: float = Field(default=0.5, ge=0.0, le=1.0, description="Difficulty 0.0-1.0")


class KuAssignmentCreateRequest(CreateRequestBase):
    """Create a student submission (ASSIGNMENT type)."""

    title: str = Field(min_length=1, max_length=200, description="Submission title")

    # Content (at least one of content or file expected)
    content: str | None = Field(None, description="Text content of submission")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Derivation
    parent_ku_uid: str | None = Field(
        None, description="Curriculum Ku this assignment is based on"
    )

    # Processing
    processor_type: ProcessorType | None = Field(
        None, description="How to process (LLM, HUMAN, etc.)"
    )
    instructions: str | None = Field(
        None, description="Processing instructions (absorbed from ReportProject)"
    )

    # File metadata (populated by upload handler, not user input)
    original_filename: str | None = Field(None, description="Uploaded filename")
    file_path: str | None = Field(None, description="Server file path")
    file_size: int | None = Field(None, ge=0, description="File size in bytes")
    file_type: str | None = Field(None, description="MIME type")


class KuAiReportCreateRequest(CreateRequestBase):
    """Create an AI-derived report (AI_REPORT type). System-initiated."""

    title: str = Field(min_length=1, max_length=200, description="Report title")
    parent_ku_uid: str = Field(description="Assignment Ku this report derives from")

    # Content
    content: str | None = Field(None, description="AI-generated analysis")
    processed_content: str | None = Field(None, description="Processed output")
    summary: str | None = Field(None, max_length=500, description="Brief summary")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")

    # Processing
    processor_type: ProcessorType = Field(
        default=ProcessorType.LLM, description="Processing type"
    )
    instructions: str | None = Field(None, description="Instructions used for generation")


class KuFeedbackCreateRequest(CreateRequestBase):
    """Create teacher feedback on an assignment (FEEDBACK_REPORT type)."""

    title: str = Field(min_length=1, max_length=200, description="Feedback title")
    parent_ku_uid: str = Field(description="Assignment Ku being reviewed")
    subject_uid: str | None = Field(None, description="Student UID the feedback is about")

    # Content
    feedback: str = Field(min_length=1, description="Feedback text")
    content: str | None = Field(None, description="Additional content")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")


# =============================================================================
# UPDATE REQUEST (shared across all KuTypes)
# =============================================================================


class KuUpdateRequest(UpdateRequestBase):
    """Update any Ku type. All fields optional."""

    title: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = None
    summary: str | None = Field(None, max_length=500)
    domain: Domain | None = None
    tags: list[str] | None = None

    # Processing
    status: KuStatus | None = None
    processor_type: ProcessorType | None = None
    instructions: str | None = None
    processing_error: str | None = None
    processed_content: str | None = None

    # Feedback
    feedback: str | None = None
    subject_uid: str | None = None

    # Learning metadata
    complexity: KuComplexity | None = None
    learning_level: LearningLevel | None = None
    sel_category: SELCategory | None = None
    quality_score: float | None = Field(None, ge=0.0, le=1.0)
    estimated_time_minutes: int | None = Field(None, ge=1)
    difficulty_rating: float | None = Field(None, ge=0.0, le=1.0)

    # Sharing
    visibility: Visibility | None = None


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class KuResponse(ResponseBase):
    """API response for any Ku type."""

    uid: str
    title: str
    ku_type: KuType
    user_uid: str | None = None
    parent_ku_uid: str | None = None
    domain: Domain
    created_by: str | None = None

    # Content
    content: str | None = None
    summary: str = ""
    word_count: int = 0

    # File
    original_filename: str | None = None
    file_type: str | None = None

    # Processing
    status: KuStatus
    processor_type: ProcessorType | None = None
    processing_error: str | None = None

    # Feedback
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
    semantic_links: list[str] = []

    # Sharing
    visibility: Visibility = Visibility.PRIVATE

    # Substance tracking
    times_applied_in_tasks: int = 0
    times_practiced_in_events: int = 0
    times_built_into_habits: int = 0
    journal_reflections_count: int = 0
    choices_informed_count: int = 0

    # Meta
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime

    # Computed
    is_user_owned: bool = False
    is_derived: bool = False
    estimated_reading_time: int = 0

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "KuResponse":
        """Create response from DTO."""
        estimated_reading_time = max(1, dto.word_count // 200) if dto.word_count > 0 else 0

        return cls(
            # Identity
            uid=dto.uid,
            title=dto.title,
            ku_type=dto.ku_type,
            user_uid=dto.user_uid,
            parent_ku_uid=dto.parent_ku_uid,
            domain=dto.domain,
            created_by=dto.created_by,
            # Content
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
            # Feedback
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
            # Meta
            tags=dto.tags,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            # Computed
            is_user_owned=dto.user_uid is not None,
            is_derived=dto.parent_ku_uid is not None,
            estimated_reading_time=estimated_reading_time,
        )


class KuListResponse(ListResponseBase):
    """Response for listing multiple Ku items."""

    items: list[KuResponse]


# =============================================================================
# ROUTE-SPECIFIC REQUEST MODELS (content management, bulk ops, progress, schedule)
# =============================================================================


class CategorizeKuRequest(BaseModel):
    """Request to categorize a Ku."""

    category: str = Field(
        ...,
        description="Category from KuCategory constants",
        examples=["daily", "weekly", "reflection", "work"],
    )


class AddTagsRequest(BaseModel):
    """Request to add tags to a Ku."""

    tags: list[str] = Field(
        ...,
        min_length=1,
        description="List of tags to add",
        examples=[["work", "priority", "review"]],
    )


class RemoveTagsRequest(BaseModel):
    """Request to remove tags from a Ku."""

    tags: list[str] = Field(..., min_length=1, description="List of tags to remove")


class BulkCategorizeRequest(BaseModel):
    """Request to categorize multiple Ku."""

    ku_uids: list[str] = Field(..., min_length=1, description="List of Ku UIDs")
    category: str = Field(..., description="Category to assign")


class BulkTagRequest(BaseModel):
    """Request to tag multiple Ku."""

    ku_uids: list[str] = Field(..., min_length=1, description="List of Ku UIDs")
    tags: list[str] = Field(..., min_length=1, description="List of tags to add")


class BulkDeleteRequest(BaseModel):
    """Request to delete multiple Ku."""

    ku_uids: list[str] = Field(..., min_length=1, description="List of Ku UIDs to delete")
    soft_delete: bool = Field(
        default=True,
        description="If True, archive instead of permanent delete",
    )


class ProgressKuGenerateRequest(BaseModel):
    """Request model for on-demand progress Ku generation."""

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


class KuScheduleCreateRequest(BaseModel):
    """Request model for creating a Ku generation schedule."""

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


class KuScheduleUpdateRequest(BaseModel):
    """Request model for updating a Ku schedule. All fields optional."""

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


class AssessmentCreateRequest(BaseModel):
    """Request model for creating a teacher assessment (FEEDBACK_REPORT Ku)."""

    subject_uid: str = Field(..., description="Student being assessed")
    title: str = Field(..., min_length=1, max_length=500, description="Assessment title")
    content: str = Field(..., min_length=1, description="Assessment content (markdown)")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")
