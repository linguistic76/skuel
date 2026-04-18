"""
UserEntry Exercise Linker — ADR-054 Commit 6a
==============================================

Validates exercise-scope + group membership for a freshly created
``UserEntry`` and updates the entry's canonical title. The
``FULFILLS_EXERCISE`` edge is already written atomically by
``UserEntryBackend.create_with_exercise_link`` at creation time; this
linker runs post-hoc from the ``UserEntryCreated`` subscriber
(``core/events/handlers/exercise_handler.py``) to surface configuration
problems and stamp the revision-aware title.

Ported from ``submissions_core_service.process_exercise_submission`` with
one simplification: the legacy ``Submission.generate_exercise_title``
helper is replaced with ``f"{exercise_title} v{revision}"``.
"""

from __future__ import annotations

from core.models.enums.entity_enums import EntityType
from core.models.enums.user_entry_enums import ExerciseScope
from core.ports.user_entry_protocols import UserEntryOperations
from core.utils.logging import get_logger
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
        PROCESSED — validation passed, title updated
    """

    NOT_EXERCISE: str = "not_exercise"
    NOT_ASSIGNED: str = "not_assigned"
    NOT_IN_GROUP: str = "not_in_group"
    WRONG_STUDENT: str = "wrong_student"
    PROCESSED: str = "processed"


def _generate_exercise_title(exercise_title: str, revision: int) -> str:
    """Canonical title for an exercise submission (revision-aware)."""
    return f"{exercise_title} v{revision}"


class UserEntryExerciseLinker:
    """Validates + retitles a ``UserEntry`` after exercise-link creation.

    Called by the ``UserEntryCreated`` subscriber. The backend is the
    ``UserEntryOperations`` protocol consumed by ``UserEntryService`` —
    ``get_exercise_context``, ``get_entry_owner``,
    ``verify_student_group_membership``, and ``count_entries_for_exercise``
    come from the ``UserEntryLifecycleOperations`` + ``UserEntryCrudOperations``
    parents.
    """

    def __init__(self, backend: UserEntryOperations) -> None:
        self.backend = backend
        self.logger = get_logger("skuel.services.user_entry.exercise_linker")

    async def process_exercise_submission(
        self,
        entry_uid: str,
        exercise_uid: str,
    ) -> Result[str]:
        """Validate scope/membership + update title post-link-creation.

        The ``FULFILLS_EXERCISE`` edge is already written by
        ``create_with_exercise_link``. This method only performs the
        validation + title-update steps that the legacy submissions flow
        deferred to the event handler.
        """
        exercise_result = await self.backend.get_exercise_context(exercise_uid)
        if exercise_result.is_error:
            self.logger.error(f"Error querying exercise: {exercise_result.expect_error()}")
            return Result.ok(ProcessingOutcome.NOT_EXERCISE)

        records = exercise_result.value or []
        if not records:
            return Result.ok(ProcessingOutcome.NOT_EXERCISE)

        exercise_entity_type = records[0]["exercise_entity_type"]
        exercise_title = records[0].get("exercise_title") or ""
        _original_value = records[0].get("original_exercise_uid")
        original_exercise_uid: str | None = (
            str(_original_value) if _original_value is not None else None
        )
        count_exercise_uid = original_exercise_uid or exercise_uid

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

            group_uid = records[0]["group_uid"]
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

        if exercise_title:
            student_uid_result = await self.backend.get_entry_owner(entry_uid)
            if not student_uid_result.is_error:
                student_uid_records = student_uid_result.value or []
                if student_uid_records:
                    submitter_uid = student_uid_records[0]["student_uid"]

                    prior_count_result = await self.backend.count_entries_for_exercise(
                        submitter_uid, count_exercise_uid
                    )
                    prior_count = 0
                    if not prior_count_result.is_error:
                        prior_count = prior_count_result.value

                    new_title = _generate_exercise_title(
                        exercise_title=exercise_title,
                        revision=prior_count + 1,
                    )
                    await self.backend.update(
                        entry_uid,
                        {"title": new_title, "revision_number": prior_count + 1},
                    )
                    self.logger.info(f"Updated user entry title to: {new_title}")

        return Result.ok(ProcessingOutcome.PROCESSED)


__all__ = ["ProcessingOutcome", "UserEntryExerciseLinker"]
