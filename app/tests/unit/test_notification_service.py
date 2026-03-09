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
def mock_driver():
    """Create a mock Neo4j driver."""
    driver = MagicMock()
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def service(mock_driver):
    """Create NotificationService with mocked driver."""
    return NotificationService(executor=mock_driver)


# ============================================================================
# CREATE NOTIFICATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_notification_success(service, mock_driver):
    """Should create a notification and return its UID."""
    mock_driver.execute_query.return_value = Result.ok([{"uid": "notif_abc123"}])

    result = await service.create_notification(
        user_uid="user_student",
        notification_type="feedback_received",
        title="New feedback",
        message="Your teacher provided feedback.",
        source_uid="ku_feedback_xyz",
        source_type="submission_report",
    )

    assert not result.is_error
    assert result.value.startswith("notif_")

    # Verify Cypher was called with correct params
    call_args = mock_driver.execute_query.call_args
    assert "CREATE (n:Notification" in call_args[0][0]
    assert "HAS_NOTIFICATION" in call_args[0][0]
    assert call_args[0][1]["user_uid"] == "user_student"
    assert call_args[0][1]["notification_type"] == "feedback_received"


@pytest.mark.asyncio
async def test_create_notification_user_not_found(service, mock_driver):
    """Should return NotFound if user doesn't exist."""
    mock_driver.execute_query.return_value = Result.ok([])

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
async def test_get_unread_count(service, mock_driver):
    """Should return count of unread notifications."""
    mock_driver.execute_query.return_value = Result.ok([{"count": 5}])

    result = await service.get_unread_count("user_student")

    assert not result.is_error
    assert result.value == 5


@pytest.mark.asyncio
async def test_get_unread_count_zero(service, mock_driver):
    """Should return 0 when no unread notifications."""
    mock_driver.execute_query.return_value = Result.ok([{"count": 0}])

    result = await service.get_unread_count("user_student")

    assert not result.is_error
    assert result.value == 0


# ============================================================================
# GET NOTIFICATIONS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_notifications(service, mock_driver):
    """Should return list of notifications."""
    mock_driver.execute_query.return_value = Result.ok(
        [
            {
                "uid": "notif_1",
                "notification_type": "feedback_received",
                "title": "New feedback",
                "message": "Your teacher reviewed your work.",
                "source_uid": "ku_fb_1",
                "source_type": "submission_report",
                "read": False,
                "created_at": "2026-02-15T10:00:00",
            },
            {
                "uid": "notif_2",
                "notification_type": "revision_requested",
                "title": "Revision needed",
                "message": "Your teacher requested changes.",
                "source_uid": "ku_fb_2",
                "source_type": "submission_report",
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
async def test_mark_read_success(service, mock_driver):
    """Should mark a notification as read."""
    mock_driver.execute_query.return_value = Result.ok([{"uid": "notif_1"}])

    result = await service.mark_read("notif_1", "user_student")

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_mark_read_not_found(service, mock_driver):
    """Should return NotFound if notification doesn't belong to user."""
    mock_driver.execute_query.return_value = Result.ok([])

    result = await service.mark_read("notif_nonexistent", "user_student")

    assert result.is_error


# ============================================================================
# MARK ALL READ TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_mark_all_read(service, mock_driver):
    """Should mark all notifications as read and return count."""
    mock_driver.execute_query.return_value = Result.ok([{"count": 3}])

    result = await service.mark_all_read("user_student")

    assert not result.is_error
    assert result.value == 3
