"""Tests for the SubmissionsOrchestrator."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.orchestrator.submissions_orchestrator import SubmissionsOrchestrator
from core.utils.result_simplified import ErrorCategory, Errors, Result


def _make_orchestrator(**overrides: MagicMock) -> tuple[SubmissionsOrchestrator, dict[str, MagicMock]]:
    mocks: dict[str, MagicMock] = {
        "submissions_service": MagicMock(),
        "exercises_service": MagicMock(),
        "submissions_search_service": MagicMock(),
        "submissions_core_service": MagicMock(),
        "teacher_review_service": MagicMock(),
        "user_service": MagicMock(),
        "activity_report_service": MagicMock(),
        "revised_exercise_service": MagicMock(),
        "exercise_report_service": MagicMock(),
        "sharing_service": MagicMock(),
    }
    mocks.update(overrides)

    # async method wiring
    mocks["submissions_service"].get_submission = AsyncMock()
    mocks["submissions_service"].list_submissions = AsyncMock()
    mocks["submissions_service"].submit_file = AsyncMock()
    mocks["submissions_service"].delete_submission_with_file = AsyncMock()
    mocks["submissions_search_service"].get_submissions_with_feedback_status = AsyncMock()
    mocks["exercises_service"].get_student_exercises = AsyncMock()
    mocks["exercises_service"].get_exercise_for_submission = AsyncMock()
    mocks["exercise_report_service"].get_by_uid = AsyncMock()
    mocks["sharing_service"].check_access = AsyncMock()
    mocks["revised_exercise_service"].get_by_report_uid = AsyncMock()
    mocks["revised_exercise_service"].get = AsyncMock()
    mocks["revised_exercise_service"].list_for_student = AsyncMock()
    mocks["submissions_core_service"].get_assessments_for_student = AsyncMock()
    mocks["activity_report_service"].get_by_uid = AsyncMock()
    mocks["activity_report_service"].get_history = AsyncMock()
    mocks["user_service"].context_builder = MagicMock()
    mocks["user_service"].context_builder.build = AsyncMock()

    orch = SubmissionsOrchestrator(
        submissions_service=mocks["submissions_service"],
        exercises_service=mocks["exercises_service"],
        submissions_search_service=mocks["submissions_search_service"],
        submissions_core_service=mocks["submissions_core_service"],
        teacher_review_service=mocks["teacher_review_service"],
        user_service=mocks["user_service"],
        activity_report_service=mocks["activity_report_service"],
        revised_exercise_service=mocks["revised_exercise_service"],
        exercise_report_service=mocks["exercise_report_service"],
        sharing_service=mocks["sharing_service"],
    )
    return orch, mocks


@pytest.fixture
def built() -> tuple[SubmissionsOrchestrator, dict[str, MagicMock]]:
    return _make_orchestrator()


# --- submit_file_with_learning_context ---


@pytest.mark.asyncio
async def test_submit_file_with_learning_context_uses_user_context(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    ctx = SimpleNamespace(current_ps_uids={"ps_studying"}, current_learning_path_uid="lp_1")
    mocks["user_service"].context_builder.build.return_value = Result.ok(ctx)
    mocks["submissions_service"].submit_file.return_value = Result.ok(MagicMock())

    await orch.submit_file_with_learning_context(
        file_content=b"x",
        original_filename="f.md",
        user_uid="user-1",
        fulfills_exercise_uid="ex_1",
        metadata=None,
        from_ps=None,
    )

    kwargs = mocks["submissions_service"].submit_file.call_args.kwargs
    assert kwargs["context_path_step_uid"] == "ps_studying"
    assert kwargs["context_learning_path_uid"] == "lp_1"
    assert kwargs["user_uid"] == "user-1"
    assert kwargs["fulfills_exercise_uid"] == "ex_1"


@pytest.mark.asyncio
async def test_submit_file_with_learning_context_prefers_explicit_from_ps(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    ctx = SimpleNamespace(current_ps_uids={"ps_from_context"}, current_learning_path_uid="lp_1")
    mocks["user_service"].context_builder.build.return_value = Result.ok(ctx)
    mocks["submissions_service"].submit_file.return_value = Result.ok(MagicMock())

    await orch.submit_file_with_learning_context(
        file_content=b"x",
        original_filename="f.md",
        user_uid="user-1",
        fulfills_exercise_uid=None,
        metadata=None,
        from_ps="ps_explicit",
    )

    kwargs = mocks["submissions_service"].submit_file.call_args.kwargs
    assert kwargs["context_path_step_uid"] == "ps_explicit"
    assert kwargs["context_learning_path_uid"] == "lp_1"


@pytest.mark.asyncio
async def test_submit_file_with_learning_context_context_build_fails_silently(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["user_service"].context_builder.build.return_value = Result.fail(
        Errors.database("read", "boom")
    )
    mocks["submissions_service"].submit_file.return_value = Result.ok(MagicMock())

    result = await orch.submit_file_with_learning_context(
        file_content=b"x",
        original_filename="f.md",
        user_uid="user-1",
        fulfills_exercise_uid=None,
        metadata=None,
        from_ps=None,
    )

    assert result.is_ok
    kwargs = mocks["submissions_service"].submit_file.call_args.kwargs
    assert kwargs["context_path_step_uid"] is None
    assert kwargs["context_learning_path_uid"] is None


@pytest.mark.asyncio
async def test_submit_file_with_learning_context_no_context_builder(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["user_service"].context_builder = None
    mocks["submissions_service"].submit_file.return_value = Result.ok(MagicMock())

    await orch.submit_file_with_learning_context(
        file_content=b"x",
        original_filename="f.md",
        user_uid="user-1",
        fulfills_exercise_uid=None,
        metadata=None,
        from_ps=None,
    )

    kwargs = mocks["submissions_service"].submit_file.call_args.kwargs
    assert kwargs["context_path_step_uid"] is None
    assert kwargs["context_learning_path_uid"] is None


# --- get_exercise_report_view ---


@pytest.mark.asyncio
async def test_get_exercise_report_view_success(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    report = MagicMock()
    report.uid = "er_1"
    revision = MagicMock()
    mocks["exercise_report_service"].get_by_uid.return_value = Result.ok(report)
    mocks["sharing_service"].check_access.return_value = Result.ok(True)
    mocks["revised_exercise_service"].get_by_report_uid.return_value = Result.ok(revision)

    result = await orch.get_exercise_report_view("er_1", "user-1")

    assert result.is_ok
    assert result.value["report"] is report
    assert result.value["revised_exercise"] is revision


@pytest.mark.asyncio
async def test_get_exercise_report_view_report_error_propagates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["exercise_report_service"].get_by_uid.return_value = Result.fail(
        Errors.database("read", "boom")
    )

    result = await orch.get_exercise_report_view("er_1", "user-1")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.DATABASE
    mocks["sharing_service"].check_access.assert_not_called()


@pytest.mark.asyncio
async def test_get_exercise_report_view_access_denied_returns_not_found(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    report = MagicMock()
    report.uid = "er_1"
    mocks["exercise_report_service"].get_by_uid.return_value = Result.ok(report)
    mocks["sharing_service"].check_access.return_value = Result.ok(False)

    result = await orch.get_exercise_report_view("er_1", "user-1")

    assert result.is_error
    err = result.expect_error()
    assert err.category == ErrorCategory.NOT_FOUND
    assert err.details["resource"] == "ExerciseReport"
    mocks["revised_exercise_service"].get_by_report_uid.assert_not_called()


@pytest.mark.asyncio
async def test_get_exercise_report_view_access_error_returns_not_found(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    report = MagicMock()
    report.uid = "er_1"
    mocks["exercise_report_service"].get_by_uid.return_value = Result.ok(report)
    mocks["sharing_service"].check_access.return_value = Result.fail(
        Errors.database("read", "boom")
    )

    result = await orch.get_exercise_report_view("er_1", "user-1")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.NOT_FOUND


@pytest.mark.asyncio
async def test_get_exercise_report_view_missing_revision_is_ok(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    report = MagicMock()
    report.uid = "er_1"
    mocks["exercise_report_service"].get_by_uid.return_value = Result.ok(report)
    mocks["sharing_service"].check_access.return_value = Result.ok(True)
    mocks["revised_exercise_service"].get_by_report_uid.return_value = Result.ok(None)

    result = await orch.get_exercise_report_view("er_1", "user-1")

    assert result.is_ok
    assert result.value["report"] is report
    assert result.value["revised_exercise"] is None


# --- Smoke delegation tests ---


@pytest.mark.asyncio
async def test_get_submission_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["submissions_service"].get_submission.return_value = Result.ok(None)
    await orch.get_submission("sub_1")
    mocks["submissions_service"].get_submission.assert_called_once_with("sub_1")


@pytest.mark.asyncio
async def test_list_submissions_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["submissions_service"].list_submissions.return_value = Result.ok([])
    await orch.list_submissions(
        "user-1", entity_type=EntityType.EXERCISE_SUBMISSION, status=EntityStatus.ACTIVE, limit=10, offset=5
    )
    mocks["submissions_service"].list_submissions.assert_called_once_with(
        "user-1",
        entity_type=EntityType.EXERCISE_SUBMISSION,
        status=EntityStatus.ACTIVE,
        limit=10,
        offset=5,
    )


@pytest.mark.asyncio
async def test_process_submission_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["submissions_service"].submit_file.return_value = Result.ok(MagicMock())
    await orch.process_submission(
        file_content=b"x",
        original_filename="f.md",
        user_uid="user-1",
        entity_type=EntityType.EXERCISE_SUBMISSION,
        processor_type=ProcessorType.HUMAN,
    )
    assert mocks["submissions_service"].submit_file.call_args.kwargs["user_uid"] == "user-1"


@pytest.mark.asyncio
async def test_delete_submission_with_file_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["submissions_service"].delete_submission_with_file.return_value = Result.ok(True)
    await orch.delete_submission_with_file("sub_1")
    mocks["submissions_service"].delete_submission_with_file.assert_called_once_with("sub_1")


@pytest.mark.asyncio
async def test_get_submissions_with_feedback_status_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["submissions_search_service"].get_submissions_with_feedback_status.return_value = Result.ok([])
    await orch.get_submissions_with_feedback_status("user-1")
    mocks["submissions_search_service"].get_submissions_with_feedback_status.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_get_student_exercises_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["exercises_service"].get_student_exercises.return_value = Result.ok([])
    await orch.get_student_exercises("user-1")
    mocks["exercises_service"].get_student_exercises.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_get_exercise_for_submission_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["exercises_service"].get_exercise_for_submission.return_value = Result.ok(None)
    await orch.get_exercise_for_submission("sub_1")
    mocks["exercises_service"].get_exercise_for_submission.assert_called_once_with("sub_1")


@pytest.mark.asyncio
async def test_get_exercise_report_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["exercise_report_service"].get_by_uid.return_value = Result.ok(MagicMock())
    await orch.get_exercise_report("er_1")
    mocks["exercise_report_service"].get_by_uid.assert_called_once_with("er_1")


@pytest.mark.asyncio
async def test_check_report_access_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["sharing_service"].check_access.return_value = Result.ok(True)
    await orch.check_report_access("er_1", "user-1")
    mocks["sharing_service"].check_access.assert_called_once_with("er_1", "user-1")


@pytest.mark.asyncio
async def test_get_assessments_for_student_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["submissions_core_service"].get_assessments_for_student.return_value = Result.ok([])
    await orch.get_assessments_for_student("user-1", limit=20)
    mocks["submissions_core_service"].get_assessments_for_student.assert_called_once_with(
        "user-1", limit=20
    )


@pytest.mark.asyncio
async def test_get_activity_report_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["activity_report_service"].get_by_uid.return_value = Result.ok(MagicMock())
    await orch.get_activity_report("ar_1", "user-1")
    mocks["activity_report_service"].get_by_uid.assert_called_once_with("ar_1", "user-1")


@pytest.mark.asyncio
async def test_get_activity_report_history_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["activity_report_service"].get_history.return_value = Result.ok([])
    await orch.get_activity_report_history("user-1", limit=25)
    mocks["activity_report_service"].get_history.assert_called_once_with(
        subject_uid="user-1", limit=25
    )


@pytest.mark.asyncio
async def test_get_revised_exercise_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["revised_exercise_service"].get.return_value = Result.ok(MagicMock())
    await orch.get_revised_exercise("re_1")
    mocks["revised_exercise_service"].get.assert_called_once_with("re_1")


@pytest.mark.asyncio
async def test_get_revision_by_report_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["revised_exercise_service"].get_by_report_uid.return_value = Result.ok(None)
    await orch.get_revision_by_report("er_1")
    mocks["revised_exercise_service"].get_by_report_uid.assert_called_once_with("er_1")


@pytest.mark.asyncio
async def test_list_revised_exercises_delegates(
    built: tuple[SubmissionsOrchestrator, dict[str, MagicMock]],
) -> None:
    orch, mocks = built
    mocks["revised_exercise_service"].list_for_student.return_value = Result.ok([])
    await orch.list_revised_exercises("user-1")
    mocks["revised_exercise_service"].list_for_student.assert_called_once_with("user-1")
