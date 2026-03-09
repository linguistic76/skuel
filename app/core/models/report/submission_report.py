"""
SubmissionReport - Base Report Domain Model
=============================================

Frozen dataclass base for reports about submissions.

Extends UserOwnedEntity directly (NOT Submission — reports don't have file fields).
Report-specific fields: report_content, report_generated_at, subject_uid,
processor_type, report_file_path.

Leaf subclasses:
    ExerciseReport(SubmissionReport)  → EXERCISE_REPORT — report on exercise submission
    JournalReport(SubmissionReport)   → JOURNAL_REPORT — report on journal submission

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.report.submission_report_dto import SubmissionReportDTO

from core.models.enums.entity_enums import EntityType, ProcessorType
from core.models.user_owned_entity import UserOwnedEntity

_SUBMISSION_REPORT_TYPES = frozenset(
    {
        EntityType.EXERCISE_REPORT,
        EntityType.JOURNAL_REPORT,
        # Deprecated alias — kept during migration
        EntityType.SUBMISSION_REPORT,
    }
)


@dataclass(frozen=True)
class SubmissionReport(UserOwnedEntity):
    """
    Immutable domain model base for submission reports.

    Extends UserOwnedEntity (NOT Submission — no file/processing fields).
    Adds 5 report-specific fields.
    """

    def __post_init__(self) -> None:
        """Validate entity_type is a report type, then delegate to UserOwnedEntity."""
        if self.entity_type not in _SUBMISSION_REPORT_TYPES:
            object.__setattr__(self, "entity_type", EntityType.EXERCISE_REPORT)
        super().__post_init__()

    # =========================================================================
    # REPORT-SPECIFIC FIELDS
    # =========================================================================
    report_content: str | None = None
    report_generated_at: datetime | None = None  # type: ignore[assignment]
    subject_uid: str | None = None  # Who/what this report is about
    processor_type: ProcessorType | None = None  # HUMAN/LLM/AUTOMATIC
    report_file_path: str | None = None  # Generated output file path

    # =========================================================================
    # CONVERSION (generic — uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | SubmissionReportDTO") -> "SubmissionReport":  # type: ignore[override]
        """Create SubmissionReport from an EntityDTO or SubmissionReportDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "SubmissionReportDTO":  # type: ignore[override]
        """Convert SubmissionReport to domain-specific SubmissionReportDTO."""
        import dataclasses
        from typing import Any

        from core.models.report.submission_report_dto import SubmissionReportDTO

        dto_field_names = {f.name for f in dataclasses.fields(SubmissionReportDTO)}
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
        return SubmissionReportDTO(**kwargs)

    def __str__(self) -> str:
        return f"SubmissionReport(uid={self.uid}, title='{self.title}', subject={self.subject_uid})"

    def __repr__(self) -> str:
        return (
            f"SubmissionReport(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, subject_uid={self.subject_uid}, "
            f"report_content={'yes' if self.report_content else 'no'}, "
            f"user_uid={self.user_uid})"
        )
