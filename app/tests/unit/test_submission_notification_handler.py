"""UserEntryCreated → the owning teachers' ``submission_for_review`` bell (Submit & Share arc R10)."""

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from core.events.handlers.submission_notification_handler import (
    handle_submission_for_review,
    unique_recipients,
)
from core.events.user_entry_events import UserEntryCreated
from core.models.enums.entity_enums import EntityType
from core.models.enums.notification_enums import NotificationType
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def notification_service():
    service = MagicMock()
    service.create_notification = AsyncMock(return_value=Result.ok("notif_1"))
    return service


def _backend(owners: dict[str, list[str]] | None = None):
    backend = MagicMock()
    backend.get_owner_uids_batch = AsyncMock(return_value=Result.ok(owners or {}))
    return backend


def _event(groups: tuple[str, ...] = ("g_class",), title: str | None = "My essay"):
    return UserEntryCreated(
        entity_uid="ue_1",
        user_uid="user_student",
        pipeline="teacher_review",
        title=title,
        submitted_group_uids=groups,
    )


def test_one_recipient_per_teacher_across_groups_minus_the_submitter():
    # get_owner_uids_batch unions OWNS with owner_uid and does not dedupe; one teacher
    # may own two targeted groups; the submitter may own a group they submitted to.
    owners = {
        "g_a": ["user_teacher", "user_teacher"],
        "g_b": ["user_teacher", "user_other"],
        "g_c": ["user_student"],
    }
    assert unique_recipients(owners, "user_student") == ["user_teacher", "user_other"]


@pytest.mark.asyncio
async def test_each_owning_teacher_is_rung_once_and_the_bell_opens_the_review(
    notification_service,
):
    backend = _backend({"g_a": ["user_teacher", "user_teacher"], "g_b": ["user_teacher"]})

    await handle_submission_for_review(
        _event(("g_a", "g_b")), notification_service=notification_service, backend=backend
    )

    backend.get_owner_uids_batch.assert_awaited_once_with(["g_a", "g_b"])
    notification_service.create_notification.assert_awaited_once_with(
        user_uid="user_teacher",
        notification_type=NotificationType.SUBMISSION_FOR_REVIEW,
        title="Submission for review",
        message="'My essay' was submitted for your feedback.",
        source_uid="ue_1",
        source_type=EntityType.USER_ENTRY,
    )


@pytest.mark.asyncio
async def test_two_teachers_get_two_bells(notification_service):
    backend = _backend({"g_a": ["user_t1"], "g_b": ["user_t2"]})

    await handle_submission_for_review(
        _event(("g_a", "g_b"), title=None),
        notification_service=notification_service,
        backend=backend,
    )

    assert notification_service.create_notification.await_count == 2
    rung = [c.kwargs["user_uid"] for c in notification_service.create_notification.await_args_list]
    assert rung == ["user_t1", "user_t2"]
    assert (
        notification_service.create_notification.await_args_list[0].kwargs["message"]
        == "'an entry' was submitted for your feedback."
    )


@pytest.mark.asyncio
async def test_no_created_request_rings_nobody_and_reads_nothing(notification_service):
    backend = _backend()

    await handle_submission_for_review(
        _event(groups=()), notification_service=notification_service, backend=backend
    )

    backend.get_owner_uids_batch.assert_not_awaited()
    notification_service.create_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_submitter_never_rings_themselves(notification_service):
    backend = _backend({"g_own": ["user_student"]})

    await handle_submission_for_review(
        _event(("g_own",)), notification_service=notification_service, backend=backend
    )

    notification_service.create_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_owner_read_is_logged_not_raised(notification_service):
    backend = MagicMock()
    backend.get_owner_uids_batch = AsyncMock(
        return_value=Result.fail(Errors.database(operation="get_owner_uids_batch", message="down"))
    )

    await handle_submission_for_review(
        _event(), notification_service=notification_service, backend=backend
    )  # no raise

    notification_service.create_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_write_is_logged_and_the_other_teacher_is_still_rung(
    notification_service,
):
    notification_service.create_notification = AsyncMock(
        side_effect=[
            Result.fail(Errors.database(operation="create_notification", message="down")),
            Result.ok("notif_2"),
        ]
    )
    backend = _backend({"g_a": ["user_t1"], "g_b": ["user_t2"]})

    await handle_submission_for_review(
        _event(("g_a", "g_b")), notification_service=notification_service, backend=backend
    )  # no raise

    assert notification_service.create_notification.await_count == 2
    assert notification_service.create_notification.await_args_list[1] == call(
        user_uid="user_t2",
        notification_type=NotificationType.SUBMISSION_FOR_REVIEW,
        title="Submission for review",
        message="'My essay' was submitted for your feedback.",
        source_uid="ue_1",
        source_type=EntityType.USER_ENTRY,
    )
