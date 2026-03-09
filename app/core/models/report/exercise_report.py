"""
ExerciseReport - Report on an exercise submission
====================================================

Frozen dataclass for exercise reports (EntityType.EXERCISE_REPORT).

Teacher or AI report on a student's exercise submission.
Part of the learning loop:
    Exercise → ExerciseSubmission → ExerciseReport → RevisedExercise → ...

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.report.exercise_report_dto import ExerciseReportDTO

from core.models.enums.entity_enums import EntityType
from core.models.report.submission_report import SubmissionReport


@dataclass(frozen=True)
class ExerciseReport(SubmissionReport):
    """
    Immutable domain model for exercise reports (EntityType.EXERCISE_REPORT).

    Inherits all fields from SubmissionReport. Zero extra fields.
    """

    def __post_init__(self) -> None:
        """Force entity_type=EXERCISE_REPORT, then delegate to SubmissionReport."""
        if self.entity_type != EntityType.EXERCISE_REPORT:
            object.__setattr__(self, "entity_type", EntityType.EXERCISE_REPORT)
        super().__post_init__()

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | ExerciseReportDTO") -> "ExerciseReport":  # type: ignore[override]
        """Create ExerciseReport from an EntityDTO or ExerciseReportDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "ExerciseReportDTO":  # type: ignore[override]
        """Convert to ExerciseReportDTO."""
        import dataclasses
        from typing import Any

        from core.models.report.exercise_report_dto import ExerciseReportDTO

        dto_field_names = {f.name for f in dataclasses.fields(ExerciseReportDTO)}
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
        return ExerciseReportDTO(**kwargs)

    def __str__(self) -> str:
        return f"ExerciseReport(uid={self.uid}, title='{self.title}', subject={self.subject_uid})"

    def __repr__(self) -> str:
        return (
            f"ExerciseReport(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, subject_uid={self.subject_uid}, "
            f"processor_type={self.processor_type}, user_uid={self.user_uid})"
        )
