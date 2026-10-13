"""Tests for UserEntryExerciseLinker (ADR-054).

The linker validates an entry's exercise link after creation — a revision's
addressed student — and writes nothing: the title is the student's and the
version is stamped by the writer.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.user_entry.exercise_linker import (
    ProcessingOutcome,
    UserEntryExerciseLinker,
)
from core.utils.result_simplified import Errors, Result


def _make_backend() -> MagicMock:
    # spec_set: a call the linker makes on anything else raises instead of passing.
    backend = MagicMock(spec_set=["get_exercise_context", "get_entry_owner", "update"])
    backend.get_exercise_context = AsyncMock()
    backend.get_entry_owner = AsyncMock()
    backend.update = AsyncMock(return_value=Result.ok(True))
    return backend


def _make_linker(backend: MagicMock) -> UserEntryExerciseLinker:
    return UserEntryExerciseLinker(backend=backend)


class TestProcessExerciseSubmission:
    @pytest.mark.asyncio
    async def test_standard_linking_validates_and_writes_nothing(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok(
            [
                {
                    "exercise_entity_type": "exercise",
                    "student_uid": None,
                    "exercise_title": "Write Essay",
                    "original_exercise_uid": None,
                }
            ]
        )
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "ex_1")

        assert result.is_ok
        assert result.value == ProcessingOutcome.PROCESSED
        backend.update.assert_not_awaited()
        backend.get_entry_owner.assert_not_awaited()

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
    async def test_revised_exercise_named_student_is_processed(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok(
            [
                {
                    "exercise_entity_type": "revised_exercise",
                    "student_uid": "user_1",
                    "exercise_title": "Revision",
                    "original_exercise_uid": "ex_original_1",
                }
            ]
        )
        backend.get_entry_owner.return_value = Result.ok(
            [{"student_uid": "user_1", "turn_in_exercise_title": "Write Essay"}]
        )
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "re_1")

        assert result.is_ok
        assert result.value == ProcessingOutcome.PROCESSED
        backend.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_wrong_student_for_revised_exercise(self):
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok(
            [
                {
                    "exercise_entity_type": "revised_exercise",
                    "student_uid": "user_2",
                    "exercise_title": "Revision",
                    "original_exercise_uid": "ex_original_1",
                }
            ]
        )
        backend.get_entry_owner.return_value = Result.ok(
            [{"student_uid": "user_1", "turn_in_exercise_title": "Write Essay"}]
        )
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "re_1")

        assert result.is_ok
        assert result.value == ProcessingOutcome.WRONG_STUDENT

    @pytest.mark.asyncio
    async def test_the_student_title_is_never_overwritten(self):
        """The writer titles a turn-in; the linker only validates (PR 7 ruling)."""
        backend = _make_backend()
        backend.get_exercise_context.return_value = Result.ok(
            [
                {
                    "exercise_entity_type": "exercise",
                    "student_uid": None,
                    "exercise_title": "Write Essay",
                    "original_exercise_uid": None,
                }
            ]
        )
        linker = _make_linker(backend)

        result = await linker.process_exercise_submission("sub_1", "ex_1")

        assert result.value == ProcessingOutcome.PROCESSED
        backend.update.assert_not_awaited()
