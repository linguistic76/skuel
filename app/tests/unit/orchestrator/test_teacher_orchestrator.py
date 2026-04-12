"""Tests for the TeacherOrchestrator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestrator.teacher_orchestrator import TeacherOrchestrator
from core.utils.result_simplified import Result


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
    """Test that student submissions are correctly bucketed based on status."""
    mock_submissions = [
        {"uid": "sub1", "status": "submitted", "student_name": "Alice M."},
        {"uid": "sub2", "status": "revision_requested", "student_name": "Alice M."},
        {"uid": "sub3", "status": "completed", "student_name": ""},
        {"uid": "sub4", "status": "unknown_status"},  # defaults to pending
    ]
    mock_teacher_review_service.get_student_submissions.return_value = Result.ok(mock_submissions)

    result = await orchestrator.get_bucketed_student_submissions(
        teacher_uid="teacher-123", student_uid="student-456"
    )

    assert result.is_ok
    pending, revision, completed, student_name = result.value

    assert len(pending) == 2
    assert pending[0]["uid"] == "sub1"
    assert pending[1]["uid"] == "sub4"

    assert len(revision) == 1
    assert revision[0]["uid"] == "sub2"

    assert len(completed) == 1
    assert completed[0]["uid"] == "sub3"

    assert student_name == "Alice M."
    mock_teacher_review_service.get_student_submissions.assert_called_once_with(
        teacher_uid="teacher-123", student_uid="student-456"
    )


@pytest.mark.asyncio
async def test_get_bucketed_student_submissions_empty(
    orchestrator: TeacherOrchestrator, mock_teacher_review_service: MagicMock
) -> None:
    """Test bucketing works when submissions are empty."""
    mock_teacher_review_service.get_student_submissions.return_value = Result.ok([])

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
async def test_get_student_ku_detail_with_admin_stats(
    orchestrator: TeacherOrchestrator, mock_admin_stats_service: MagicMock
) -> None:
    """Test getting student KU detail when admin stats is provided."""
    mock_detail = {"viewed_count": 5}
    mock_admin_stats_service.get_user_ku_detail.return_value = Result.ok(mock_detail)

    result = await orchestrator.get_student_ku_detail("student-123")
    assert result == mock_detail
    mock_admin_stats_service.get_user_ku_detail.assert_called_once_with("student-123")


@pytest.mark.asyncio
async def test_get_student_ku_detail_without_admin_stats() -> None:
    """Test getting student KU detail degrades gracefully if admin stats is omitted."""
    mock_teacher_service = MagicMock()
    orch = TeacherOrchestrator(teacher_review_service=mock_teacher_service, admin_stats=None)

    result = await orch.get_student_ku_detail("student-123")
    assert result is None
