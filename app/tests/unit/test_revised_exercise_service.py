"""Tests for RevisedExerciseService access control.

Verifies that:
- create_revised_exercise checks teacher authority via SHARES_WITH graph path
- list_for_student scopes results to requesting teacher when teacher_uid provided
"""

from unittest.mock import AsyncMock

import pytest

from core.services.revised_exercises.revised_exercise_service import RevisedExerciseService
from core.utils.result_simplified import Result


@pytest.fixture
def mock_backend():
    backend = AsyncMock()
    backend.execute_query = AsyncMock()
    backend.create = AsyncMock()
    backend.get_revision_chain = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def service(mock_backend):
    return RevisedExerciseService(backend=mock_backend)


class TestVerifyTeacherAuthority:
    """Test _verify_teacher_authority access control."""

    @pytest.mark.asyncio
    async def test_rejects_when_no_authority(self, service, mock_backend):
        """Teacher without SHARES_WITH on submission gets rejected."""
        mock_backend.execute_query.return_value = Result.ok([])

        result = await service._verify_teacher_authority(
            teacher_uid="user_teacher",
            feedback_uid="fb_123",
            student_uid="user_student",
        )

        assert result.is_error
        error = result.expect_error()
        assert "review authority" in error.message.lower()

    @pytest.mark.asyncio
    async def test_accepts_when_authority_exists(self, service, mock_backend):
        """Teacher with SHARES_WITH on submission is accepted."""
        mock_backend.execute_query.return_value = Result.ok(
            [{"submission_uid": "sub_123"}]
        )

        result = await service._verify_teacher_authority(
            teacher_uid="user_teacher",
            feedback_uid="fb_123",
            student_uid="user_student",
        )

        assert not result.is_error
        assert result.value is True

    @pytest.mark.asyncio
    async def test_propagates_database_error(self, service, mock_backend):
        """Database errors propagate correctly."""
        from core.utils.result_simplified import Errors

        mock_backend.execute_query.return_value = Result.fail(
            Errors.database("execute_query", "connection failed")
        )

        result = await service._verify_teacher_authority(
            teacher_uid="user_teacher",
            feedback_uid="fb_123",
            student_uid="user_student",
        )

        assert result.is_error


class TestCreateRevisedExerciseAccessControl:
    """Test that create_revised_exercise enforces authority check."""

    @pytest.mark.asyncio
    async def test_blocks_creation_without_authority(self, service, mock_backend):
        """Creation fails when teacher lacks review authority."""
        # Authority check returns empty (no matching graph path)
        mock_backend.execute_query.return_value = Result.ok([])

        result = await service.create_revised_exercise(
            teacher_uid="user_teacher",
            original_exercise_uid="ex_123",
            feedback_uid="fb_123",
            student_uid="user_student",
            instructions="Please revise section 2",
        )

        assert result.is_error
        error = result.expect_error()
        assert "review authority" in error.message.lower()
        # backend.create should NOT have been called
        mock_backend.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_creation_with_authority(self, service, mock_backend):
        """Creation proceeds when teacher has review authority."""
        # First call: authority check succeeds
        # Second call: get_revision_chain (via backend method)
        # Third call: OWNS relationship creation
        mock_backend.execute_query.side_effect = [
            Result.ok([{"submission_uid": "sub_123"}]),  # authority check
            Result.ok(True),  # OWNS relationship
        ]
        mock_backend.get_revision_chain.return_value = Result.ok([])
        mock_backend.create.return_value = Result.ok(AsyncMock(uid="re_test_abc"))
        mock_backend.link_to_feedback = AsyncMock(return_value=Result.ok(True))
        mock_backend.link_to_exercise = AsyncMock(return_value=Result.ok(True))

        result = await service.create_revised_exercise(
            teacher_uid="user_teacher",
            original_exercise_uid="ex_123",
            feedback_uid="fb_123",
            student_uid="user_student",
            instructions="Please revise section 2",
        )

        assert not result.is_error
        mock_backend.create.assert_called_once()


class TestListForStudentScoping:
    """Test that list_for_student scopes by teacher when provided."""

    @pytest.mark.asyncio
    async def test_unscoped_query_without_teacher_uid(self, service, mock_backend):
        """Without teacher_uid, queries all revisions for student."""
        mock_backend.execute_query.return_value = Result.ok([])

        await service.list_for_student("user_student")

        query = mock_backend.execute_query.call_args[0][0]
        assert "teacher_uid" not in mock_backend.execute_query.call_args[0][1]
        assert "OWNS" not in query

    @pytest.mark.asyncio
    async def test_scoped_query_with_teacher_uid(self, service, mock_backend):
        """With teacher_uid, query includes OWNS from teacher."""
        mock_backend.execute_query.return_value = Result.ok([])

        await service.list_for_student("user_student", teacher_uid="user_teacher")

        query = mock_backend.execute_query.call_args[0][0]
        params = mock_backend.execute_query.call_args[0][1]
        assert "OWNS" in query
        assert params["teacher_uid"] == "user_teacher"
        assert params["student_uid"] == "user_student"
