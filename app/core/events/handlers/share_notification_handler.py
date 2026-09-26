"""
Share Notification Handler
==========================

Rings a person when someone shares their work with them (Submit & Share arc
R10):

  EntryShared → "Shared with you" — the bell opens ``/gradebook/{entry_uid}``,
                where the recipient sees the R6 card.

The event is published only for a share link this call created, so a
re-share rings nobody twice; a group share publishes nothing (group-share
notifications are future work, R10).

See: /docs/decisions/ADR-088-submit-and-share.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.events.user_entry_events import EntryShared
from core.models.enums.entity_enums import EntityType
from core.models.enums.notification_enums import NotificationType
from core.models.type_hints import UserUID
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.ports.notification_protocols import NotificationOperations

logger = get_logger("skuel.events.share_notification_handler")


async def handle_entry_shared(
    event: EntryShared,
    notification_service: NotificationOperations,
) -> None:
    """Ring the recipient of a new person share."""
    title = event.title or "an entry"
    result = await notification_service.create_notification(
        user_uid=UserUID(event.recipient_uid),
        notification_type=NotificationType.SHARED_WITH_YOU,
        title="Shared with you",
        message=f"'{title}' was shared with you.",
        source_uid=event.entity_uid,
        source_type=EntityType.USER_ENTRY,
    )
    if result.is_error:
        logger.error(
            f"Failed to create shared-with-you notification for user {event.recipient_uid}: "
            f"{result.error}"
        )
    else:
        logger.info(
            f"Shared-with-you notification created for user {event.recipient_uid} "
            f"(entry {event.entity_uid}, shared by {event.owner_uid})"
        )


__all__ = ["handle_entry_shared"]
