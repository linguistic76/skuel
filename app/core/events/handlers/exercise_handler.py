"""
Exercise Submission Handler
=============================

Listens for SubmissionCreated events with a fulfills_project_uid.
When present, calls process_exercise_submission() to create
FULFILLS_EXERCISE + SHARES_WITH relationships.

Formerly assignment_handler.py — renamed per of Ku hierarchy refactoring.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from core.events.submission_events import SubmissionCreated
from core.utils.logging import get_logger

logger = get_logger("skuel.events.exercise_handler")


async def handle_exercise_submission(
    event: SubmissionCreated,
    reports_core_service: object,
) -> None:
    """
    Handle SubmissionCreated events that fulfill an exercise.

    When fulfills_project_uid is present, delegates to
    reports_core_service.process_exercise_submission() which:
    1. Creates FULFILLS_EXERCISE relationship
    2. Auto-shares with teacher via SHARES_WITH
    3. Sets status to SUBMITTED if processor_type is HUMAN

    Args:
        event: The SubmissionCreated event
        reports_core_service: ReportsCoreService with process_exercise_submission()
    """
    if not event.fulfills_project_uid:
        return

    logger.info(
        f"Exercise submission detected: ku={event.submission_uid} "
        f"-> exercise={event.fulfills_project_uid}"
    )

    result = await reports_core_service.process_exercise_submission(  # type: ignore[attr-defined]
        ku_uid=event.submission_uid,
        exercise_uid=event.fulfills_project_uid,
    )

    if result.is_error:
        logger.error(
            f"Failed to process exercise submission: ku={event.submission_uid}, "
            f"exercise={event.fulfills_project_uid}, error={result.error}"
        )
    elif result.value:
        logger.info(
            f"Exercise submission processed: ku={event.submission_uid} "
            f"-> exercise={event.fulfills_project_uid}"
        )
