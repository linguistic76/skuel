"""Tests for UserEntryExerciseLinker (ADR-054 Commit 6a).

Retargeted from the former
``tests/unit/services/test_submissions_core_service.py::TestProcessExerciseSubmission``
onto the new ``core/services/user_entry/exercise_linker.py`` module.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.user_entry.exercise_linker import (
    ProcessingOutcome,
    UserEntryExerciseLinker,
)
from core.utils.result_simplified import Errors, Result


def _make_backend() -> MagicMock:
    backend = MagicMock()
    backend.get_exercise_context = AsyncMock()
    backend.get_entry_owner = AsyncMock()
    backend.verify_student_group_membership = AsyncMock()
    backend.count_entries_for_exercise = AsyncMock()
    backend.update = AsyncMock(return_value=Result.ok(True))
    return backend


def _make_linker(backend: MagicMock) -> UserEntryExerciseLinker:
    return UserEntryExerciseLinker(backend=backend)


class TestProcessExerciseSubmission:
    @pytest.mark.asyncio
    async def test_standard_linking_and_title_update(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok(
            [
                {
                    "exercise_entity_type": "exercise",
                    "scope": "assigned",
                    "teacher_uid": "teacher_1",
                    "student_uid": None,
                    "exercise_title": "Write Essay",
                    "group_uid": "grp_1",
                }
            ]
        )
        backend.verify_student_group_membership.return_value = Result.ok(
            [{"student_uid": "user_1", "member_of_group": "grp_1"}]
        )
        backend.get_entry_owner.return_value = Result.ok([{"student_uid": "user_1"}])
        backend.count_entries_for_exercise.return_value = Result.ok(0)
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value == ProcessingOutcome.PROCESSED

    @pytest.mark.asyncio
    async def test_not_assigned_scope(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok(
            [
                {
                    "exercise_entity_type": "exercise",
                    "scope": "shared",
                    "teacher_uid": "teacher_1",
                    "student_uid": None,
                    "exercise_title": "Shared Ex",
                    "group_uid": None,
                }
            ]
        )
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value == ProcessingOutcome.NOT_ASSIGNED

    @pytest.mark.asyncio
    async def test_exercise_not_found(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok([])
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "ex_missing")

        assert result.is_ok
        assert result.value == ProcessingOutcome.NOT_EXERCISE

    @pytest.mark.asyncio
    async def test_query_failure_returns_not_exercise(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.fail(Errors.database("query", "timeout"))
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value == ProcessingOutcome.NOT_EXERCISE

    @pytest.mark.asyncio
    async def test_revised_exercise_counts_against_original(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok(
            [
                {
                    "exercise_entity_type": "revised_exercise",
                    "scope": None,
                    "teacher_uid": "teacher_1",
                    "student_uid": "user_1",
                    "exercise_title": "Revision",
                    "group_uid": None,
                    "original_exercise_uid": "ex_original_1",
                }
            ]
        )
        backend.get_entry_owner.return_value = Result.ok([{"student_uid": "user_1"}])
        backend.count_entries_for_exercise.return_value = Result.ok(1)
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "re_1")

        assert result.is_ok
        assert result.value == ProcessingOutcome.PROCESSED
        backend.count_entries_for_exercise.assert_awaited_once_with("user_1", "ex_original_1")

    @pytest.mark.asyncio
    async def test_wrong_student_for_revised_exercise(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok(
            [
                {
                    "exercise_entity_type": "revised_exercise",
                    "scope": None,
                    "teacher_uid": "teacher_1",
                    "student_uid": "user_2",
                    "exercise_title": "Revision",
                    "group_uid": None,
                    "original_exercise_uid": "ex_original_1",
                }
            ]
        )
        backend.get_entry_owner.return_value = Result.ok([{"student_uid": "user_1"}])
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "re_1")

        assert result.is_ok
        assert result.value == ProcessingOutcome.WRONG_STUDENT

    @pytest.mark.asyncio
    async def test_not_in_group(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok(
            [
                {
                    "exercise_entity_type": "exercise",
                    "scope": "assigned",
                    "teacher_uid": "teacher_1",
                    "student_uid": None,
                    "exercise_title": "Essay",
                    "group_uid": "grp_1",
                }
            ]
        )
        backend.verify_student_group_membership.return_value = Result.ok(
            [{"student_uid": "user_1", "member_of_group": None}]
        )
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value == ProcessingOutcome.NOT_IN_GROUP

    @pytest.mark.asyncio
    async def test_title_update_called_when_exercise_has_title(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok(
            [
                {
                    "exercise_entity_type": "exercise",
                    "scope": "assigned",
                    "teacher_uid": "teacher_1",
                    "student_uid": None,
                    "exercise_title": "Write Essay",
                    "group_uid": None,
                }
            ]
        )
        backend.get_entry_owner.return_value = Result.ok([{"student_uid": "user_1"}])
        backend.count_entries_for_exercise.return_value = Result.ok(0)
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value == ProcessingOutcome.PROCESSED
        backend.update.assert_awaited_once()
        call_args = backend.update.await_args
        assert call_args.args[0] == "sub_1"
        assert call_args.args[1]["title"] == "Write Essay v1"
        assert call_args.args[1]["revision_number"] == 1

    @pytest.mark.asyncio
    async def test_no_title_update_when_exercise_title_empty(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok(
            [
                {
                    "exercise_entity_type": "exercise",
                    "scope": "assigned",
                    "teacher_uid": "teacher_1",
                    "student_uid": None,
                    "exercise_title": "",
                    "group_uid": None,
                }
            ]
        )
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value == ProcessingOutcome.PROCESSED
        backend.update.assert_not_awaited()
