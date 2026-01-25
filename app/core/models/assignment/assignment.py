"""
Assignment Domain Model
=======================

Core domain model for file submission and processing pipeline.

An Assignment represents a file submitted by a user for processing:
- Uploaded file metadata and storage location
- Processing status and processor type
- Processed output content and files
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class AssignmentType(str, Enum):
    """
    Type of assignment - determines processing pipeline.

    File submission types ONLY. Journal types moved to JournalType enum
    in journal_enums.py (January 2026 - Domain Separation).

    TRANSCRIPT: Meeting notes, voice memos, document transcriptions
    REPORT: Document processing (PDF, Word)
    IMAGE_ANALYSIS: Visual content analysis
    VIDEO_SUMMARY: Video content summarization

    Note: For journal entries, use the Journal domain with JournalType enum.
    See: core/models/enums/journal_enums.py
    """

    TRANSCRIPT = "transcript"
    REPORT = "report"
    IMAGE_ANALYSIS = "image_analysis"
    VIDEO_SUMMARY = "video_summary"

    def get_display_name(self) -> str:
        """Get human-readable display name for UI."""
        return {
            AssignmentType.TRANSCRIPT: "Transcript",
            AssignmentType.REPORT: "Report",
            AssignmentType.IMAGE_ANALYSIS: "Image Analysis",
            AssignmentType.VIDEO_SUMMARY: "Video Summary",
        }[self]


class AssignmentStatus(str, Enum):
    """
    Processing status of assignment.

    SUBMITTED: File uploaded, not yet processed
    QUEUED: In processing queue
    PROCESSING: Currently being processed
    COMPLETED: Processing finished successfully
    FAILED: Processing error occurred
    MANUAL_REVIEW: Awaiting human review
    """

    SUBMITTED = "submitted"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class ProcessorType(str, Enum):
    """
    Type of processor used for assignment.

    LLM: AI/LLM processing (OpenAI, Anthropic)
    HUMAN: Manual human review
    HYBRID: LLM + human review
    AUTOMATIC: System-determined processor
    """

    LLM = "llm"
    HUMAN = "human"
    HYBRID = "hybrid"
    AUTOMATIC = "automatic"


@dataclass(frozen=True)
class Assignment:
    """
    Assignment domain model (Tier 3 - frozen, immutable).

    Represents a file submitted for processing with full lifecycle tracking.

    Fields:
        uid: Unique identifier (e.g., "assignment.abc123")
        user_uid: User who submitted the assignment
        assignment_type: Type of assignment (journal, transcript, etc.)
        status: Current processing status

        # File metadata
        original_filename: Name of uploaded file
        file_path: Storage location (local or cloud)
        file_size: Size in bytes
        file_type: MIME type (e.g., "audio/mpeg")

        # Processing metadata
        processor_type: Type of processor (LLM, human, hybrid)
        processing_started_at: When processing began
        processing_completed_at: When processing finished
        processing_error: Error message if failed

        # Output
        processed_content: Text content (formatted journal, transcript, etc.)
        processed_file_path: Path to processed file if applicable

        # Timestamps
        created_at: When assignment was created
        updated_at: When assignment was last updated

        # Additional metadata
        metadata: Flexible JSON for processor-specific data
    """

    uid: str
    user_uid: str
    assignment_type: AssignmentType
    status: AssignmentStatus

    # File metadata
    original_filename: str
    file_path: str
    file_size: int
    file_type: str

    # Processing metadata
    processor_type: ProcessorType
    processing_started_at: datetime | None = None  # type: ignore[assignment]
    processing_completed_at: datetime | None = None  # type: ignore[assignment]
    processing_error: str | None = None

    # Output
    processed_content: str | None = None
    processed_file_path: str | None = None

    # Timestamps
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]

    # Metadata
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Initialize mutable fields with proper defaults."""
        now = datetime.now()
        if self.created_at is None:
            object.__setattr__(self, "created_at", now)
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", now)

    @property
    def is_completed(self) -> bool:
        """Check if processing is complete"""
        return self.status == AssignmentStatus.COMPLETED

    @property
    def is_processing(self) -> bool:
        """Check if currently processing"""
        return self.status == AssignmentStatus.PROCESSING

    @property
    def is_failed(self) -> bool:
        """Check if processing failed"""
        return self.status == AssignmentStatus.FAILED

    @property
    def requires_manual_review(self) -> bool:
        """Check if assignment needs human review"""
        return self.status == AssignmentStatus.MANUAL_REVIEW

    def get_processing_duration(self) -> float | None:
        """
        Get processing duration in seconds.

        Returns None if processing hasn't started or completed.

        Note: This method handles both Python timedelta and Neo4j Duration objects.
        Ideally, the adapter layer should convert Neo4j types to Python types,
        but this provides defensive handling at the domain boundary.
        """
        if not self.processing_started_at or not self.processing_completed_at:
            return None

        delta = self.processing_completed_at - self.processing_started_at

        # Handle Python timedelta (standard case)
        if isinstance(delta, timedelta):
            return delta.total_seconds()

        # Handle Neo4j Duration object (should be converted at adapter layer)
        # Check for 'seconds' attribute without hasattr to satisfy linter
        try:
            # Neo4j Duration has .seconds, .nanoseconds attributes
            return float(delta.seconds)
        except AttributeError:
            # Fallback: attempt numeric conversion
            try:
                return float(delta)
            except (TypeError, ValueError):
                return None


@dataclass
class AssignmentDTO:
    """
    Assignment Data Transfer Object (Tier 2 - mutable).

    Used for transferring assignment data between layers.
    """

    uid: str
    user_uid: str
    assignment_type: str  # Enum value as string
    status: str  # Enum value as string

    # File metadata
    original_filename: str
    file_path: str
    file_size: int
    file_type: str

    # Processing metadata
    processor_type: str  # Enum value as string
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    processing_error: str | None = None

    # Output
    processed_content: str | None = None
    processed_file_path: str | None = None

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Metadata
    metadata: dict[str, Any] | None = None


def assignment_pure_to_dto(assignment: Assignment) -> AssignmentDTO:
    """Convert Assignment (Tier 3) to AssignmentDTO (Tier 2)"""
    return AssignmentDTO(
        uid=assignment.uid,
        user_uid=assignment.user_uid,
        assignment_type=assignment.assignment_type.value,
        status=assignment.status.value,
        original_filename=assignment.original_filename,
        file_path=assignment.file_path,
        file_size=assignment.file_size,
        file_type=assignment.file_type,
        processor_type=assignment.processor_type.value,
        processing_started_at=assignment.processing_started_at,
        processing_completed_at=assignment.processing_completed_at,
        processing_error=assignment.processing_error,
        processed_content=assignment.processed_content,
        processed_file_path=assignment.processed_file_path,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
        metadata=assignment.metadata,
    )


def assignment_dto_to_pure(dto: AssignmentDTO) -> Assignment:
    """Convert AssignmentDTO (Tier 2) to Assignment (Tier 3)"""
    return Assignment(
        uid=dto.uid,
        user_uid=dto.user_uid,
        assignment_type=AssignmentType(dto.assignment_type),
        status=AssignmentStatus(dto.status),
        original_filename=dto.original_filename,
        file_path=dto.file_path,
        file_size=dto.file_size,
        file_type=dto.file_type,
        processor_type=ProcessorType(dto.processor_type),
        processing_started_at=dto.processing_started_at,
        processing_completed_at=dto.processing_completed_at,
        processing_error=dto.processing_error,
        processed_content=dto.processed_content,
        processed_file_path=dto.processed_file_path,
        created_at=dto.created_at or datetime.now(),
        updated_at=dto.updated_at or datetime.now(),
        metadata=dto.metadata,
    )
