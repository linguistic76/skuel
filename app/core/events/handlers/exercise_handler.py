"""
Exercise Submission Handler
=============================

Listens for ``UserEntryCreated`` events with a ``fulfills_exercise_uid``.
When present, calls ``UserEntryExerciseLinker.process_exercise_submission()``
to validate scope/group membership and stamp the revision-aware title. The
``FULFILLS_EXERCISE`` edge itself is already written atomically by
``UserEntryBackend.create_with_exercise_link`` at creation time.

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
See: /docs/decisions/ADR-054-user-entry-unified-hub.md
"""

from core.events.user_entry_events import UserEntryCreated
from core.services.user_entry.exercise_linker import ProcessingOutcome
from core.utils.logging import get_logger

logger = get_logger("skuel.events.exercise_handler")

# Outcomes that indicate a genuine configuration problem the teacher should know about.
_WARN_OUTCOMES = {ProcessingOutcome.NOT_IN_GROUP}


async def handle_exercise_submission(
    event: UserEntryCreated,
    exercise_linker: object,
) -> None:
    """Handle ``UserEntryCreated`` events that fulfill an exercise.

    When ``fulfills_exercise_uid`` is present, delegates to
    ``exercise_linker.process_exercise_submission()`` and logs the outcome:
      PROCESSED      → info  (success)
      NOT_ASSIGNED   → debug (expected no-op for personal/assessment exercises)
      NOT_EXERCISE   → debug (exercise uid not found — probably a stale uid)
      NOT_IN_GROUP   → warning (student not in the exercise's group)
      WRONG_STUDENT  → warning (RevisedExercise targets a different student)

    Args:
        event: The UserEntryCreated event
        exercise_linker: UserEntryExerciseLinker with process_exercise_submission()
    """
    if not event.fulfills_exercise_uid:
        logger.debug(
            f"Exercise submission skipped — no fulfills_exercise_uid: entry={event.entity_uid}"
        )
        return

    result = await exercise_linker.process_exercise_submission(  # type: ignore[attr-defined]
        entry_uid=event.entity_uid,
        exercise_uid=event.fulfills_exercise_uid,
    )

    if result.is_error:
        logger.error(
            f"process_exercise_submission error: entry={event.entity_uid} "
            f"exercise={event.fulfills_exercise_uid} error={result.expect_error()}"
        )
        return

    outcome = result.value
    ctx = f"entry={event.entity_uid} exercise={event.fulfills_exercise_uid}"

    if outcome == ProcessingOutcome.PROCESSED:
        logger.info(f"Exercise submission routed to teacher queue: {ctx}")
    elif outcome in _WARN_OUTCOMES:
        logger.warning(f"Exercise submission not routed [{outcome}]: {ctx}")
    else:
        # NOT_EXERCISE, NOT_ASSIGNED, WRONG_STUDENT — expected no-ops
        logger.debug(f"Exercise submission skipped [{outcome}]: {ctx}")
