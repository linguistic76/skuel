"""
Unit Tests for Feedback Notification Handler
==============================================

Tests that ReportSubmitted, SubmissionApproved, SubmissionRevisionRequested,
and RevisedExerciseCreated events create the correct notifications via
NotificationService.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events.handlers.report_notification_handler import (
    handle_report_submitted,
    handle_revised_exercise_created,
    handle_revision_requested,
    handle_submission_approved,
)
from core.events.learning_loop_events import (
    ReportSubmitted,
    RevisedExerciseCreated,
    UserEntryApproved,
    UserEntryRevisionRequested,
)
from core.models.enums.entity_enums import EntityType
from core.utils.result_simplified import Result


@pytest.fixture
def mock_notification_service():
    """Create a mock NotificationService."""
    service = MagicMock()
    service.create_notification = AsyncMock(return_value=Result.ok("notif_test123"))
    return service


# ============================================================================
# FEEDBACK SUBMITTED HANDLER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_handle_report_submitted_creates_notification(mock_notification_service):
    """Should create a feedback_received notification pointing to the feedback entity."""
    event = ReportSubmitted(
        submission_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="user_student",
        report_uid="ku_feedback_456",
        occurred_at=datetime.now(),
    )

    await handle_report_submitted(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_called_once_with(
        user_uid="user_student",
        notification_type="feedback_received",
        title="New feedback on your submission",
        message="Your teacher reviewed your submission and left feedback.",
        source_uid="ku_feedback_456",
        source_type=EntityType.ENTRY_REPORT,
    )


@pytest.mark.asyncio
async def test_handle_report_submitted_skips_when_no_student(mock_notification_service):
    """Should skip notification when student_uid is empty."""
    event = ReportSubmitted(
        submission_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="",
        report_uid="ku_feedback_456",
        occurred_at=datetime.now(),
    )

    await handle_report_submitted(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_not_called()


# ============================================================================
# SUBMISSION APPROVED HANDLER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_handle_submission_approved_creates_notification(mock_notification_service):
    """Should create a submission_approved notification."""
    event = UserEntryApproved(
        entity_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="user_student",
        occurred_at=datetime.now(),
        mastered_ku_count=0,
    )

    await handle_submission_approved(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_called_once_with(
        user_uid="user_student",
        notification_type="submission_approved",
        title="Your submission was approved",
        message="Your teacher approved your work on this submission.",
        source_uid="ku_submission_123",
        source_type=EntityType.USER_ENTRY,
    )


@pytest.mark.asyncio
async def test_handle_submission_approved_includes_mastery_count(mock_notification_service):
    """Should include mastered Ku count in message when mastered_ku_count > 0."""
    event = UserEntryApproved(
        entity_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="user_student",
        occurred_at=datetime.now(),
        mastered_ku_count=3,
    )

    await handle_submission_approved(event, notification_service=mock_notification_service)

    call_kwargs = mock_notification_service.create_notification.call_args[1]
    assert "3 knowledge unit(s)" in call_kwargs["message"]
    assert call_kwargs["notification_type"] == "submission_approved"


@pytest.mark.asyncio
async def test_handle_submission_approved_skips_when_no_student(mock_notification_service):
    """Should skip notification when student_uid is empty."""
    event = UserEntryApproved(
        entity_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="",
        occurred_at=datetime.now(),
    )

    await handle_submission_approved(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_not_called()


# ============================================================================
# REVISION REQUESTED HANDLER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_handle_revision_requested_creates_notification(mock_notification_service):
    """Should create a revision_requested notification for the student."""
    event = UserEntryRevisionRequested(
        entity_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="user_student",
        occurred_at=datetime.now(),
        revision_notes="Please add more detail to section 2.",
        metadata={"report_uid": "ku_feedback_789"},
    )

    await handle_revision_requested(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_called_once_with(
        user_uid="user_student",
        notification_type="revision_requested",
        title="Revision requested on your submission",
        message="Your teacher has requested changes to your submission.",
        source_uid="ku_feedback_789",
        source_type=EntityType.ENTRY_REPORT,
    )


@pytest.mark.asyncio
async def test_handle_revision_requested_skips_when_no_student(mock_notification_service):
    """Should skip notification when student_uid is empty."""
    event = UserEntryRevisionRequested(
        entity_uid="ku_submission_123",
        teacher_uid="user_teacher",
        student_uid="",
        occurred_at=datetime.now(),
    )

    await handle_revision_requested(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_not_called()


# ============================================================================
# REVISED EXERCISE CREATED HANDLER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_handle_revised_exercise_created_creates_notification(mock_notification_service):
    """Should create a revised_exercise_created notification for the student."""
    event = RevisedExerciseCreated(
        revised_exercise_uid="re_revision_abc",
        teacher_uid="user_teacher",
        student_uid="user_student",
        original_exercise_uid="exercise_123",
        report_uid="sr_456",
        revision_number=1,
        occurred_at=datetime.now(),
    )

    await handle_revised_exercise_created(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_called_once_with(
        user_uid="user_student",
        notification_type="revised_exercise_created",
        title="Revision instructions are ready",
        message="Your teacher created revision instructions based on your submission feedback.",
        source_uid="re_revision_abc",
        source_type=EntityType.REVISED_EXERCISE,
    )


@pytest.mark.asyncio
async def test_handle_revised_exercise_created_includes_revision_number(mock_notification_service):
    """Should include revision number in message when revision_number > 1."""
    event = RevisedExerciseCreated(
        revised_exercise_uid="re_revision_abc",
        teacher_uid="user_teacher",
        student_uid="user_student",
        original_exercise_uid="exercise_123",
        report_uid="sr_456",
        revision_number=3,
        occurred_at=datetime.now(),
    )

    await handle_revised_exercise_created(event, notification_service=mock_notification_service)

    call_kwargs = mock_notification_service.create_notification.call_args[1]
    assert "revision #3" in call_kwargs["message"]


@pytest.mark.asyncio
async def test_handle_revised_exercise_created_skips_when_no_student(mock_notification_service):
    """Should skip notification when student_uid is empty."""
    event = RevisedExerciseCreated(
        revised_exercise_uid="re_revision_abc",
        teacher_uid="user_teacher",
        student_uid="",
        original_exercise_uid="exercise_123",
        report_uid="sr_456",
        revision_number=1,
        occurred_at=datetime.now(),
    )

    await handle_revised_exercise_created(event, notification_service=mock_notification_service)

    mock_notification_service.create_notification.assert_not_called()
