"""
Submission Notification Handler
===============================

Rings a teacher when a student submits work for their feedback (Submit &
Share arc R10):

  UserEntryCreated (with ``submitted_group_uids``) → "Submission for review"
  — the bell opens ``/teaching/review/{entry_uid}``, the ``SUBMISSION_FOR_REVIEW``
  card override.

The event carries only the groups whose ``SUBMITTED_TO_GROUP`` that creation
wrote (the created subset), so a re-sync that finds the request standing
rings nobody. The recipients are the owners of those groups
(``get_owner_uids_batch`` — the ``OWNS`` edge unioned with the ``owner_uid``
/ ``user_uid`` spellings, undeduplicated), collected into ONE set across
every group and minus the submitter: one submission rings each teacher once,
however many of the targeted groups they own.

See: /docs/decisions/ADR-088-submit-and-share.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.events.user_entry_events import UserEntryCreated
from core.models.enums.entity_enums import EntityType
from core.models.enums.notification_enums import NotificationType
from core.models.type_hints import UserUID
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.ports.base_protocols import RelationshipCrudOperations
    from core.ports.notification_protocols import NotificationOperations

logger = get_logger("skuel.events.submission_notification_handler")


def unique_recipients(owners_by_group: dict[str, list[str]], submitter_uid: str) -> list[str]:
    """One recipient per owning teacher across every targeted group, the submitter excluded.

    ``get_owner_uids_batch`` does not deduplicate (a group carries both its
    ``owner_uid`` and its ``OWNS`` edge), and one teacher may own several of
    the targeted groups; first-seen order is kept so the bells are written
    in a stable order.
    """
    seen: dict[str, None] = {}
    for owners in owners_by_group.values():
        for owner_uid in owners:
            if owner_uid != submitter_uid:
                seen.setdefault(owner_uid, None)
    return list(seen)


async def handle_submission_for_review(
    event: UserEntryCreated,
    notification_service: NotificationOperations,
    backend: RelationshipCrudOperations,
) -> None:
    """Ring every owning teacher of the groups a new feedback request reached."""
    if not event.submitted_group_uids:
        return

    owners_result = await backend.get_owner_uids_batch(list(event.submitted_group_uids))
    if owners_result.is_error:
        logger.error(
            f"Teacher bell skipped for entry {event.entity_uid}: could not resolve the owners "
            f"of {list(event.submitted_group_uids)}: {owners_result.expect_error()}"
        )
        return

    recipients = unique_recipients(owners_result.value, event.user_uid)
    if not recipients:
        logger.warning(
            f"Teacher bell skipped for entry {event.entity_uid}: the submitted groups "
            f"{list(event.submitted_group_uids)} have no owner but the submitter"
        )
        return

    title = event.title or "an entry"
    for recipient_uid in recipients:
        result = await notification_service.create_notification(
            user_uid=UserUID(recipient_uid),
            notification_type=NotificationType.SUBMISSION_FOR_REVIEW,
            title="Submission for review",
            message=f"'{title}' was submitted for your feedback.",
            source_uid=event.entity_uid,
            source_type=EntityType.USER_ENTRY,
        )
        if result.is_error:
            logger.error(
                f"Failed to create submission-for-review notification for teacher "
                f"{recipient_uid} (entry {event.entity_uid}): {result.error}"
            )
        else:
            logger.info(
                f"Submission-for-review notification created for teacher {recipient_uid} "
                f"(entry {event.entity_uid}, submitted by {event.user_uid})"
            )


__all__ = ["handle_submission_for_review", "unique_recipients"]
