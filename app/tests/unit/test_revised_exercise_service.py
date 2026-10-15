"""Tests for RevisedExerciseService's reads.

Verifies that list_for_student scopes results to the requesting teacher when
teacher_uid is provided. The service writes nothing: a revision is sent from
the review page (``TeacherReviewService.request_revision``).
"""

from unittest.mock import AsyncMock

import pytest

from core.services.revised_exercises.revised_exercise_service import RevisedExerciseService
from core.utils.result_simplified import Result


@pytest.fixture
def mock_backend():
    backend = AsyncMock()
    backend.list_for_student = AsyncMock()
    return backend


@pytest.fixture
def service(mock_backend):
    return RevisedExerciseService(backend=mock_backend)


class TestListForStudentScoping:
    """Test that list_for_student scopes by teacher when provided."""

    @pytest.mark.asyncio
    async def test_unscoped_query_without_teacher_uid(self, service, mock_backend):
        """Without teacher_uid, delegates to backend.list_for_student without teacher."""
        mock_backend.list_for_student.return_value = Result.ok([])

        await service.list_for_student("user_student")

        mock_backend.list_for_student.assert_called_once_with("user_student", None)

    @pytest.mark.asyncio
    async def test_scoped_query_with_teacher_uid(self, service, mock_backend):
        """With teacher_uid, delegates to backend.list_for_student with teacher scoping."""
        mock_backend.list_for_student.return_value = Result.ok([])

        await service.list_for_student("user_student", teacher_uid="user_teacher")

        mock_backend.list_for_student.assert_called_once_with("user_student", "user_teacher")
