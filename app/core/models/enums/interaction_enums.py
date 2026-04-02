"""
Interaction Enums — User Interaction Contract
==============================================

Enums for the Interaction entity type (EntityType.INTERACTION):
the 22nd entity in SKUEL, representing a situated learning-loop event.

See: /docs/decisions/ADR-051-user-interaction-contract.md (pending)
"""

from enum import StrEnum


class InteractionType(StrEnum):
    """
    Type of learning-loop interaction being recorded.

    Only EXERCISE_SUBMISSION is implemented in Phase 1.
    KU_VIEW, PATH_STEP_COMPLETION, and FORM_SUBMISSION are reserved
    enum values that document the intended extension points — they do
    not require implementation until needed.
    """

    EXERCISE_SUBMISSION = "exercise_submission"
    # Reserved (Phase 2+):
    KU_VIEW = "ku_view"
    PATH_STEP_COMPLETION = "path_step_completion"
    FORM_SUBMISSION = "form_submission"


class InteractionResult(StrEnum):
    """
    Result status of the interaction after it was processed.

    PENDING:             Interaction recorded, result not yet known.
    REPORT_GENERATED:    An ExerciseReport was auto-generated.
    SHARED_WITH_TEACHER: Submission was shared with a teacher for review.
    COMPLETED:           Interaction fully processed with no further action needed.
    FAILED:              Processing failed (error recorded on the submission).
    """

    PENDING = "pending"
    REPORT_GENERATED = "report_generated"
    SHARED_WITH_TEACHER = "shared_with_teacher"
    COMPLETED = "completed"
    FAILED = "failed"
