"""
Report Enums - Single Source of Truth
======================================

Consolidated enums for the unified Report domain (February 2026).

Journal is now a ReportType. Journal-specific enums (JournalType, JournalCategory,
ContentType, ContentStatus) live here alongside ReportType, ReportStatus, ProcessorType.

Per One Path Forward: One definition, imported everywhere.
"""

from enum import Enum


class ReportType(str, Enum):
    """
    Type of report - determines processing pipeline and UI presentation.

    File submission types:
        TRANSCRIPT: Meeting notes, voice memos, document transcriptions
        ASSIGNMENT: Document processing (PDF, Word)
        IMAGE_ANALYSIS: Visual content analysis
        VIDEO_SUMMARY: Video content summarization

    Content types:
        JOURNAL: Personal reflection/writing entry (merged February 2026)
    """

    TRANSCRIPT = "transcript"
    ASSIGNMENT = "assignment"
    IMAGE_ANALYSIS = "image_analysis"
    VIDEO_SUMMARY = "video_summary"
    JOURNAL = "journal"
    PROGRESS = "progress"
    ASSESSMENT = "assessment"

    def get_display_name(self) -> str:
        """Get human-readable display name for UI."""
        return {
            ReportType.TRANSCRIPT: "Transcript",
            ReportType.ASSIGNMENT: "Assignment",
            ReportType.IMAGE_ANALYSIS: "Image Analysis",
            ReportType.VIDEO_SUMMARY: "Video Summary",
            ReportType.JOURNAL: "Journal",
            ReportType.PROGRESS: "Progress Report",
            ReportType.ASSESSMENT: "Teacher Assessment",
        }[self]

    def is_journal(self) -> bool:
        """Check if this is a journal-type report."""
        return self == ReportType.JOURNAL

    def is_progress(self) -> bool:
        """Check if this is a system-generated progress report."""
        return self == ReportType.PROGRESS

    def is_assessment(self) -> bool:
        """Check if this is a teacher assessment."""
        return self == ReportType.ASSESSMENT

    def is_system_generated(self) -> bool:
        """Check if this report type is system-generated (not user-submitted)."""
        return self == ReportType.PROGRESS

    def is_file_based(self) -> bool:
        """Check if this report type requires file upload."""
        return self not in {ReportType.JOURNAL, ReportType.PROGRESS, ReportType.ASSESSMENT}


class ReportStatus(str, Enum):
    """
    Processing status of report.

    DRAFT: Initial state for journals (content being written)
    SUBMITTED: File uploaded, not yet processed
    QUEUED: In processing queue
    PROCESSING: Currently being processed
    COMPLETED: Processing finished successfully
    FAILED: Processing error occurred
    MANUAL_REVIEW: Awaiting human review
    ARCHIVED: Soft-deleted/archived
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"
    REVISION_REQUESTED = "revision_requested"  # Teacher requests changes (ADR-040)
    ARCHIVED = "archived"

    def is_terminal(self) -> bool:
        """Check if this is a terminal (non-progressing) status."""
        return self in {
            ReportStatus.COMPLETED,
            ReportStatus.FAILED,
            ReportStatus.ARCHIVED,
        }


class ProjectScope(str, Enum):
    """
    Scope of a ReportProject.

    PERSONAL: User's own AI feedback template (default)
    ASSIGNED: Teacher-created, assigned to a group (ADR-040)
    """

    PERSONAL = "personal"
    ASSIGNED = "assigned"


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


class JournalType(str, Enum):
    """
    Journal retention tiers.

    Two-tier journal system:
    - VOICE (PJ1): Ephemeral voice journals, max 3 stored, audio source
    - CURATED (PJ2): Permanent curated text/markdown journals
    """

    VOICE = "voice"
    CURATED = "curated"

    def is_ephemeral(self) -> bool:
        """Check if this type has auto-cleanup (max retention limit)."""
        return self == JournalType.VOICE

    def max_retention_count(self) -> int | None:
        """
        Return max retention count for ephemeral types, None for permanent.

        VOICE journals have FIFO cleanup - only most recent 3 are kept.
        CURATED journals are permanent (no limit).
        """
        if self == JournalType.VOICE:
            return 3
        return None

    def get_display_name(self) -> str:
        """Get human-readable display name."""
        return {
            JournalType.VOICE: "Voice Journal",
            JournalType.CURATED: "Curated Journal",
        }[self]


class ContentType(Enum):
    """Types of content in the system."""

    JOURNAL = "journal"
    AUDIO_TRANSCRIPT = "audio_transcript"
    NOTE = "note"
    ARTICLE = "article"
    REFLECTION = "reflection"


class ContentStatus(Enum):
    """
    Status of content processing.

    Maps to ReportStatus for journal-type reports:
        DRAFT -> ReportStatus.DRAFT
        TRANSCRIBED -> ReportStatus.PROCESSING
        PROCESSED -> ReportStatus.COMPLETED
        PUBLISHED -> ReportStatus.COMPLETED (with visibility=PUBLIC)
        ARCHIVED -> ReportStatus.ARCHIVED
    """

    DRAFT = "draft"
    TRANSCRIBED = "transcribed"
    PROCESSED = "processed"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class JournalCategory(Enum):
    """Categories for journal entries."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    REFLECTION = "reflection"
    GRATITUDE = "gratitude"
    GOALS = "goals"
    IDEAS = "ideas"
    DREAMS = "dreams"
    HEALTH = "health"
    WORK = "work"
    PERSONAL = "personal"
    LEARNING = "learning"
    PROJECT = "project"
    OTHER = "other"
