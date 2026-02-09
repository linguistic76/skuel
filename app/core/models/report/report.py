"""
Report Domain Model
====================

Core domain model for all user-submitted content:
- File submissions (transcripts, assignments, image analysis, video summary)
- Journal entries (voice, curated text) — merged February 2026

A Report represents any content submitted by a user for processing or reflection.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from core.models.enums.metadata_enums import Visibility
from core.models.enums.report_enums import (
    ContentType,
    JournalCategory,
    JournalType,
    ProcessorType,
    ReportStatus,
    ReportType,
)


@dataclass(frozen=True)
class Report:
    """
    Report domain model (Tier 3 - frozen, immutable).

    Represents any user-submitted content with full lifecycle tracking.
    Journals are reports with report_type=JOURNAL.

    Fields:
        uid: Unique identifier (e.g., "report_abc123")
        user_uid: User who submitted the report
        report_type: Type of report (transcript, assignment, journal, etc.)
        status: Current processing status

        # File metadata (optional — journals don't have files)
        original_filename: Name of uploaded file
        file_path: Storage location (local or cloud)
        file_size: Size in bytes
        file_type: MIME type (e.g., "audio/mpeg")

        # Processing metadata
        processor_type: Type of processor (LLM, human, hybrid)

        # Journal fields (None for non-journal types)
        title: Journal entry title
        content: Journal body text
        journal_type: VOICE or CURATED
        content_type: JOURNAL, AUDIO_TRANSCRIPT, etc.
        journal_category: Category for organization
        entry_date: Date of journal entry

        # Sharing
        visibility: PRIVATE, SHARED, or PUBLIC
    """

    uid: str
    user_uid: str
    report_type: ReportType
    status: ReportStatus

    # Subject (who the report is about — defaults to user_uid)
    subject_uid: str | None = None

    # File metadata (optional — journals don't have files)
    original_filename: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    file_type: str | None = None

    # Processing metadata
    processor_type: ProcessorType | None = None
    processing_started_at: datetime | None = None  # type: ignore[assignment]
    processing_completed_at: datetime | None = None  # type: ignore[assignment]
    processing_error: str | None = None

    # Output
    processed_content: str | None = None
    processed_file_path: str | None = None

    # --- Journal fields (None for non-journal types) ---

    # Content
    title: str | None = None
    content: str | None = None
    tags: list[str] = None  # type: ignore[assignment]
    journal_category: JournalCategory | None = None

    # Journal classification
    journal_type: JournalType | None = None
    content_type: ContentType | None = None
    entry_date: date | None = None

    # Content metrics
    word_count: int = 0
    reading_time_minutes: float = 0.0

    # Source info (transcribed audio)
    source_type: str | None = None
    source_file: str | None = None
    transcription_uid: str | None = None

    # Extracted insights
    mood: str | None = None
    energy_level: int | None = None
    key_topics: list[str] = None  # type: ignore[assignment]
    mentioned_people: list[str] = None  # type: ignore[assignment]
    mentioned_places: list[str] = None  # type: ignore[assignment]
    action_items: list[str] = None  # type: ignore[assignment]

    # AI Feedback (via ReportProject)
    project_uid: str | None = None
    feedback: str | None = None
    feedback_generated_at: datetime | None = None  # type: ignore[assignment]

    created_by: str | None = None

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
        if self.tags is None:
            object.__setattr__(self, "tags", [])
        if self.key_topics is None:
            object.__setattr__(self, "key_topics", [])
        if self.mentioned_people is None:
            object.__setattr__(self, "mentioned_people", [])
        if self.mentioned_places is None:
            object.__setattr__(self, "mentioned_places", [])
        if self.action_items is None:
            object.__setattr__(self, "action_items", [])

        # Default subject_uid for PROGRESS and ASSESSMENT types
        if self.subject_uid is None and self.report_type in (
            ReportType.PROGRESS,
            ReportType.ASSESSMENT,
        ):
            object.__setattr__(self, "subject_uid", self.user_uid)

        # Compute word_count and reading_time for journals
        if self.report_type == ReportType.JOURNAL and self.content:
            if self.word_count == 0:
                wc = len(self.content.split())
                object.__setattr__(self, "word_count", wc)
            if self.reading_time_minutes == 0.0 and self.word_count > 0:
                object.__setattr__(self, "reading_time_minutes", self.word_count / 225)

        # Default entry_date for journals
        if self.report_type == ReportType.JOURNAL and self.entry_date is None:
            object.__setattr__(self, "entry_date", date.today())

    # ========================================================================
    # REPORT STATUS PROPERTIES
    # ========================================================================

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
        """
        if not self.processing_started_at or not self.processing_completed_at:
            return None

        delta = self.processing_completed_at - self.processing_started_at

        if isinstance(delta, timedelta):
            return delta.total_seconds()

        try:
            return float(delta.seconds)
        except AttributeError:
            try:
                return float(delta)
            except (TypeError, ValueError):
                return None

    # ========================================================================
    # SHARING
    # ========================================================================

    def is_shareable(self) -> bool:
        """
        Check if report can be shared.

        Only completed reports can be shared to ensure quality control.
        """
        return self.status == ReportStatus.COMPLETED

    def can_view(self, user_uid: str, owner_uid: str, shared_user_uids: set[str]) -> bool:
        """
        Check if a user can view this report.

        Access is granted if:
        - User is the owner
        - Report is PUBLIC
        - Report is SHARED and user is in shared_user_uids
        """
        return (
            user_uid == owner_uid
            or self.visibility == Visibility.PUBLIC
            or (self.visibility == Visibility.SHARED and user_uid in shared_user_uids)
        )

    # ========================================================================
    # JOURNAL DOMAIN METHODS
    # ========================================================================

    @property
    def is_progress_report(self) -> bool:
        """Check if this is a system-generated progress report."""
        return self.report_type == ReportType.PROGRESS

    @property
    def is_assessment(self) -> bool:
        """Check if this is a teacher assessment."""
        return self.report_type == ReportType.ASSESSMENT

    @property
    def is_about_self(self) -> bool:
        """Check if this report is about the user who created it."""
        return self.subject_uid is None or self.subject_uid == self.user_uid

    @property
    def is_journal(self) -> bool:
        """Check if this is a journal-type report."""
        return self.report_type == ReportType.JOURNAL

    @property
    def is_voice_journal(self) -> bool:
        """Check if this is a voice (ephemeral) journal."""
        return self.is_journal and self.journal_type == JournalType.VOICE

    @property
    def is_curated_journal(self) -> bool:
        """Check if this is a curated (permanent) journal."""
        return self.is_journal and self.journal_type == JournalType.CURATED

    def has_insights(self) -> bool:
        """Check if insights have been extracted from journal content."""
        return bool(self.mood or self.energy_level or self.key_topics or self.action_items)

    def is_recent(self, days: int = 7) -> bool:
        """Check if journal entry is recent."""
        if not self.entry_date:
            return False
        delta = date.today() - self.entry_date
        return delta.days <= days

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of content (journal body or processed content)."""
        text = self.content or self.processed_content or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."


@dataclass
class ReportDTO:
    """
    Report Data Transfer Object (Tier 2 - mutable).

    Used for transferring report data between layers.
    All enum values stored as strings.
    """

    uid: str
    user_uid: str
    report_type: str
    status: str

    # Subject
    subject_uid: str | None = None

    # File metadata (optional)
    original_filename: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    file_type: str | None = None

    # Processing metadata
    processor_type: str | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    processing_error: str | None = None

    # Output
    processed_content: str | None = None
    processed_file_path: str | None = None

    # Journal fields
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    journal_category: str | None = None
    journal_type: str | None = None
    content_type: str | None = None
    entry_date: date | None = None
    word_count: int = 0
    reading_time_minutes: float = 0.0

    # Source info
    source_type: str | None = None
    source_file: str | None = None
    transcription_uid: str | None = None

    # Extracted insights
    mood: str | None = None
    energy_level: int | None = None
    key_topics: list[str] | None = None
    mentioned_people: list[str] | None = None
    mentioned_places: list[str] | None = None
    action_items: list[str] | None = None

    # AI Feedback
    project_uid: str | None = None
    feedback: str | None = None
    feedback_generated_at: datetime | None = None

    created_by: str | None = None

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Metadata
    metadata: dict[str, Any] | None = None

    # Sharing
    visibility: str = "private"


def report_pure_to_dto(report: Report) -> ReportDTO:
    """Convert Report (Tier 3) to ReportDTO (Tier 2)"""
    return ReportDTO(
        uid=report.uid,
        user_uid=report.user_uid,
        report_type=report.report_type.value,
        status=report.status.value,
        subject_uid=report.subject_uid,
        original_filename=report.original_filename,
        file_path=report.file_path,
        file_size=report.file_size,
        file_type=report.file_type,
        processor_type=report.processor_type.value if report.processor_type else None,
        processing_started_at=report.processing_started_at,
        processing_completed_at=report.processing_completed_at,
        processing_error=report.processing_error,
        processed_content=report.processed_content,
        processed_file_path=report.processed_file_path,
        title=report.title,
        content=report.content,
        tags=list(report.tags) if report.tags else None,
        journal_category=report.journal_category.value if report.journal_category else None,
        journal_type=report.journal_type.value if report.journal_type else None,
        content_type=report.content_type.value if report.content_type else None,
        entry_date=report.entry_date,
        word_count=report.word_count,
        reading_time_minutes=report.reading_time_minutes,
        source_type=report.source_type,
        source_file=report.source_file,
        transcription_uid=report.transcription_uid,
        mood=report.mood,
        energy_level=report.energy_level,
        key_topics=list(report.key_topics) if report.key_topics else None,
        mentioned_people=list(report.mentioned_people) if report.mentioned_people else None,
        mentioned_places=list(report.mentioned_places) if report.mentioned_places else None,
        action_items=list(report.action_items) if report.action_items else None,
        project_uid=report.project_uid,
        feedback=report.feedback,
        feedback_generated_at=report.feedback_generated_at,
        created_by=report.created_by,
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
        subject_uid=dto.subject_uid,
        original_filename=dto.original_filename,
        file_path=dto.file_path,
        file_size=dto.file_size,
        file_type=dto.file_type,
        processor_type=ProcessorType(dto.processor_type) if dto.processor_type else None,
        processing_started_at=dto.processing_started_at,
        processing_completed_at=dto.processing_completed_at,
        processing_error=dto.processing_error,
        processed_content=dto.processed_content,
        processed_file_path=dto.processed_file_path,
        title=dto.title,
        content=dto.content,
        tags=dto.tags,
        journal_category=JournalCategory(dto.journal_category) if dto.journal_category else None,
        journal_type=JournalType(dto.journal_type) if dto.journal_type else None,
        content_type=ContentType(dto.content_type) if dto.content_type else None,
        entry_date=dto.entry_date,
        word_count=dto.word_count,
        reading_time_minutes=dto.reading_time_minutes,
        source_type=dto.source_type,
        source_file=dto.source_file,
        transcription_uid=dto.transcription_uid,
        mood=dto.mood,
        energy_level=dto.energy_level,
        key_topics=dto.key_topics,
        mentioned_people=dto.mentioned_people,
        mentioned_places=dto.mentioned_places,
        action_items=dto.action_items,
        project_uid=dto.project_uid,
        feedback=dto.feedback,
        feedback_generated_at=dto.feedback_generated_at,
        created_by=dto.created_by,
        created_at=dto.created_at or datetime.now(),
        updated_at=dto.updated_at or datetime.now(),
        metadata=dto.metadata,
        visibility=Visibility(dto.visibility),
    )
