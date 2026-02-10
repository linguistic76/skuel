"""
Unified Knowledge DTO (Tier 2 - Transfer)
==========================================

"Ku is the heartbeat of SKUEL."

Mutable data transfer object for ALL knowledge in the system. Four manifestations:

    CURRICULUM      → Admin-created shared knowledge (no owner)
    ASSIGNMENT      → Student submission (user-owned)
    AI_REPORT       → AI-derived from assignment (user-owned)
    FEEDBACK_REPORT → Teacher feedback on assignment (teacher-owned)

This DTO replaces both the old KuDTO (curriculum-only, 27 fields) and ReportDTO
(user submissions, 49 fields). One DTO, one pipeline. One Path Forward.

Uses KuDTOMixin for conditional user_uid validation:
    CURRICULUM:  user_uid must be None
    Others:      user_uid is required

Factory methods per KuType for type-safe creation:
    KuDTO.create_curriculum(title, domain, ...)
    KuDTO.create_assignment(user_uid, title, ...)
    KuDTO.create_ai_report(user_uid, title, parent_ku_uid, ...)
    KuDTO.create_feedback_report(user_uid, title, parent_ku_uid, ...)

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums import Domain, KuComplexity, LearningLevel, SELCategory
from core.models.enums.ku_enums import KuStatus, KuType, ProcessorType
from core.models.enums.metadata_enums import Visibility
from core.models.ku_dto_mixin import KuDTOMixin
from core.services.protocols import get_enum_value


@dataclass
class KuDTO(KuDTOMixin):
    """
    Mutable data transfer object for unified knowledge.

    47 business fields matching the Ku domain model, organized in 9 sections.

    Used for:
    - Moving data between service and repository layers
    - Database operations (save/update)
    - Service-to-service communication
    """

    # =========================================================================
    # IDENTITY
    # =========================================================================
    uid: str = ""
    title: str = ""
    ku_type: KuType = KuType.CURRICULUM
    user_uid: str | None = None
    parent_ku_uid: str | None = None
    domain: Domain = Domain.KNOWLEDGE
    created_by: str | None = None

    # =========================================================================
    # CONTENT
    # =========================================================================
    content: str | None = None
    summary: str = ""
    word_count: int = 0

    # =========================================================================
    # FILE (ASSIGNMENT submissions)
    # =========================================================================
    original_filename: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    file_type: str | None = None

    # =========================================================================
    # PROCESSING
    # =========================================================================
    status: KuStatus = KuStatus.DRAFT
    processor_type: ProcessorType | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    processing_error: str | None = None
    processed_content: str | None = None
    processed_file_path: str | None = None
    instructions: str | None = None

    # =========================================================================
    # FEEDBACK
    # =========================================================================
    feedback: str | None = None
    feedback_generated_at: datetime | None = None
    subject_uid: str | None = None

    # =========================================================================
    # LEARNING
    # =========================================================================
    complexity: KuComplexity = KuComplexity.MEDIUM
    learning_level: LearningLevel = LearningLevel.BEGINNER
    sel_category: SELCategory | None = None
    quality_score: float = 0.0
    estimated_time_minutes: int = 15
    difficulty_rating: float = 0.5
    semantic_links: list[str] = field(default_factory=list)

    # =========================================================================
    # SHARING
    # =========================================================================
    visibility: Visibility = Visibility.PRIVATE

    # =========================================================================
    # SUBSTANCE TRACKING
    # =========================================================================
    times_applied_in_tasks: int = 0
    times_practiced_in_events: int = 0
    times_built_into_habits: int = 0
    journal_reflections_count: int = 0
    choices_informed_count: int = 0

    last_applied_date: datetime | None = None
    last_practiced_date: datetime | None = None
    last_built_into_habit_date: datetime | None = None
    last_reflected_date: datetime | None = None
    last_choice_informed_date: datetime | None = None

    # =========================================================================
    # META
    # =========================================================================
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    # =========================================================================
    # FACTORY METHODS (per KuType)
    # =========================================================================

    @classmethod
    def create_curriculum(
        cls,
        title: str,
        domain: Domain,
        **kwargs: Any,
    ) -> "KuDTO":
        """
        Create a CURRICULUM Ku (admin-created shared knowledge).

        No user_uid — curriculum is shared content.
        Status defaults to COMPLETED, visibility to PUBLIC.
        """
        kwargs.pop("user_uid", None)  # Curriculum never has user_uid
        kwargs.setdefault("status", KuStatus.COMPLETED)
        kwargs.setdefault("visibility", Visibility.PUBLIC)
        return cls._create_ku_dto(
            ku_type=KuType.CURRICULUM,
            title=title,
            user_uid=None,
            domain=domain,
            **kwargs,
        )

    @classmethod
    def create_assignment(
        cls,
        user_uid: str,
        title: str,
        **kwargs: Any,
    ) -> "KuDTO":
        """
        Create an ASSIGNMENT Ku (student submission).

        Requires user_uid. Status defaults to DRAFT, visibility to PRIVATE.
        """
        return cls._create_ku_dto(
            ku_type=KuType.ASSIGNMENT,
            title=title,
            user_uid=user_uid,
            **kwargs,
        )

    @classmethod
    def create_ai_report(
        cls,
        user_uid: str,
        title: str,
        parent_ku_uid: str,
        **kwargs: Any,
    ) -> "KuDTO":
        """
        Create an AI_REPORT Ku (AI-derived from assignment).

        Requires user_uid and parent_ku_uid (the assignment it derives from).
        """
        return cls._create_ku_dto(
            ku_type=KuType.AI_REPORT,
            title=title,
            user_uid=user_uid,
            parent_ku_uid=parent_ku_uid,
            **kwargs,
        )

    @classmethod
    def create_feedback_report(
        cls,
        user_uid: str,
        title: str,
        parent_ku_uid: str,
        **kwargs: Any,
    ) -> "KuDTO":
        """
        Create a FEEDBACK_REPORT Ku (teacher feedback on assignment).

        Requires user_uid (teacher) and parent_ku_uid (the assignment reviewed).
        """
        return cls._create_ku_dto(
            ku_type=KuType.FEEDBACK_REPORT,
            title=title,
            user_uid=user_uid,
            parent_ku_uid=parent_ku_uid,
            **kwargs,
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update DTO fields from a dictionary (for update operations)."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(
            self,
            updates,
            allowed_fields={
                # Content
                "title",
                "content",
                "summary",
                "word_count",
                "domain",
                # File
                "original_filename",
                "file_path",
                "file_size",
                "file_type",
                # Processing
                "status",
                "processor_type",
                "processing_started_at",
                "processing_completed_at",
                "processing_error",
                "processed_content",
                "processed_file_path",
                "instructions",
                # Feedback
                "feedback",
                "feedback_generated_at",
                "subject_uid",
                # Learning
                "complexity",
                "learning_level",
                "sel_category",
                "quality_score",
                "estimated_time_minutes",
                "difficulty_rating",
                "semantic_links",
                # Sharing
                "visibility",
                # Substance tracking
                "times_applied_in_tasks",
                "times_practiced_in_events",
                "times_built_into_habits",
                "journal_reflections_count",
                "choices_informed_count",
                "last_applied_date",
                "last_practiced_date",
                "last_built_into_habit_date",
                "last_reflected_date",
                "last_choice_informed_date",
                # Meta
                "tags",
                "metadata",
            },
            enum_mappings={
                "ku_type": KuType,
                "status": KuStatus,
                "processor_type": ProcessorType,
                "domain": Domain,
                "complexity": KuComplexity,
                "learning_level": LearningLevel,
                "sel_category": SELCategory,
                "visibility": Visibility,
            },
        )

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        from core.models.dto_helpers import convert_datetimes_to_iso

        data = {
            # Identity
            "uid": self.uid,
            "title": self.title,
            "ku_type": get_enum_value(self.ku_type),
            "user_uid": self.user_uid,
            "parent_ku_uid": self.parent_ku_uid,
            "domain": get_enum_value(self.domain),
            "created_by": self.created_by,
            # Content
            "content": self.content,
            "summary": self.summary,
            "word_count": self.word_count,
            # File
            "original_filename": self.original_filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "file_type": self.file_type,
            # Processing
            "status": get_enum_value(self.status),
            "processor_type": get_enum_value(self.processor_type) if self.processor_type else None,
            "processing_started_at": self.processing_started_at,
            "processing_completed_at": self.processing_completed_at,
            "processing_error": self.processing_error,
            "processed_content": self.processed_content,
            "processed_file_path": self.processed_file_path,
            "instructions": self.instructions,
            # Feedback
            "feedback": self.feedback,
            "feedback_generated_at": self.feedback_generated_at,
            "subject_uid": self.subject_uid,
            # Learning
            "complexity": get_enum_value(self.complexity),
            "learning_level": get_enum_value(self.learning_level),
            "sel_category": get_enum_value(self.sel_category) if self.sel_category else None,
            "quality_score": self.quality_score,
            "estimated_time_minutes": self.estimated_time_minutes,
            "difficulty_rating": self.difficulty_rating,
            "semantic_links": list(self.semantic_links),
            # Sharing
            "visibility": get_enum_value(self.visibility),
            # Substance tracking
            "times_applied_in_tasks": self.times_applied_in_tasks,
            "times_practiced_in_events": self.times_practiced_in_events,
            "times_built_into_habits": self.times_built_into_habits,
            "journal_reflections_count": self.journal_reflections_count,
            "choices_informed_count": self.choices_informed_count,
            "last_applied_date": self.last_applied_date,
            "last_practiced_date": self.last_practiced_date,
            "last_built_into_habit_date": self.last_built_into_habit_date,
            "last_reflected_date": self.last_reflected_date,
            "last_choice_informed_date": self.last_choice_informed_date,
            # Meta
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata) if self.metadata else {},
        }

        convert_datetimes_to_iso(
            data,
            [
                "created_at",
                "updated_at",
                "processing_started_at",
                "processing_completed_at",
                "feedback_generated_at",
                "last_applied_date",
                "last_practiced_date",
                "last_built_into_habit_date",
                "last_reflected_date",
                "last_choice_informed_date",
            ],
        )

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KuDTO":
        """
        Create DTO from dictionary (from database).

        Infrastructure fields (embedding, embedding_version, etc.) are
        automatically filtered out by dto_from_dict.

        See: /docs/decisions/ADR-037-embedding-infrastructure-separation.md
        """
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "ku_type": KuType,
                "status": KuStatus,
                "processor_type": ProcessorType,
                "domain": Domain,
                "complexity": KuComplexity,
                "sel_category": SELCategory,
                "learning_level": LearningLevel,
                "visibility": Visibility,
            },
            datetime_fields=[
                "created_at",
                "updated_at",
                "processing_started_at",
                "processing_completed_at",
                "feedback_generated_at",
                "last_applied_date",
                "last_practiced_date",
                "last_built_into_habit_date",
                "last_reflected_date",
                "last_choice_informed_date",
            ],
            list_fields=["tags", "semantic_links"],
            dict_fields=["metadata"],
            deprecated_fields=[
                # Old KuDTO fields
                "prerequisites",
                "enables",
                "related_to",
                # Old Report fields
                "report_type",
                "journal_category",
                "journal_type",
                "content_type",
                "entry_date",
                "reading_time_minutes",
                "source_type",
                "source_file",
                "transcription_uid",
                "mood",
                "energy_level",
                "key_topics",
                "mentioned_people",
                "mentioned_places",
                "action_items",
                "project_uid",
            ],
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, KuDTO):
            return False
        return self.uid == other.uid
