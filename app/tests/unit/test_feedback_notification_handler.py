"""
Unit Tests for Feedback Notification Handler
==============================================

Tests that SubmissionReviewed and SubmissionRevisionRequested events
create the correct notifications via NotificationService.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events.handlers.feedback_notification_handler import (
    handle_report_reviewed,
    handle_revision_requested,
)
from core.events.submission_events import SubmissionReviewed, SubmissionRevisionRequested
from core.utils.result_simplified import Result


@pytest.fixture
def mock_notification_service():
    """Create a mock NotificationService."""
    service = MagicMock()
    service.create_notification = AsyncMock(return_value=Result.ok("notif_test123"))
    return service


# ============================================================================
# SUBMISSION REVIEWED HANDLER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_handle_report_reviewed_creates_notification(mock_notification_service):
    """Should create a feedback_received notification for the student."""
    event = SubmissionReviewed(
        submission_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="user_student",
        occurred_at=datetime.now(),
        metadata={"feedback_uid": "ku_feedback_456"},
    )

    await handle_report_reviewed(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_called_once_with(
        user_uid="user_student",
        notification_type="feedback_received",
        title="New feedback on your submission",
        message="Your teacher reviewed your submission and provided feedback.",
        source_uid="ku_feedback_456",
        source_type="feedback_report",
    )


@pytest.mark.asyncio
async def test_handle_report_reviewed_uses_submission_uid_when_no_feedback_uid(
    mock_notification_service,
):
    """Should fall back to submission_uid when metadata has no feedback_uid."""
    event = SubmissionReviewed(
        submission_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="user_student",
        occurred_at=datetime.now(),
    )

    await handle_report_reviewed(event, notification_service=mock_notification_service)

    call_kwargs = mock_notification_service.create_notification.call_args[1]
    assert call_kwargs["source_uid"] == "ku_submission_123"


@pytest.mark.asyncio
async def test_handle_report_reviewed_skips_when_no_student(mock_notification_service):
    """Should skip notification when student_uid is empty."""
    event = SubmissionReviewed(
        submission_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="",
        occurred_at=datetime.now(),
    )

    await handle_report_reviewed(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_not_called()


# ============================================================================
# REVISION REQUESTED HANDLER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_handle_revision_requested_creates_notification(mock_notification_service):
    """Should create a revision_requested notification for the student."""
    event = SubmissionRevisionRequested(
        submission_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="user_student",
        occurred_at=datetime.now(),
        revision_notes="Please add more detail to section 2.",
        metadata={"feedback_uid": "ku_feedback_789"},
    )

    await handle_revision_requested(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_called_once_with(
        user_uid="user_student",
        notification_type="revision_requested",
        title="Revision requested on your submission",
        message="Your teacher has requested changes to your submission.",
        source_uid="ku_feedback_789",
        source_type="feedback_report",
    )


@pytest.mark.asyncio
async def test_handle_revision_requested_skips_when_no_student(mock_notification_service):
    """Should skip notification when student_uid is empty."""
    event = SubmissionRevisionRequested(
        submission_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="",
        occurred_at=datetime.now(),
    )

    await handle_revision_requested(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_not_called()
