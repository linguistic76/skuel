"""
Exercise Submission Handler
=============================

Listens for SubmissionCreated events with a fulfills_exercise_uid.
When present, calls process_exercise_submission() to create
FULFILLS_EXERCISE + SHARES_WITH relationships.

Formerly assignment_handler.py — renamed per of Ku hierarchy refactoring.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from core.events.submission_events import SubmissionCreated
from core.services.submissions.submissions_core_service import ProcessingOutcome
from core.utils.logging import get_logger

logger = get_logger("skuel.events.exercise_handler")

# Outcomes that indicate a genuine configuration problem the teacher should know about.
_WARN_OUTCOMES = {ProcessingOutcome.NO_TEACHER, ProcessingOutcome.NOT_IN_GROUP}


async def handle_exercise_submission(
    event: SubmissionCreated,
    reports_core_service: object,
) -> None:
    """
    Handle SubmissionCreated events that fulfill an exercise.

    When fulfills_exercise_uid is present, delegates to
    reports_core_service.process_exercise_submission() and logs the
    outcome at the appropriate level:
      PROCESSED      → info  (success)
      NOT_ASSIGNED   → debug (expected no-op for personal/assessment exercises)
      NOT_EXERCISE   → debug (exercise uid not found — probably a stale uid)
      NO_TEACHER     → warning (exercise has no owner; submission not routed)
      NOT_IN_GROUP   → warning (student not in the exercise's group)
      WRONG_STUDENT  → warning (RevisedExercise targets a different student)

    Args:
        event: The SubmissionCreated event
        reports_core_service: SubmissionsCoreService with process_exercise_submission()
    """
    if not event.fulfills_exercise_uid:
        logger.debug(
            f"Exercise submission skipped — no fulfills_exercise_uid: submission={event.submission_uid}"
        )
        return

    result = await reports_core_service.process_exercise_submission(  # type: ignore[attr-defined]
        submission_uid=event.submission_uid,
        exercise_uid=event.fulfills_exercise_uid,
    )

    if result.is_error:
        logger.error(
            f"process_exercise_submission error: submission={event.submission_uid} "
            f"exercise={event.fulfills_exercise_uid} error={result.error}"
        )
        return

    outcome = result.value
    ctx = f"submission={event.submission_uid} exercise={event.fulfills_exercise_uid}"

    if outcome == ProcessingOutcome.PROCESSED:
        logger.info(f"Exercise submission routed to teacher queue: {ctx}")
    elif outcome in _WARN_OUTCOMES:
        logger.warning(f"Exercise submission not routed [{outcome}]: {ctx}")
    else:
        # NOT_EXERCISE, NOT_ASSIGNED, WRONG_STUDENT — expected no-ops
        logger.debug(f"Exercise submission skipped [{outcome}]: {ctx}")
