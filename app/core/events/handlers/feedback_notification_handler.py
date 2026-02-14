"""
Feedback Notification Handler
==============================

Creates Notification nodes when teachers provide feedback or request revisions.

Event handlers are registered in bootstrap via functools.partial for dependency injection.

See: /docs/architecture/SUBMISSION_FEEDBACK_LOOP.md
"""

from core.events.report_events import ReportReviewed, ReportRevisionRequested
from core.utils.logging import get_logger

logger = get_logger("skuel.events.feedback_notification_handler")


async def handle_report_reviewed(
    event: ReportReviewed,
    notification_service: object,
) -> None:
    """
    Create notification when teacher provides feedback on a submission.

    Args:
        event: The ReportReviewed event (contains report_uid, teacher_uid, student_uid)
        notification_service: NotificationService instance (injected via functools.partial)
    """
    if not event.student_uid:
        logger.debug(f"No student_uid on ReportReviewed for {event.report_uid}, skipping notification")
        return

    feedback_uid = ""
    if event.metadata:
        feedback_uid = event.metadata.get("feedback_uid", "")

    source_uid = feedback_uid or event.report_uid

    result = await notification_service.create_notification(  # type: ignore[attr-defined]
        user_uid=event.student_uid,
        notification_type="feedback_received",
        title="New feedback on your submission",
        message="Your teacher reviewed your submission and provided feedback.",
        source_uid=source_uid,
        source_type="feedback_report",
    )

    if result.is_error:
        logger.error(
            f"Failed to create feedback notification for student {event.student_uid}: "
            f"{result.error}"
        )
    else:
        logger.info(
            f"Feedback notification created for student {event.student_uid} "
            f"on submission {event.report_uid}"
        )


async def handle_revision_requested(
    event: ReportRevisionRequested,
    notification_service: object,
) -> None:
    """
    Create notification when teacher requests revision on a submission.

    Args:
        event: The ReportRevisionRequested event
        notification_service: NotificationService instance (injected via functools.partial)
    """
    if not event.student_uid:
        logger.debug(
            f"No student_uid on ReportRevisionRequested for {event.report_uid}, "
            f"skipping notification"
        )
        return

    feedback_uid = ""
    if event.metadata:
        feedback_uid = event.metadata.get("feedback_uid", "")

    source_uid = feedback_uid or event.report_uid

    result = await notification_service.create_notification(  # type: ignore[attr-defined]
        user_uid=event.student_uid,
        notification_type="revision_requested",
        title="Revision requested on your submission",
        message="Your teacher has requested changes to your submission.",
        source_uid=source_uid,
        source_type="feedback_report",
    )

    if result.is_error:
        logger.error(
            f"Failed to create revision notification for student {event.student_uid}: "
            f"{result.error}"
        )
    else:
        logger.info(
            f"Revision notification created for student {event.student_uid} "
            f"on submission {event.report_uid}"
        )
