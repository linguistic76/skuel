"""EntryShared → the recipient's ``shared_with_you`` bell (Submit & Share arc R10)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events.handlers.share_notification_handler import handle_entry_shared
from core.events.user_entry_events import EntryShared
from core.models.enums.entity_enums import EntityType
from core.models.enums.notification_enums import NotificationType
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def notification_service():
    service = MagicMock()
    service.create_notification = AsyncMock(return_value=Result.ok("notif_1"))
    return service


@pytest.mark.asyncio
async def test_the_recipient_is_rung_and_the_bell_opens_the_entry(notification_service):
    event = EntryShared(
        entity_uid="ue_1", owner_uid="user_owner", recipient_uid="user_peer", title="My essay"
    )

    await handle_entry_shared(event, notification_service=notification_service)

    notification_service.create_notification.assert_awaited_once_with(
        user_uid="user_peer",
        notification_type=NotificationType.SHARED_WITH_YOU,
        title="Shared with you",
        message="'My essay' was shared with you.",
        source_uid="ue_1",
        source_type=EntityType.USER_ENTRY,
    )


@pytest.mark.asyncio
async def test_a_failed_write_is_logged_not_raised(notification_service):
    notification_service.create_notification = AsyncMock(
        return_value=Result.fail(Errors.database(operation="create_notification", message="down"))
    )
    event = EntryShared(entity_uid="ue_1", owner_uid="user_owner", recipient_uid="user_peer")

    await handle_entry_shared(event, notification_service=notification_service)  # no raise
