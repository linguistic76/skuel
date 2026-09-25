"""
Report Notification Handler
==============================

Creates Notification nodes when a teacher or an admin writes about a student's
work. Each handler rings the student:

  ReportSubmitted              → "New feedback on your submission"
  UserEntryApproved            → "Your submission was approved"
                                 + "You mastered N knowledge units!" when mastered_ku_count > 0
  UserEntryRevisionRequested   → "Revision requested on your submission"
  RevisedExerciseCreated       → "Revision instructions are ready"
  ActivityReportWritten        → "New activity report" (an admin's report on the
                                 student's activity — Submit & Share arc R10)

Every notification names the entity the bell opens (``source_type`` +
``source_uid``); the card resolves the page from those two, so a handler
never chooses a URL.

Event handlers are registered in bootstrap via functools.partial for dependency injection.

See: /docs/architecture/LEARNING_LOOP_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.events.learning_loop_events import (
    ActivityReportWritten,
    ReportSubmitted,
    RevisedExerciseCreated,
    UserEntryApproved,
    UserEntryRevisionRequested,
)
from core.models.enums.entity_enums import EntityType
from core.models.enums.notification_enums import NotificationType
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
        notification_type=NotificationType.FEEDBACK_RECEIVED,
        title="New feedback on your submission",
        message="Your teacher reviewed your submission and left feedback.",
        source_uid=event.report_uid,
        source_type=EntityType.ENTRY_REPORT,
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
        notification_type=NotificationType.SUBMISSION_APPROVED,
        title="Your submission was approved",
        message=message,
        source_uid=event.entity_uid,
        source_type=EntityType.USER_ENTRY,
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

    # The bell opens the EntryReport that carries the teacher's notes. Both
    # publishers (request_revision, request_revision_with_exercise) put its uid
    # in ``metadata["report_uid"]``; an event without one is a publisher bug,
    # and ringing with the entry's uid under an ENTRY_REPORT source would open
    # nothing — refuse loudly instead.
    report_uid = str((event.metadata or {}).get("report_uid") or "")
    if not report_uid:
        logger.error(
            f"UserEntryRevisionRequested for {event.entity_uid} carries no report_uid; "
            f"no notification created"
        )
        return

    result = await notification_service.create_notification(
        user_uid=UserUID(event.student_uid),
        notification_type=NotificationType.REVISION_REQUESTED,
        title="Revision requested on your submission",
        message="Your teacher has requested changes to your submission.",
        source_uid=report_uid,
        source_type=EntityType.ENTRY_REPORT,
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
        notification_type=NotificationType.REVISED_EXERCISE_CREATED,
        title="Revision instructions are ready",
        message=f"Your teacher created {revision_label} instructions based on your submission feedback.",
        source_uid=event.revised_exercise_uid,
        source_type=EntityType.REVISED_EXERCISE,
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


async def handle_activity_report_written(
    event: ActivityReportWritten,
    notification_service: NotificationOperations,
) -> None:
    """Ring the subject when an admin writes an activity report about them.

    The report is the subject's own (Submit & Share arc R11), so the bell opens
    ``/activity-reports/detail`` through the ACTIVITY_REPORT source type.
    """
    result = await notification_service.create_notification(
        user_uid=UserUID(event.subject_uid),
        notification_type=NotificationType.ACTIVITY_REPORT_RECEIVED,
        title="New activity report",
        message=f"An admin wrote a report on your activity for {event.time_period}.",
        source_uid=event.report_uid,
        source_type=EntityType.ACTIVITY_REPORT,
    )

    if result.is_error:
        logger.error(
            f"Failed to create activity report notification for user {event.subject_uid}: "
            f"{result.error}"
        )
    else:
        logger.info(
            f"Activity report notification created for user {event.subject_uid} "
            f"(report {event.report_uid}, written by {event.author_uid})"
        )
