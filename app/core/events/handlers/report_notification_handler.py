"""
Report Notification Handler
==============================

Creates Notification nodes when teachers provide feedback or request revisions.

Teacher actions produce student notifications:

  ReportSubmitted              → "New feedback on your submission"
  UserEntryApproved            → "Your submission was approved"
                                 + "You mastered N knowledge units!" when mastered_ku_count > 0
  UserEntryRevisionRequested   → "Revision requested on your submission"
  RevisedExerciseCreated       → "Revision instructions are ready"

Event handlers are registered in bootstrap via functools.partial for dependency injection.

See: /docs/architecture/LEARNING_LOOP_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.events.learning_loop_events import (
    ReportSubmitted,
    RevisedExerciseCreated,
    UserEntryApproved,
    UserEntryRevisionRequested,
)
from core.models.type_hints import UserUID
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.ports.notification_protocols import NotificationOperations

logger = get_logger("skuel.events.report_notification_handler")


async def handle_report_submitted(
    event: ReportSubmitted,
    notification_service: NotificationOperations,
) -> None:
    """Create notification when teacher submits written feedback on a user entry."""
    if not event.student_uid:
        logger.debug(
            f"No student_uid on ReportSubmitted for {event.submission_uid}, skipping notification"
        )
        return

    result = await notification_service.create_notification(
        user_uid=UserUID(event.student_uid),
        notification_type="feedback_received",
        title="New feedback on your submission",
        message="Your teacher reviewed your submission and left feedback.",
        source_uid=event.report_uid,
        source_type="entry_report",
    )

    if result.is_error:
        logger.error(
            f"Failed to create report notification for student {event.student_uid}: {result.error}"
        )
    else:
        logger.info(
            f"Feedback notification created for student {event.student_uid} "
            f"on submission {event.submission_uid}"
        )


async def handle_submission_approved(
    event: UserEntryApproved,
    notification_service: NotificationOperations,
) -> None:
    """Create notification when teacher approves a user entry."""
    if not event.student_uid:
        logger.debug(
            f"No student_uid on UserEntryApproved for {event.entity_uid}, skipping notification"
        )
        return

    if event.mastered_ku_count > 0:
        message = (
            f"Your teacher approved your work. "
            f"You mastered {event.mastered_ku_count} knowledge unit(s)!"
        )
    else:
        message = "Your teacher approved your work on this submission."

    result = await notification_service.create_notification(
        user_uid=UserUID(event.student_uid),
        notification_type="submission_approved",
        title="Your submission was approved",
        message=message,
        source_uid=event.entity_uid,
        source_type="user_entry",
    )

    if result.is_error:
        logger.error(
            f"Failed to create approval notification for student {event.student_uid}: "
            f"{result.error}"
        )
    else:
        logger.info(
            f"Approval notification created for student {event.student_uid} "
            f"on entry {event.entity_uid}"
            + (f" ({event.mastered_ku_count} KUs mastered)" if event.mastered_ku_count else "")
        )


async def handle_revision_requested(
    event: UserEntryRevisionRequested,
    notification_service: NotificationOperations,
) -> None:
    """Create notification when teacher requests revision on a user entry."""
    if not event.student_uid:
        logger.debug(
            f"No student_uid on UserEntryRevisionRequested for {event.entity_uid}, "
            f"skipping notification"
        )
        return

    report_uid = ""
    if event.metadata:
        report_uid = event.metadata.get("report_uid", "")

    source_uid = report_uid or event.entity_uid

    result = await notification_service.create_notification(
        user_uid=UserUID(event.student_uid),
        notification_type="revision_requested",
        title="Revision requested on your submission",
        message="Your teacher has requested changes to your submission.",
        source_uid=source_uid,
        source_type="entry_report",
    )

    if result.is_error:
        logger.error(
            f"Failed to create revision notification for student {event.student_uid}: "
            f"{result.error}"
        )
    else:
        logger.info(
            f"Revision notification created for student {event.student_uid} "
            f"on entry {event.entity_uid}"
        )


async def handle_revised_exercise_created(
    event: RevisedExerciseCreated,
    notification_service: NotificationOperations,
) -> None:
    """Create notification when teacher creates revision instructions for a student."""
    if not event.student_uid:
        logger.debug(
            f"No student_uid on RevisedExerciseCreated for {event.revised_exercise_uid}, "
            f"skipping notification"
        )
        return

    revision_label = (
        f"revision #{event.revision_number}" if event.revision_number > 1 else "revision"
    )

    result = await notification_service.create_notification(
        user_uid=UserUID(event.student_uid),
        notification_type="revised_exercise_created",
        title="Revision instructions are ready",
        message=f"Your teacher created {revision_label} instructions based on your submission feedback.",
        source_uid=event.revised_exercise_uid,
        source_type="revised_exercise",
    )

    if result.is_error:
        logger.error(
            f"Failed to create revised exercise notification for student {event.student_uid}: "
            f"{result.error}"
        )
    else:
        logger.info(
            f"Revised exercise notification created for student {event.student_uid} "
            f"({revision_label}, exercise {event.revised_exercise_uid})"
        )
