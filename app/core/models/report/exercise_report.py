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
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.report.exercise_report_dto import ExerciseReportDTO

from core.models.enums.entity_enums import EntityType, ProcessorType
from core.models.enums.learning_enums import AssessmentOutcome
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True, kw_only=True)
class ExerciseReport(UserOwnedEntity):
    """
    Immutable domain model for exercise reports (EntityType.EXERCISE_REPORT).

    Extends UserOwnedEntity with 6 report-specific fields.
    """

    def __post_init__(self) -> None:
        """Force entity_type=EXERCISE_REPORT, then delegate to UserOwnedEntity."""
        if self.entity_type != EntityType.EXERCISE_REPORT:
            object.__setattr__(self, "entity_type", EntityType.EXERCISE_REPORT)
        super().__post_init__()

    # =========================================================================
    # REPORT-SPECIFIC FIELDS
    # =========================================================================
    # LLM/teacher-generated analysis lives on ``processed_content`` (not the
    # inherited ``Entity.content`` field, which is reserved for user-drafted
    # text). Written by ``create_report_node`` as ``processed_content: $feedback``.
    processed_content: str | None = None
    report_generated_at: datetime | None = None
    # GRAPH-NATIVE: projected from the REPORT_FOR edge on read by
    # ExerciseReportBackend.get_by_uid / list_for_submission, not stored as a
    # Neo4j node property. create_report_node writes the REPORT_FOR relationship;
    # reads hydrate this field via `RETURN n{.*, subject_uid: sub.uid}`.
    subject_uid: str | None = None  # UID of the submission this report is about
    processor_type: ProcessorType | None = None  # HUMAN/LLM/AUTOMATIC
    assessment_outcome: AssessmentOutcome | None = None  # APPROVED/NEEDS_REVISION/AI_EVALUATED
    report_file_path: str | None = None  # Generated output file path
    assessment_score: float | None = None  # 0.0-1.0 score for ASSESSMENT-scope exercises

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
