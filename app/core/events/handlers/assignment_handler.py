"""
Assignment Submission Handler
==============================

Listens for SubmissionCreated events with a fulfills_project_uid.
When present, calls process_assignment_submission() to create
FULFILLS_PROJECT + SHARES_WITH relationships.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from core.events.submission_events import SubmissionCreated
from core.utils.logging import get_logger

logger = get_logger("skuel.events.assignment_handler")


async def handle_assignment_submission(
    event: SubmissionCreated,
    reports_core_service: object,
) -> None:
    """
    Handle SubmissionCreated events that fulfill an assignment.

    When fulfills_project_uid is present, delegates to
    reports_core_service.process_assignment_submission() which:
    1. Creates FULFILLS_PROJECT relationship
    2. Auto-shares with teacher via SHARES_WITH
    3. Sets status to SUBMITTED if processor_type is HUMAN

    Args:
        event: The SubmissionCreated event
        reports_core_service: KuCoreService with process_assignment_submission()
    """
    if not event.fulfills_project_uid:
        return

    logger.info(
        f"Assignment submission detected: ku={event.submission_uid} -> project={event.fulfills_project_uid}"
    )

    result = await reports_core_service.process_assignment_submission(  # type: ignore[attr-defined]
        ku_uid=event.submission_uid,
        project_uid=event.fulfills_project_uid,
    )

    if result.is_error:
        logger.error(
            f"Failed to process assignment submission: ku={event.submission_uid}, "
            f"project={event.fulfills_project_uid}, error={result.error}"
        )
    elif result.value:
        logger.info(
            f"Assignment submission processed: ku={event.submission_uid} -> project={event.fulfills_project_uid}"
        )
