"""``UserEntryOrchestrator.get_submit_target`` — what the Submit page may name (Submit & Share arc PR 7).

An Exercise through its audience-scoped read; a RevisedExercise for the student
it names or its owner, titled by its root; everything else one not-found.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestrator.user_entry_orchestrator import UserEntryOrchestrator
from core.utils.result_simplified import ErrorCategory, Errors, Result

STUDENT = "user_student"
TEACHER = "user_teacher"


def _not_found(uid: str):
    return Result.fail(Errors.not_found(resource="Exercise", identifier=uid))


def _orchestrator(*, exercises: dict[str, str], revision=None, revision_error=None):
    """``exercises`` maps uid → title for the scoped read; a revision is one model or none."""

    async def scoped(uid: str, user_uid: str):
        if uid in exercises:
            return Result.ok(SimpleNamespace(uid=uid, title=exercises[uid]))
        return _not_found(uid)

    exercise_service = MagicMock()
    exercise_service.get_exercise_for_user = AsyncMock(side_effect=scoped)
    revised = MagicMock()
    revised.get = AsyncMock(
        return_value=(revision_error if revision_error is not None else Result.ok(revision))
    )
    return UserEntryOrchestrator(
        user_entry_service=MagicMock(),
        exercises_service=exercise_service,
        teacher_review_service=MagicMock(),
        user_service=MagicMock(),
        activity_report_service=MagicMock(),
        revised_exercise_service=revised,
        entry_report_service=MagicMock(),
        report_relationship_service=MagicMock(),
    )


def _revision(student: str = STUDENT, root: str | None = "ex.root"):
    return SimpleNamespace(
        uid="re_1",
        title="Revision 2",
        student_uid=student,
        user_uid=TEACHER,
        original_exercise_uid=root,
    )


@pytest.mark.asyncio
async def test_an_exercise_in_the_callers_audience_is_named_by_its_title() -> None:
    o = _orchestrator(exercises={"ex.root": "The Gentle Return"})
    result = await o.get_submit_target("ex.root", STUDENT)
    assert result.is_ok
    assert result.value.title == "The Gentle Return"
    assert result.value.is_revision is False


@pytest.mark.asyncio
async def test_a_revision_for_the_named_student_is_named_by_its_root() -> None:
    o = _orchestrator(exercises={"ex.root": "The Gentle Return"}, revision=_revision())
    result = await o.get_submit_target("re_1", STUDENT)
    assert result.is_ok
    assert result.value.title == "The Gentle Return"
    assert result.value.is_revision is True


@pytest.mark.asyncio
async def test_the_revisions_owner_may_name_it_too() -> None:
    o = _orchestrator(exercises={"ex.root": "The Gentle Return"}, revision=_revision())
    result = await o.get_submit_target("re_1", TEACHER)
    assert result.is_ok and result.value.title == "The Gentle Return"


@pytest.mark.asyncio
async def test_a_revision_whose_root_is_gone_keeps_its_own_title() -> None:
    o = _orchestrator(exercises={}, revision=_revision())
    result = await o.get_submit_target("re_1", STUDENT)
    assert result.is_ok and result.value.title == "Revision 2"


@pytest.mark.asyncio
async def test_a_stranger_gets_one_not_found_for_a_revision() -> None:
    o = _orchestrator(exercises={"ex.root": "The Gentle Return"}, revision=_revision())
    result = await o.get_submit_target("re_1", "user_stranger")
    assert result.is_error
    assert result.expect_error().category is ErrorCategory.NOT_FOUND


@pytest.mark.asyncio
async def test_an_unknown_uid_is_not_found() -> None:
    o = _orchestrator(exercises={})
    result = await o.get_submit_target("nothing", STUDENT)
    assert result.is_error
    assert result.expect_error().category is ErrorCategory.NOT_FOUND


@pytest.mark.asyncio
async def test_a_backend_failure_on_the_exercise_read_is_not_masked_as_not_found() -> None:
    o = _orchestrator(exercises={})
    o._exercises.get_exercise_for_user = AsyncMock(
        return_value=Result.fail(Errors.database(operation="get", message="down"))
    )
    result = await o.get_submit_target("ex.root", STUDENT)
    assert result.is_error
    assert result.expect_error().category is ErrorCategory.DATABASE
    o._revised_exercise.get.assert_not_awaited()
