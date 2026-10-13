"""
UserEntry Exercise Linker — ADR-054
===================================

Validates a freshly created ``UserEntry``'s exercise link. The
``FULFILLS_EXERCISE`` edge, the turn-in snapshot (``turn_in_exercise_uid`` /
``turn_in_exercise_title`` / ``turn_in_revision``) and the title default are all
written atomically by ``UserEntryBackend.create_with_exercise_link`` at creation
time; this linker runs post-hoc from the ``UserEntryCreated`` subscriber
(``core/events/handlers/exercise_handler.py``) only to surface a configuration
problem: a turn-in against a RevisedExercise addressed to another student. It
never writes: the title is the student's and the version lives on the edge and
the snapshot.
"""

from __future__ import annotations

from core.models.enums.entity_enums import EntityType
from core.ports.user_entry_protocols import UserEntryOperations
from core.utils.logging import get_logger
from core.utils.result_simplified import Result


class ProcessingOutcome(str):
    """Outcome token returned by ``process_exercise_submission``.

    Expected no-op (debug):
        NOT_EXERCISE — exercise_uid not found or wrong entity_type

    Configuration problem (warning):
        WRONG_STUDENT — RevisedExercise targets a different student

    Success:
        PROCESSED — validation passed
    """

    NOT_EXERCISE: str = "not_exercise"
    WRONG_STUDENT: str = "wrong_student"
    PROCESSED: str = "processed"


class UserEntryExerciseLinker:
    """Validates a ``UserEntry``'s exercise link after creation.

    Called by the ``UserEntryCreated`` subscriber. The backend is the
    ``UserEntryOperations`` protocol consumed by ``UserEntryService`` —
    ``get_exercise_context`` and ``get_entry_owner`` come from the
    ``UserEntryLifecycleOperations`` + ``UserEntryCrudOperations`` parents.
    """

    def __init__(self, backend: UserEntryOperations) -> None:
        self.backend = backend
        self.logger = get_logger("skuel.services.user_entry.exercise_linker")

    async def process_exercise_submission(
        self,
        entry_uid: str,
        exercise_uid: str,
    ) -> Result[str]:
        """Validate the link post-creation; write nothing.

        The ``FULFILLS_EXERCISE`` edge, the snapshot and the title are
        already written by ``create_with_exercise_link``. This method only
        surfaces the configuration problem ``ProcessingOutcome`` names.
        """
        exercise_result = await self.backend.get_exercise_context(exercise_uid)
        if exercise_result.is_error:
            self.logger.error(f"Error querying exercise: {exercise_result.expect_error()}")
            return Result.ok(ProcessingOutcome.NOT_EXERCISE)

        records = exercise_result.value or []
        if not records:
            return Result.ok(ProcessingOutcome.NOT_EXERCISE)

        if records[0]["exercise_entity_type"] != EntityType.REVISED_EXERCISE.value:
            return Result.ok(ProcessingOutcome.PROCESSED)

        re_student_uid = records[0]["student_uid"]
        submitter_result = await self.backend.get_entry_owner(entry_uid)
        if submitter_result.is_error:
            self.logger.error(f"Error querying submitter: {submitter_result.expect_error()}")
            return Result.ok(ProcessingOutcome.NOT_EXERCISE)

        submitter_records = submitter_result.value or []
        if not submitter_records:
            return Result.ok(ProcessingOutcome.NOT_EXERCISE)

        if submitter_records[0]["student_uid"] != re_student_uid:
            return Result.ok(ProcessingOutcome.WRONG_STUDENT)
        return Result.ok(ProcessingOutcome.PROCESSED)


__all__ = ["ProcessingOutcome", "UserEntryExerciseLinker"]
