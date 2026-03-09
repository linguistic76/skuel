"""
JournalReport - Report on a journal submission
=================================================

Frozen dataclass for journal reports (EntityType.JOURNAL_REPORT).

AI-generated report on a student's journal submission.
Created by the journal output generator after processing a journal entry.

Part of the journal learning loop:
    JournalSubmission → (AI processing) → JournalReport

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.report.journal_report_dto import JournalReportDTO

from core.models.enums.entity_enums import EntityType
from core.models.report.submission_report import SubmissionReport


@dataclass(frozen=True)
class JournalReport(SubmissionReport):
    """
    Immutable domain model for journal reports (EntityType.JOURNAL_REPORT).

    Inherits all fields from SubmissionReport. Zero extra fields.
    """

    def __post_init__(self) -> None:
        """Force entity_type=JOURNAL_REPORT, then delegate to SubmissionReport."""
        if self.entity_type != EntityType.JOURNAL_REPORT:
            object.__setattr__(self, "entity_type", EntityType.JOURNAL_REPORT)
        super().__post_init__()

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | JournalReportDTO") -> "JournalReport":  # type: ignore[override]
        """Create JournalReport from an EntityDTO or JournalReportDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "JournalReportDTO":  # type: ignore[override]
        """Convert to JournalReportDTO."""
        import dataclasses
        from typing import Any

        from core.models.report.journal_report_dto import JournalReportDTO

        dto_field_names = {f.name for f in dataclasses.fields(JournalReportDTO)}
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
        return JournalReportDTO(**kwargs)

    def __str__(self) -> str:
        return f"JournalReport(uid={self.uid}, title='{self.title}', subject={self.subject_uid})"

    def __repr__(self) -> str:
        return (
            f"JournalReport(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, subject_uid={self.subject_uid}, "
            f"processor_type={self.processor_type}, user_uid={self.user_uid})"
        )
