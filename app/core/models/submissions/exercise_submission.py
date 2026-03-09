"""
ExerciseSubmission - Student work submitted against an Exercise
================================================================

Frozen dataclass for exercise submissions (EntityType.EXERCISE_SUBMISSION).

Inherits all fields from Submission (Entity ~48 + 13 submission fields).
Zero extra fields — exercise-specific metadata lives in the metadata dict.

Learning loop role:
    Exercise (shared template) → student submits → ExerciseSubmission (user-owned)
                                                    └─ FULFILLS_EXERCISE → Exercise
                                                    └─ SHARES_WITH → teacher

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.submissions.exercise_submission_dto import ExerciseSubmissionDTO

from core.models.enums.entity_enums import EntityType
from core.models.submissions.submission import Submission


@dataclass(frozen=True)
class ExerciseSubmission(Submission):
    """
    Immutable domain model for exercise submissions (EntityType.EXERCISE_SUBMISSION).

    Inherits all fields from Submission. Zero extra fields.
    """

    def __post_init__(self) -> None:
        """Force entity_type=EXERCISE_SUBMISSION, then delegate to Submission."""
        if self.entity_type != EntityType.EXERCISE_SUBMISSION:
            object.__setattr__(self, "entity_type", EntityType.EXERCISE_SUBMISSION)
        super().__post_init__()

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | ExerciseSubmissionDTO") -> "ExerciseSubmission":  # type: ignore[override]
        """Create ExerciseSubmission from an EntityDTO or ExerciseSubmissionDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "ExerciseSubmissionDTO":  # type: ignore[override]
        """Convert to ExerciseSubmissionDTO."""
        import dataclasses
        from typing import Any

        from core.models.submissions.exercise_submission_dto import ExerciseSubmissionDTO

        dto_field_names = {f.name for f in dataclasses.fields(ExerciseSubmissionDTO)}
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
        return ExerciseSubmissionDTO(**kwargs)

    def __str__(self) -> str:
        return f"ExerciseSubmission(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"ExerciseSubmission(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, user_uid={self.user_uid})"
        )
