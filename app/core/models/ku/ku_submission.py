"""
SubmissionKu - Content Processing Domain Model (Intermediate Base)
===================================================================

Frozen dataclass for all content-processing entities:
KuType.SUBMISSION, KuType.JOURNAL, KuType.AI_REPORT, KuType.FEEDBACK_REPORT.

Inherits ~48 common fields from KuBase. Adds 13 submission-specific fields:
- File (4): original_filename, file_path, file_size, file_type
- Processing (8): processor_type, timestamps, error, content, instructions, max_retention
- Subject (1): subject_uid — who this report is about

Submission-specific methods: get_processing_duration, get_summary.

Leaf subclasses (JournalKu, AiReportKu, FeedbackKu) inherit from SubmissionKu
and force their specific ku_type. FeedbackKu adds 2 extra fields.

See: /.claude/plans/ku-decomposition-domain-types.md (Phase 8)
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO

from core.models.enums.ku_enums import KuType, ProcessorType
from core.models.ku.ku_base import KuBase

_SUBMISSION_KU_TYPES = frozenset({
    KuType.SUBMISSION,
    KuType.JOURNAL,
    KuType.AI_REPORT,
    KuType.FEEDBACK_REPORT,
})


@dataclass(frozen=True)
class SubmissionKu(KuBase):
    """
    Immutable domain model for content-processing entities.

    Accepts 4 ku_types: SUBMISSION, JOURNAL, AI_REPORT, FEEDBACK_REPORT.

    Inherits ~48 common fields from KuBase (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 13 submission-specific fields for file storage, content processing,
    and subject tracking.
    """

    def __post_init__(self) -> None:
        """Validate ku_type is a submission type, then delegate to KuBase."""
        if self.ku_type not in _SUBMISSION_KU_TYPES:
            object.__setattr__(self, "ku_type", KuType.SUBMISSION)
        super().__post_init__()

    # =========================================================================
    # FILE (uploads)
    # =========================================================================
    original_filename: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    file_type: str | None = None  # MIME type (e.g., "audio/mpeg")

    # =========================================================================
    # PROCESSING
    # =========================================================================
    processor_type: ProcessorType | None = None
    processing_started_at: datetime | None = None  # type: ignore[assignment]
    processing_completed_at: datetime | None = None  # type: ignore[assignment]
    processing_error: str | None = None
    processed_content: str | None = None
    processed_file_path: str | None = None
    instructions: str | None = None  # LLM processing instructions
    max_retention: int | None = None  # FIFO cleanup limit (None = permanent)

    # =========================================================================
    # SUBJECT
    # =========================================================================
    subject_uid: str | None = None  # Who this report is about

    # =========================================================================
    # SUBMISSION-SPECIFIC METHODS
    # =========================================================================

    def get_processing_duration(self) -> float | None:
        """Get processing duration in seconds, or None if not applicable."""
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

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of content (body text or processed content)."""
        text = self.content or self.processed_content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def explain_existence(self) -> str:
        """Explain why this submission exists."""
        return self.description or self.summary or f"{self.ku_type.value}: {self.title}"

    # =========================================================================
    # CONVERSION (generic — uses KuBase._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "SubmissionKu":
        """Create SubmissionKu from a KuDTO."""
        return cls._from_dto(dto)

    def __str__(self) -> str:
        return f"SubmissionKu(uid={self.uid}, type={self.ku_type.value}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"SubmissionKu(uid='{self.uid}', ku_type={self.ku_type}, "
            f"title='{self.title}', status={self.status}, "
            f"processor_type={self.processor_type}, user_uid={self.user_uid})"
        )
