"""
UserEntry Exercise Linker — ADR-054
===================================

Validates exercise-scope + group membership for a freshly created
``UserEntry``. The ``FULFILLS_EXERCISE`` edge, the turn-in snapshot
(``turn_in_exercise_uid`` / ``turn_in_exercise_title`` / ``turn_in_revision``)
and the title default are all written atomically by
``UserEntryBackend.create_with_exercise_link`` at creation time; this linker
runs post-hoc from the ``UserEntryCreated`` subscriber
(``core/events/handlers/exercise_handler.py``) only to surface configuration
problems. It never writes: the title is the student's (Submit & Share arc
PR 7 ruling) and the version lives on the edge and the snapshot.
"""

from __future__ import annotations

from core.models.enums.entity_enums import EntityType
from core.models.enums.user_entry_enums import ExerciseScope
from core.ports.user_entry_protocols import UserEntryOperations
from core.utils.logging import get_logger
from core.utils.neo4j_props import neo4j_str
from core.utils.result_simplified import Result


class ProcessingOutcome(str):
    """Outcome token returned by ``process_exercise_submission``.

    Expected no-ops (debug/info):
        NOT_EXERCISE — exercise_uid not found or wrong entity_type
        NOT_ASSIGNED — exercise scope is not ``assigned`` (personal/assessment)

    Configuration problems (warning):
        NOT_IN_GROUP  — student is not a member of the exercise's target group
        WRONG_STUDENT — RevisedExercise targets a different student

    Success:
        PROCESSED — validation passed
    """

    NOT_EXERCISE: str = "not_exercise"
    NOT_ASSIGNED: str = "not_assigned"
    NOT_IN_GROUP: str = "not_in_group"
    WRONG_STUDENT: str = "wrong_student"
    PROCESSED: str = "processed"


class UserEntryExerciseLinker:
    """Validates a ``UserEntry``'s exercise link after creation (scope + membership).

    Called by the ``UserEntryCreated`` subscriber. The backend is the
    ``UserEntryOperations`` protocol consumed by ``UserEntryService`` —
    ``get_exercise_context``, ``get_entry_owner`` and
    ``verify_student_group_membership`` come from the
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
        """Validate scope/membership post-link-creation; write nothing.

        The ``FULFILLS_EXERCISE`` edge, the snapshot and the title are
        already written by ``create_with_exercise_link``. This method only
        surfaces the configuration problems ``ProcessingOutcome`` names.
        """
        exercise_result = await self.backend.get_exercise_context(exercise_uid)
        if exercise_result.is_error:
            self.logger.error(f"Error querying exercise: {exercise_result.expect_error()}")
            return Result.ok(ProcessingOutcome.NOT_EXERCISE)

        records = exercise_result.value or []
        if not records:
            return Result.ok(ProcessingOutcome.NOT_EXERCISE)

        exercise_entity_type = records[0]["exercise_entity_type"]

        if exercise_entity_type == EntityType.REVISED_EXERCISE.value:
            re_student_uid = records[0]["student_uid"]

            submitter_result = await self.backend.get_entry_owner(entry_uid)
            if submitter_result.is_error:
                self.logger.error(f"Error querying submitter: {submitter_result.expect_error()}")
                return Result.ok(ProcessingOutcome.NOT_EXERCISE)

            submitter_records = submitter_result.value or []
            if not submitter_records:
                return Result.ok(ProcessingOutcome.NOT_EXERCISE)

            submitter_uid = submitter_records[0]["student_uid"]
            if submitter_uid != re_student_uid:
                return Result.ok(ProcessingOutcome.WRONG_STUDENT)
        else:
            scope = records[0]["scope"]
            if scope != ExerciseScope.ASSIGNED:
                return Result.ok(ProcessingOutcome.NOT_ASSIGNED)

            group_uid = neo4j_str(records[0], "group_uid", "")
            if group_uid:
                student_result = await self.backend.verify_student_group_membership(
                    entry_uid, group_uid
                )
                if student_result.is_error:
                    self.logger.error(
                        f"Error verifying student membership: {student_result.expect_error()}"
                    )
                    return Result.ok(ProcessingOutcome.NOT_IN_GROUP)

                student_records = student_result.value or []
                if student_records and not student_records[0]["member_of_group"]:
                    return Result.ok(ProcessingOutcome.NOT_IN_GROUP)

        return Result.ok(ProcessingOutcome.PROCESSED)


__all__ = ["ProcessingOutcome", "UserEntryExerciseLinker"]
