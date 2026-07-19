"""
Interaction Enums — User Interaction Contract
==============================================

Enums for the Interaction entity type (EntityType.INTERACTION):
the 22nd entity in SKUEL, representing a situated learning-loop event.

See: /docs/decisions/ADR-051-user-interaction-contract.md
"""

from __future__ import annotations

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
    Result status of the interaction as the report pipeline progresses.

    Forward-only lifecycle (ADR-051 Phase 2), in pipeline order:

    PENDING:             Interaction recorded, result not yet known.
    SHARED_WITH_TEACHER: Submission was shared with a teacher for review.
    REPORT_GENERATED:    An EntryReport (teacher or AI) was created for the entry.
    COMPLETED:           Teacher approved the entry — terminal.
    FAILED:              Pipeline processing failed before a report existed — terminal.

    Transitions are validated by ``allowed_from()``; a stale event can never
    move a record backwards (e.g. REPORT_GENERATED never demotes to
    SHARED_WITH_TEACHER).
    """

    PENDING = "pending"
    SHARED_WITH_TEACHER = "shared_with_teacher"
    REPORT_GENERATED = "report_generated"
    COMPLETED = "completed"
    FAILED = "failed"

    def allowed_from(self) -> tuple[InteractionResult, ...]:
        """Statuses a record may hold for a transition INTO this status to apply.

        Empty for PENDING — it is the birth status, never a transition target.
        FAILED only applies pre-report: once feedback exists, a later pipeline
        error no longer erases that outcome.
        """
        transitions: dict[InteractionResult, tuple[InteractionResult, ...]] = {
            InteractionResult.PENDING: (),
            InteractionResult.SHARED_WITH_TEACHER: (InteractionResult.PENDING,),
            InteractionResult.REPORT_GENERATED: (
                InteractionResult.PENDING,
                InteractionResult.SHARED_WITH_TEACHER,
            ),
            InteractionResult.COMPLETED: (
                InteractionResult.PENDING,
                InteractionResult.SHARED_WITH_TEACHER,
                InteractionResult.REPORT_GENERATED,
            ),
            InteractionResult.FAILED: (
                InteractionResult.PENDING,
                InteractionResult.SHARED_WITH_TEACHER,
            ),
        }
        return transitions[self]

    def is_terminal(self) -> bool:
        """True when no further transition can leave this status."""
        return self in (InteractionResult.COMPLETED, InteractionResult.FAILED)
