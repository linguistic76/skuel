"""
Report Domain Model
====================

Core domain model for file submission and processing pipeline.

A Report represents a file submitted by a user for processing:
- Uploaded file metadata and storage location
- Processing status and processor type
- Processed output content and files
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from core.models.enums.metadata_enums import Visibility


class ReportType(str, Enum):
    """
    Type of report - determines processing pipeline.

    File submission types ONLY. Journal types moved to JournalType enum
    in journal_enums.py (January 2026 - Domain Separation).

    TRANSCRIPT: Meeting notes, voice memos, document transcriptions
    ASSIGNMENT: Document processing (PDF, Word)
    IMAGE_ANALYSIS: Visual content analysis
    VIDEO_SUMMARY: Video content summarization

    Note: For journal entries, use the Journal domain with JournalType enum.
    See: core/models/enums/journal_enums.py
    """

    TRANSCRIPT = "transcript"
    ASSIGNMENT = "assignment"
    IMAGE_ANALYSIS = "image_analysis"
    VIDEO_SUMMARY = "video_summary"

    def get_display_name(self) -> str:
        """Get human-readable display name for UI."""
        return {
            ReportType.TRANSCRIPT: "Transcript",
            ReportType.ASSIGNMENT: "Assignment",
            ReportType.IMAGE_ANALYSIS: "Image Analysis",
            ReportType.VIDEO_SUMMARY: "Video Summary",
        }[self]


class ReportStatus(str, Enum):
    """
    Processing status of report.

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
    Type of processor used for report.

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
class Report:
    """
    Report domain model (Tier 3 - frozen, immutable).

    Represents a file submitted for processing with full lifecycle tracking.

    Fields:
        uid: Unique identifier (e.g., "report_abc123")
        user_uid: User who submitted the report
        report_type: Type of report (transcript, assignment, etc.)
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
        created_at: When report was created
        updated_at: When report was last updated

        # Additional metadata
        metadata: Flexible JSON for processor-specific data
    """

    uid: str
    user_uid: str
    report_type: ReportType
    status: ReportStatus

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

    # Sharing
    visibility: Visibility = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Initialize mutable fields with proper defaults."""
        now = datetime.now()
        if self.created_at is None:
            object.__setattr__(self, "created_at", now)
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", now)
        if self.visibility is None:
            object.__setattr__(self, "visibility", Visibility.PRIVATE)

    @property
    def is_completed(self) -> bool:
        """Check if processing is complete"""
        return self.status == ReportStatus.COMPLETED

    @property
    def is_processing(self) -> bool:
        """Check if currently processing"""
        return self.status == ReportStatus.PROCESSING

    @property
    def is_failed(self) -> bool:
        """Check if processing failed"""
        return self.status == ReportStatus.FAILED

    @property
    def requires_manual_review(self) -> bool:
        """Check if report needs human review"""
        return self.status == ReportStatus.MANUAL_REVIEW

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

    def is_shareable(self) -> bool:
        """
        Check if report can be shared.

        Only completed reports can be shared to ensure quality control.
        Failed or processing reports should not be shared.
        """
        return self.status == ReportStatus.COMPLETED

    def can_view(self, user_uid: str, owner_uid: str, shared_user_uids: set[str]) -> bool:
        """
        Check if a user can view this report.

        Access is granted if:
        - User is the owner
        - Report is PUBLIC
        - Report is SHARED and user is in shared_user_uids

        Args:
            user_uid: User requesting access
            owner_uid: Report owner
            shared_user_uids: Set of user UIDs with SHARES_WITH relationship

        Returns:
            True if user can view, False otherwise
        """
        return (
            user_uid == owner_uid
            or self.visibility == Visibility.PUBLIC
            or (self.visibility == Visibility.SHARED and user_uid in shared_user_uids)
        )


@dataclass
class ReportDTO:
    """
    Report Data Transfer Object (Tier 2 - mutable).

    Used for transferring report data between layers.
    """

    uid: str
    user_uid: str
    report_type: str  # Enum value as string
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

    # Sharing
    visibility: str = "private"  # Visibility enum value as string


def report_pure_to_dto(report: Report) -> ReportDTO:
    """Convert Report (Tier 3) to ReportDTO (Tier 2)"""
    return ReportDTO(
        uid=report.uid,
        user_uid=report.user_uid,
        report_type=report.report_type.value,
        status=report.status.value,
        original_filename=report.original_filename,
        file_path=report.file_path,
        file_size=report.file_size,
        file_type=report.file_type,
        processor_type=report.processor_type.value,
        processing_started_at=report.processing_started_at,
        processing_completed_at=report.processing_completed_at,
        processing_error=report.processing_error,
        processed_content=report.processed_content,
        processed_file_path=report.processed_file_path,
        created_at=report.created_at,
        updated_at=report.updated_at,
        metadata=report.metadata,
        visibility=report.visibility.value,
    )


def report_dto_to_pure(dto: ReportDTO) -> Report:
    """Convert ReportDTO (Tier 2) to Report (Tier 3)"""
    return Report(
        uid=dto.uid,
        user_uid=dto.user_uid,
        report_type=ReportType(dto.report_type),
        status=ReportStatus(dto.status),
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
        visibility=Visibility(dto.visibility),
    )
