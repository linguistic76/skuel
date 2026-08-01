"""Tests for the TeacherOrchestrator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestrator.teacher_orchestrator import TeacherOrchestrator
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def mock_teacher_review_service() -> MagicMock:
    """Mock for TeacherReviewOperations."""
    mock = MagicMock()
    # Ensure all async methods return AsyncMocks
    mock.get_review_queue = AsyncMock()
    mock.get_submission_detail = AsyncMock()
    mock.get_students_summary = AsyncMock()
    mock.get_student_submissions = AsyncMock()
    mock.get_teacher_groups_with_stats = AsyncMock()
    mock.get_group_detail = AsyncMock()
    mock.verify_teacher_authority = AsyncMock(return_value=Result.ok(True))
    return mock


@pytest.fixture
def mock_admin_stats_service() -> MagicMock:
    """Mock for AdminStatsService."""
    mock = MagicMock()
    mock.get_user_ku_detail = AsyncMock()
    return mock


@pytest.fixture
def orchestrator(
    mock_teacher_review_service: MagicMock, mock_admin_stats_service: MagicMock
) -> TeacherOrchestrator:
    """Configured TeacherOrchestrator instance."""
    return TeacherOrchestrator(
        teacher_review_service=mock_teacher_review_service,
        admin_stats=mock_admin_stats_service,
    )


@pytest.mark.asyncio
async def test_get_bucketed_student_submissions_success(
    orchestrator: TeacherOrchestrator, mock_teacher_review_service: MagicMock
) -> None:
    """Needs Review is queue membership, not a status read.

    The student-scoped review queue (same query, same copy-revision collapse
    as /teaching/queue) decides the pending bucket; statuses only split the
    remainder into revision vs completed/history.
    """
    mock_submissions = [
        {"uid": "sub1", "status": "submitted", "student_name": "Alice M."},
        {"uid": "sub2", "status": "revision_requested", "student_name": "Alice M."},
        {"uid": "sub3", "status": "completed", "student_name": ""},
        # Pending status but ABSENT from the queue — a superseded copy.
        # It is history, never Needs Review.
        {"uid": "sub4", "status": "submitted"},
    ]
    mock_teacher_review_service.get_student_submissions.return_value = Result.ok(mock_submissions)
    mock_teacher_review_service.get_review_queue.return_value = Result.ok(
        [{"submission_uid": "sub1"}]
    )

    result = await orchestrator.get_bucketed_student_submissions(
        teacher_uid="teacher-123", student_uid="student-456"
    )

    assert result.is_ok
    pending, revision, completed, student_name = result.value

    assert [item["uid"] for item in pending] == ["sub1"]
    assert [item["uid"] for item in revision] == ["sub2"]
    assert [item["uid"] for item in completed] == ["sub3", "sub4"]

    assert student_name == "Alice M."
    mock_teacher_review_service.get_student_submissions.assert_called_once_with(
        teacher_uid="teacher-123", student_uid="student-456"
    )
    mock_teacher_review_service.get_review_queue.assert_called_once_with(
        teacher_uid="teacher-123", student_uid="student-456"
    )


@pytest.mark.asyncio
async def test_get_bucketed_student_submissions_empty(
    orchestrator: TeacherOrchestrator, mock_teacher_review_service: MagicMock
) -> None:
    """Test bucketing works when submissions are empty."""
    mock_teacher_review_service.get_student_submissions.return_value = Result.ok([])
    mock_teacher_review_service.get_review_queue.return_value = Result.ok([])

    result = await orchestrator.get_bucketed_student_submissions(
        teacher_uid="teacher-123", student_uid="student-456"
    )

    assert result.is_ok
    pending, revision, completed, student_name = result.value

    assert len(pending) == 0
    assert len(revision) == 0
    assert len(completed) == 0
    assert student_name == "student-456"  # falls back to uid when no names exist


@pytest.mark.asyncio
async def test_get_bucketed_student_submissions_queue_error_propagates(
    orchestrator: TeacherOrchestrator, mock_teacher_review_service: MagicMock
) -> None:
    """A failed queue read must fail the bucketing — silently bucketing
    everything to history would hide reviewable work."""
    mock_teacher_review_service.get_student_submissions.return_value = Result.ok(
        [{"uid": "sub1", "status": "submitted"}]
    )
    mock_teacher_review_service.get_review_queue.return_value = Result.fail(
        Errors.database("execute_query", "timeout")
    )

    result = await orchestrator.get_bucketed_student_submissions(
        teacher_uid="teacher-123", student_uid="student-456"
    )

    assert result.is_error


@pytest.mark.asyncio
async def test_get_student_ku_detail_with_admin_stats(
    orchestrator: TeacherOrchestrator, mock_admin_stats_service: MagicMock
) -> None:
    """Test getting student KU detail when admin stats is provided."""
    mock_detail = {"viewed_count": 5}
    mock_admin_stats_service.get_user_ku_detail.return_value = Result.ok(mock_detail)

    result = await orchestrator.get_student_ku_detail("teacher-123", "student-123")
    assert result == mock_detail
    mock_admin_stats_service.get_user_ku_detail.assert_called_once_with("student-123")


@pytest.mark.asyncio
async def test_get_student_ku_detail_without_admin_stats() -> None:
    """Test getting student KU detail degrades gracefully if admin stats is omitted."""
    mock_teacher_service = MagicMock()
    mock_teacher_service.verify_teacher_authority = AsyncMock(return_value=Result.ok(True))
    orch = TeacherOrchestrator(teacher_review_service=mock_teacher_service, admin_stats=None)

    result = await orch.get_student_ku_detail("teacher-123", "student-123")
    assert result is None
