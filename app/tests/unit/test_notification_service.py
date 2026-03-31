"""
Unit Tests for NotificationService
=====================================

Tests create, get_unread_count, get_notifications, mark_read, mark_all_read.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.notifications.notification_service import NotificationService
from core.utils.result_simplified import Result


@pytest.fixture
def mock_backend():
    """Create a mock NotificationBackend."""
    backend = MagicMock()
    backend.create_notification = AsyncMock()
    backend.get_unread_count = AsyncMock()
    backend.get_notifications = AsyncMock()
    backend.mark_read = AsyncMock()
    backend.mark_all_read = AsyncMock()
    return backend


@pytest.fixture
def service(mock_backend):
    """Create NotificationService with mocked backend."""
    return NotificationService(executor=mock_backend)


# ============================================================================
# CREATE NOTIFICATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_notification_success(service, mock_backend):
    """Should create a notification and return its UID."""
    mock_backend.create_notification.return_value = Result.ok([{"uid": "notif_abc123"}])

    result = await service.create_notification(
        user_uid="user_student",
        notification_type="feedback_received",
        title="New feedback",
        message="Your teacher provided feedback.",
        source_uid="ku_feedback_xyz",
        source_type="exercise_report",
    )

    assert not result.is_error
    assert result.value.startswith("notif_")

    # Verify backend was called with correct params
    call_args = mock_backend.create_notification.call_args
    params = call_args[0][0]
    assert params["user_uid"] == "user_student"
    assert params["notification_type"] == "feedback_received"


@pytest.mark.asyncio
async def test_create_notification_user_not_found(service, mock_backend):
    """Should return NotFound if user doesn't exist."""
    mock_backend.create_notification.return_value = Result.ok([])

    result = await service.create_notification(
        user_uid="nonexistent_user",
        notification_type="test",
        title="Test",
        message="Test",
        source_uid="ku_test",
        source_type="test",
    )

    assert result.is_error


# ============================================================================
# GET UNREAD COUNT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_unread_count(service, mock_backend):
    """Should return count of unread notifications."""
    mock_backend.get_unread_count.return_value = Result.ok([{"count": 5}])

    result = await service.get_unread_count("user_student")

    assert not result.is_error
    assert result.value == 5


@pytest.mark.asyncio
async def test_get_unread_count_zero(service, mock_backend):
    """Should return 0 when no unread notifications."""
    mock_backend.get_unread_count.return_value = Result.ok([{"count": 0}])

    result = await service.get_unread_count("user_student")

    assert not result.is_error
    assert result.value == 0


# ============================================================================
# GET NOTIFICATIONS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_notifications(service, mock_backend):
    """Should return list of notifications."""
    mock_backend.get_notifications.return_value = Result.ok(
        [
            {
                "uid": "notif_1",
                "notification_type": "feedback_received",
                "title": "New feedback",
                "message": "Your teacher reviewed your work.",
                "source_uid": "ku_fb_1",
                "source_type": "exercise_report",
                "read": False,
                "created_at": "2026-02-15T10:00:00",
            },
            {
                "uid": "notif_2",
                "notification_type": "revision_requested",
                "title": "Revision needed",
                "message": "Your teacher requested changes.",
                "source_uid": "ku_fb_2",
                "source_type": "exercise_report",
                "read": True,
                "created_at": "2026-02-14T10:00:00",
            },
        ]
    )

    result = await service.get_notifications("user_student", limit=20)

    assert not result.is_error
    assert len(result.value) == 2
    assert result.value[0]["uid"] == "notif_1"
    assert result.value[0]["read"] is False
    assert result.value[1]["read"] is True


# ============================================================================
# MARK READ TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_mark_read_success(service, mock_backend):
    """Should mark a notification as read."""
    mock_backend.mark_read.return_value = Result.ok([{"uid": "notif_1"}])

    result = await service.mark_read("notif_1", "user_student")

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_mark_read_not_found(service, mock_backend):
    """Should return NotFound if notification doesn't belong to user."""
    mock_backend.mark_read.return_value = Result.ok([])

    result = await service.mark_read("notif_nonexistent", "user_student")

    assert result.is_error


# ============================================================================
# MARK ALL READ TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_mark_all_read(service, mock_backend):
    """Should mark all notifications as read and return count."""
    mock_backend.mark_all_read.return_value = Result.ok([{"count": 3}])

    result = await service.mark_all_read("user_student")

    assert not result.is_error
    assert result.value == 3
