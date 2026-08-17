"""Tests for RevisedExerciseService access control.

Verifies that:
- create() checks teacher authority via SHARES_WITH graph path
- list_for_student scopes results to requesting teacher when teacher_uid provided
"""

from unittest.mock import AsyncMock

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.exercises.revised_exercise import RevisedExercise
from core.services.revised_exercises.revised_exercise_service import RevisedExerciseService
from core.utils.result_simplified import Result


def _make_entity(**overrides: object) -> RevisedExercise:
    """Create a minimal RevisedExercise for testing."""
    defaults = {
        "uid": "re_test_abc",
        "entity_type": EntityType.REVISED_EXERCISE,
        "title": "Revision 1",
        "user_uid": "user_teacher",
        "revision_number": 0,
        "original_exercise_uid": "ex_123",
        "report_uid": "fb_123",
        "student_uid": "user_student",
        "instructions": "Please revise section 2",
    }
    defaults.update(overrides)
    return RevisedExercise(**defaults)


@pytest.fixture
def mock_backend():
    backend = AsyncMock()
    backend.verify_teacher_authority = AsyncMock()
    backend.auto_share_with_student = AsyncMock()
    backend.list_for_student = AsyncMock()
    backend.create = AsyncMock()
    backend.get_revision_chain = AsyncMock(return_value=Result.ok([]))
    backend.get_next_revision_number = AsyncMock(return_value=Result.ok(1))
    return backend


@pytest.fixture
def service(mock_backend):
    return RevisedExerciseService(backend=mock_backend)


class TestVerifyTeacherAuthority:
    """Test _verify_teacher_authority access control."""

    @pytest.mark.asyncio
    async def test_rejects_when_no_authority(self, service, mock_backend):
        """Teacher without SHARES_WITH on submission gets rejected."""
        mock_backend.verify_teacher_authority.return_value = Result.ok([])

        result = await service._verify_teacher_authority(
            teacher_uid="user_teacher",
            report_uid="fb_123",
            student_uid="user_student",
        )

        assert result.is_error
        error = result.expect_error()
        assert "review authority" in error.message.lower()

    @pytest.mark.asyncio
    async def test_accepts_when_authority_exists(self, service, mock_backend):
        """Teacher with SHARES_WITH on submission is accepted."""
        mock_backend.verify_teacher_authority.return_value = Result.ok(
            [{"submission_uid": "sub_123"}]
        )

        result = await service._verify_teacher_authority(
            teacher_uid="user_teacher",
            report_uid="fb_123",
            student_uid="user_student",
        )

        assert not result.is_error
        assert result.value == [{"submission_uid": "sub_123"}]

    @pytest.mark.asyncio
    async def test_propagates_database_error(self, service, mock_backend):
        """Database errors propagate correctly."""
        from core.utils.result_simplified import Errors

        mock_backend.verify_teacher_authority.return_value = Result.fail(
            Errors.database("verify_teacher_authority", "connection failed")
        )

        result = await service._verify_teacher_authority(
            teacher_uid="user_teacher",
            report_uid="fb_123",
            student_uid="user_student",
        )

        assert result.is_error


class TestCreateRevisedExerciseAccessControl:
    """Test that create() enforces authority check."""

    @pytest.mark.asyncio
    async def test_blocks_creation_without_authority(self, service, mock_backend):
        """Creation fails when teacher lacks review authority."""
        # Authority check returns empty (no matching graph path)
        mock_backend.verify_teacher_authority.return_value = Result.ok([])

        entity = _make_entity()
        result = await service.create(entity)

        assert result.is_error
        error = result.expect_error()
        assert "review authority" in error.message.lower()
        # backend.create should NOT have been called
        mock_backend.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_creation_with_authority(self, service, mock_backend):
        """Creation proceeds when teacher has review authority."""
        mock_backend.verify_teacher_authority.return_value = Result.ok(
            [{"submission_uid": "sub_123"}]
        )
        mock_backend.auto_share_with_student.return_value = Result.ok(True)
        mock_backend.get_next_revision_number.return_value = Result.ok(1)
        mock_backend.create.return_value = Result.ok(AsyncMock(uid="re_test_abc"))
        mock_backend.link_to_report = AsyncMock(return_value=Result.ok(True))
        mock_backend.link_to_exercise = AsyncMock(return_value=Result.ok(True))

        entity = _make_entity()
        result = await service.create(entity)

        assert not result.is_error
        mock_backend.create.assert_called_once()
        # Sharer attribution (arc 2 C4): the enriched entity crosses the
        # boundary stamped with the teacher as creator.
        enriched = mock_backend.create.call_args[0][0]
        assert enriched.created_by == "user_teacher"

    @pytest.mark.asyncio
    async def test_auto_shares_with_student(self, service, mock_backend):
        """RevisedExercise is auto-shared with the student via SHARES_WITH."""
        mock_backend.verify_teacher_authority.return_value = Result.ok(
            [{"submission_uid": "sub_123"}]
        )
        mock_backend.auto_share_with_student.return_value = Result.ok(True)
        mock_backend.get_next_revision_number.return_value = Result.ok(1)
        mock_backend.create.return_value = Result.ok(AsyncMock(uid="re_test_abc"))
        mock_backend.link_to_report = AsyncMock(return_value=Result.ok(True))
        mock_backend.link_to_exercise = AsyncMock(return_value=Result.ok(True))

        entity = _make_entity()
        await service.create(entity)

        # Verify auto_share_with_student was called with correct student_uid
        mock_backend.auto_share_with_student.assert_called_once()
        call_args = mock_backend.auto_share_with_student.call_args[0]
        assert call_args[0] == "user_student"  # student_uid


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
