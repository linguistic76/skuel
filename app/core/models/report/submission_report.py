"""
SubmissionReport - Submission Report Domain Model
===================================================

Frozen dataclass for submission report entities (EntityType.SUBMISSION_REPORT).

Inherits all fields from Submission (Entity ~48 + 13 submission fields).
Adds 2 report-specific fields:
- report_content: str | None — the report text
- report_generated_at: datetime | None — when report was generated

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.report.submission_report_dto import SubmissionReportDTO

from core.models.enums.entity_enums import EntityType
from core.models.submissions.submission import Submission


@dataclass(frozen=True)
class SubmissionReport(Submission):
    """
    Immutable domain model for submission reports (EntityType.SUBMISSION_REPORT).

    Inherits all fields from Submission. Adds 2 report-specific fields.
    Uses subject_uid (from Submission) for "who this report is about".
    """

    def __post_init__(self) -> None:
        """Force entity_type=SUBMISSION_REPORT, then delegate to Submission."""
        if self.entity_type != EntityType.SUBMISSION_REPORT:
            object.__setattr__(self, "entity_type", EntityType.SUBMISSION_REPORT)
        super().__post_init__()

    # =========================================================================
    # REPORT-SPECIFIC FIELDS
    # =========================================================================
    report_content: str | None = None
    report_generated_at: datetime | None = None  # type: ignore[assignment]

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
