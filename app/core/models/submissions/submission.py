"""
Submission - Content Processing Domain Model (Intermediate Base)
===================================================================

Frozen dataclass base for content-processing entities with file/artifact semantics.
Accepted entity types: SUBMISSION, JOURNAL, SUBMISSION_REPORT.

Note: ACTIVITY_REPORT (EntityType.ACTIVITY_REPORT) does NOT inherit from Submission.
ActivityReport responds to aggregate activity patterns (no file fields), and inherits
from UserOwnedEntity directly.

Role in the Educational Loop
------------------------------
A Submission (EntityType.SUBMISSION) is the user's work product in response
to an Exercise. It is the user-owned half of the core loop:

    Exercise (shared template) → user submits → Submission (user-owned)
                                                 └─ FULFILLS_EXERCISE → Exercise
                                                 └─ SHARES_WITH → teacher

The Submission is created by and belongs to the student. The teacher receives
access only via the SHARES_WITH relationship created at submission time.

The three leaf types that share this base:
    SUBMISSION      → Student's file upload / text submitted against an Exercise
    JOURNAL         → Voice or text journal entry (user's own reflections)
    SUBMISSION_REPORT → Teacher's or AI's feedback on a Submission (teacher-owned)

Fields
-------
- File (4): original_filename, file_path, file_size, file_type
- Processing (8): processor_type, timestamps, error, processed_content,
                  instructions, max_retention
- Subject (1): subject_uid — who this report is about (student, for feedback)

Leaf subclasses (Journal, SubmissionReport) inherit from Submission and force their
specific entity_type. SubmissionReport adds 2 extra fields.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.submissions.submission_dto import SubmissionDTO

from core.models.enums.entity_enums import EntityType, ProcessorType
from core.models.user_owned_entity import UserOwnedEntity

_SUBMISSION_KU_TYPES = frozenset(
    {
        EntityType.SUBMISSION,
        EntityType.JOURNAL,
        EntityType.SUBMISSION_REPORT,
        # AI_FEEDBACK intentionally excluded: ActivityReport inherits UserOwnedEntity directly
    }
)


@dataclass(frozen=True)
class Submission(UserOwnedEntity):
    """
    Immutable domain model for content-processing entities.

    Accepts 3 ku_types: SUBMISSION, JOURNAL, SUBMISSION_REPORT.
    (ACTIVITY_REPORT uses ActivityReport(UserOwnedEntity) — no file fields.)

    Inherits common fields from UserOwnedEntity (identity, content, status,
    sharing, meta, embedding, user_uid, priority).

    Adds 13 submission-specific fields for file storage, content processing,
    and subject tracking.
    """

    def __post_init__(self) -> None:
        """Validate entity_type is a submission type, then delegate to UserOwnedEntity."""
        if self.entity_type not in _SUBMISSION_KU_TYPES:
            object.__setattr__(self, "entity_type", EntityType.SUBMISSION)
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
    # TITLE GENERATION
    # =========================================================================

    @classmethod
    def generate_exercise_title(
        cls,
        exercise_title: str,
        user_uid: str,
        revision_number: int = 1,
        revision_date: date | None = None,
    ) -> str:
        """Auto-generate the canonical exercise submission title.

        Format: {Exercise Title} — {user_id}
        Revision: {Exercise Title} — {user_id} #{revision_number}, {Mar 02}

        Examples:
            Meditation Fundamentals — mike
            Meditation Fundamentals — mike #2, Mar 02
        """
        user_id = user_uid.removeprefix("user_")
        base = f"{exercise_title} \u2014 {user_id}"
        if revision_number > 1:
            date_str = (revision_date or date.today()).strftime("%b %d")
            return f"{base} #{revision_number}, {date_str}"
        return base

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
        return self.description or self.summary or f"{self.entity_type.value}: {self.title}"

    # =========================================================================
    # CONVERSION (generic — uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | SubmissionDTO") -> "Submission":
        """Create Submission from an EntityDTO or SubmissionDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "SubmissionDTO":  # type: ignore[override]
        """Convert Submission to domain-specific SubmissionDTO."""
        import dataclasses
        from typing import Any

        from core.models.submissions.submission_dto import SubmissionDTO

        dto_field_names = {f.name for f in dataclasses.fields(SubmissionDTO)}
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            if f.name.startswith("_"):
                continue
            if f.name not in dto_field_names:
                continue
            value = getattr(self, f.name)
            if isinstance(value, tuple):
                value = list(value)
            kwargs[f.name] = value
        return SubmissionDTO(**kwargs)

    def __str__(self) -> str:
        return f"Submission(uid={self.uid}, type={self.entity_type.value}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"Submission(uid='{self.uid}', entity_type={self.entity_type}, "
            f"title='{self.title}', status={self.status}, "
            f"processor_type={self.processor_type}, user_uid={self.user_uid})"
        )
