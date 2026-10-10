"""Tests for RevisedExerciseService access control.

Verifies that:
- create() admits before any write: the report's entry is the student's, asks
  the teacher for feedback (ADR-088 §2), and fulfils the exercise being revised
- every refusal is not-found, and the exercise is judged only after the entry
- list_for_student scopes results to requesting teacher when teacher_uid provided
"""

from unittest.mock import AsyncMock

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.exercises.revised_exercise import RevisedExercise
from core.services.revised_exercises.revised_exercise_service import RevisedExerciseService
from core.utils.result_simplified import Errors, Result

TARGET = {"submission_uid": "sub_123", "exercise_uids": ["ex_123"]}


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
    backend.get_revision_target = AsyncMock(return_value=Result.ok(TARGET))
    backend.auto_share_with_student = AsyncMock(return_value=Result.ok(True))
    backend.list_for_student = AsyncMock()
    backend.create = AsyncMock(return_value=Result.ok(AsyncMock(uid="re_test_abc")))
    backend.get_revision_chain = AsyncMock(return_value=Result.ok([]))
    backend.get_next_revision_number = AsyncMock(return_value=Result.ok(1))
    backend.get_original_exercise_modality = AsyncMock(return_value=Result.ok(None))
    backend.link_to_report = AsyncMock(return_value=Result.ok(True))
    backend.link_to_exercise = AsyncMock(return_value=Result.ok(True))
    return backend


@pytest.fixture
def entry_service():
    entries = AsyncMock()
    entries.teacher_has_feedback_authority = AsyncMock(return_value=Result.ok(True))
    return entries


@pytest.fixture
def service(mock_backend, entry_service):
    return RevisedExerciseService(backend=mock_backend, entry_service=entry_service)


def _is_not_found(result: Result[object], resource: str) -> bool:
    if not result.is_error:
        return False
    error = result.expect_error()
    return error.category.value == "not_found" and resource in error.message


class TestAdmitRevision:
    """admit_revision — the one up-front check create() runs before writing."""

    @pytest.mark.asyncio
    async def test_admits_the_teacher_the_entry_asks(self, service, entry_service):
        result = await service.admit_revision("user_teacher", "fb_123", "user_student", "ex_123")

        assert result.is_ok
        assert result.value.submission_uid == "sub_123"
        entry_service.teacher_has_feedback_authority.assert_awaited_once_with(
            "sub_123", "user_teacher"
        )

    @pytest.mark.asyncio
    async def test_no_target_is_not_found_and_asks_no_authority(
        self, service, mock_backend, entry_service
    ):
        """A missing report, a report on no entry, and the wrong student look alike."""
        mock_backend.get_revision_target.return_value = Result.ok(None)

        result = await service.admit_revision("user_teacher", "fb_123", "user_student", "ex_123")

        assert _is_not_found(result, "EntryReport")
        entry_service.teacher_has_feedback_authority.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_teacher_the_entry_does_not_ask_is_not_found(self, service, entry_service):
        entry_service.teacher_has_feedback_authority.return_value = Result.ok(False)

        result = await service.admit_revision("user_teacher", "fb_123", "user_student", "ex_999")

        # The exercise is not judged for a refused entry: the answer is the report's.
        assert _is_not_found(result, "EntryReport")

    @pytest.mark.asyncio
    async def test_an_exercise_the_entry_does_not_fulfil_is_not_found(self, service):
        result = await service.admit_revision("user_teacher", "fb_123", "user_student", "ex_999")

        assert _is_not_found(result, "Exercise")

    @pytest.mark.asyncio
    async def test_backend_errors_propagate(self, service, mock_backend, entry_service):
        mock_backend.get_revision_target.return_value = Result.fail(
            Errors.database("get_revision_target", "connection failed")
        )
        assert (await service.admit_revision("t", "fb", "s", "ex")).is_error

        mock_backend.get_revision_target.return_value = Result.ok(TARGET)
        entry_service.teacher_has_feedback_authority.return_value = Result.fail(
            Errors.database("verify_teacher_has_group_access", "connection failed")
        )
        result = await service.admit_revision("t", "fb", "s", "ex_123")
        assert result.is_error
        assert not _is_not_found(result, "EntryReport")


class TestCreateRevisedExerciseAccessControl:
    """create() writes nothing unless admit_revision admits."""

    @pytest.mark.asyncio
    async def test_blocks_creation_without_authority(self, service, mock_backend, entry_service):
        entry_service.teacher_has_feedback_authority.return_value = Result.ok(False)

        result = await service.create(_make_entity())

        assert _is_not_found(result, "EntryReport")
        mock_backend.create.assert_not_called()
        mock_backend.auto_share_with_student.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocks_creation_for_an_unfulfilled_exercise(self, service, mock_backend):
        result = await service.create(_make_entity(original_exercise_uid="ex_999"))

        assert _is_not_found(result, "Exercise")
        mock_backend.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_creation_with_authority(self, service, mock_backend):
        result = await service.create(_make_entity())

        assert not result.is_error
        mock_backend.create.assert_called_once()
        enriched = mock_backend.create.call_args[0][0]
        # Sharer attribution: the enriched entity crosses the boundary stamped
        # with the teacher as creator, and carries the admitted entry.
        assert enriched.created_by == "user_teacher"
        assert enriched.submission_uid == "sub_123"

    @pytest.mark.asyncio
    async def test_a_client_submission_uid_never_replaces_the_admitted_one(
        self, service, mock_backend
    ):
        await service.create(_make_entity(submission_uid="ue_someone_else"))

        assert mock_backend.create.call_args[0][0].submission_uid == "sub_123"

    @pytest.mark.asyncio
    async def test_auto_shares_with_student(self, service, mock_backend):
        """RevisedExercise is auto-shared with the student via SHARES_WITH."""
        await service.create(_make_entity())

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
