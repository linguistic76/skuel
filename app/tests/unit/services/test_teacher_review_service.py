"""Tests for TeacherReviewService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events.submission_events import (
    ReportSubmitted,
    SubmissionApproved,
    SubmissionRevisionRequested,
)
from core.services.report.teacher_review_service import TeacherReviewService
from core.utils.result_simplified import Errors, Result


TEACHER_UID = "user_teacher_abc"
STUDENT_UID = "user_student_xyz"
SUBMISSION_UID = "es_submission_001"
REPORT_UID = "sr_report_001"
EXERCISE_UID = "ex_exercise_001"
GROUP_UID = "group_class_001"


def _make_service(executor=None, ku_interaction_service=None, event_bus=None):
    executor = executor or MagicMock()
    if not hasattr(executor, "execute_query"):
        executor.execute_query = AsyncMock(return_value=Result.ok([]))
    return TeacherReviewService(
        executor=executor,
        ku_interaction_service=ku_interaction_service,
        event_bus=event_bus,
    )


def _make_executor(*side_effects):
    """Create executor with execute_query returning given side effects in order."""
    executor = MagicMock()
    if side_effects:
        executor.execute_query = AsyncMock(side_effect=list(side_effects))
    else:
        executor.execute_query = AsyncMock(return_value=Result.ok([]))
    return executor


def _make_event_bus():
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    return bus


# ========================================================================
# TestVerifyTeacherAccess
# ========================================================================


class TestVerifyTeacherAccess:
    @pytest.mark.asyncio
    async def test_access_granted(self):
        executor = _make_executor(Result.ok([{"has_access": True}]))
        service = _make_service(executor=executor)

        result = await service._verify_teacher_access(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value is True

    @pytest.mark.asyncio
    async def test_access_denied_empty_records(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        result = await service._verify_teacher_access(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert "does not have review access" in str(result.error)

    @pytest.mark.asyncio
    async def test_access_check_propagates_db_error(self):
        db_error = Errors.database("execute_query", "connection lost")
        executor = _make_executor(Result.fail(db_error))
        service = _make_service(executor=executor)

        result = await service._verify_teacher_access(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert result.error is db_error

    @pytest.mark.asyncio
    async def test_access_check_uses_correct_params(self):
        executor = _make_executor(Result.ok([{"has_access": True}]))
        service = _make_service(executor=executor)

        await service._verify_teacher_access(SUBMISSION_UID, TEACHER_UID)

        call_args = executor.execute_query.call_args
        params = call_args[0][1]
        assert params["teacher_uid"] == TEACHER_UID
        assert params["report_uid"] == SUBMISSION_UID


# ========================================================================
# TestSubmitReport
# ========================================================================


class TestSubmitReport:
    @pytest.mark.asyncio
    async def test_success(self):
        executor = _make_executor(
            # _verify_teacher_access
            Result.ok([{"has_access": True}]),
            # main query
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "completed",
                "student_uid": STUDENT_UID,
                "report_entity_uid": REPORT_UID,
            }]),
        )
        service = _make_service(executor=executor)

        result = await service.submit_report(SUBMISSION_UID, TEACHER_UID, "Great work!")

        assert not result.is_error
        assert result.value["ku_uid"] == SUBMISSION_UID
        assert result.value["status"] == "completed"
        assert result.value["feedback_submitted"] is True
        assert "report_uid" in result.value

    @pytest.mark.asyncio
    async def test_access_denied(self):
        executor = _make_executor(Result.ok([]))  # access check fails
        service = _make_service(executor=executor)

        result = await service.submit_report(SUBMISSION_UID, TEACHER_UID, "feedback")

        assert result.is_error
        assert "does not have review access" in str(result.error)

    @pytest.mark.asyncio
    async def test_main_query_db_error(self):
        db_error = Errors.database("execute_query", "write failure")
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.fail(db_error),
        )
        service = _make_service(executor=executor)

        result = await service.submit_report(SUBMISSION_UID, TEACHER_UID, "feedback")

        assert result.is_error
        assert result.error is db_error

    @pytest.mark.asyncio
    async def test_main_query_empty_records(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([]),  # submission not found
        )
        service = _make_service(executor=executor)

        result = await service.submit_report(SUBMISSION_UID, TEACHER_UID, "feedback")

        assert result.is_error
        assert "not found" in str(result.error)

    @pytest.mark.asyncio
    async def test_publishes_report_submitted_event(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "completed",
                "student_uid": STUDENT_UID,
                "report_entity_uid": REPORT_UID,
            }]),
        )
        event_bus = _make_event_bus()
        service = _make_service(executor=executor, event_bus=event_bus)

        await service.submit_report(SUBMISSION_UID, TEACHER_UID, "Good job")

        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert isinstance(event, ReportSubmitted)
        assert event.submission_uid == SUBMISSION_UID
        assert event.teacher_uid == TEACHER_UID
        assert event.student_uid == STUDENT_UID

    @pytest.mark.asyncio
    async def test_no_event_bus_does_not_raise(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "completed",
                "student_uid": STUDENT_UID,
                "report_entity_uid": REPORT_UID,
            }]),
        )
        service = _make_service(executor=executor, event_bus=None)

        result = await service.submit_report(SUBMISSION_UID, TEACHER_UID, "feedback")

        assert not result.is_error

    @pytest.mark.asyncio
    async def test_null_student_uid_defaults_to_empty(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "completed",
                "student_uid": None,
                "report_entity_uid": REPORT_UID,
            }]),
        )
        event_bus = _make_event_bus()
        service = _make_service(executor=executor, event_bus=event_bus)

        await service.submit_report(SUBMISSION_UID, TEACHER_UID, "feedback")

        event = event_bus.publish_async.call_args[0][0]
        assert event.student_uid == ""


# ========================================================================
# TestRequestRevision
# ========================================================================


class TestRequestRevision:
    @pytest.mark.asyncio
    async def test_success(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "revision_requested",
                "student_uid": STUDENT_UID,
                "report_entity_uid": REPORT_UID,
            }]),
        )
        service = _make_service(executor=executor)

        result = await service.request_revision(SUBMISSION_UID, TEACHER_UID, "Fix section 2")

        assert not result.is_error
        assert result.value["ku_uid"] == SUBMISSION_UID
        assert result.value["revision_requested"] is True
        assert "report_uid" in result.value

    @pytest.mark.asyncio
    async def test_access_denied(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        result = await service.request_revision(SUBMISSION_UID, TEACHER_UID, "notes")

        assert result.is_error
        assert "does not have review access" in str(result.error)

    @pytest.mark.asyncio
    async def test_main_query_db_error(self):
        db_error = Errors.database("execute_query", "timeout")
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.fail(db_error),
        )
        service = _make_service(executor=executor)

        result = await service.request_revision(SUBMISSION_UID, TEACHER_UID, "notes")

        assert result.is_error
        assert result.error is db_error

    @pytest.mark.asyncio
    async def test_empty_records_returns_not_found(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([]),
        )
        service = _make_service(executor=executor)

        result = await service.request_revision(SUBMISSION_UID, TEACHER_UID, "notes")

        assert result.is_error
        assert "not found" in str(result.error)

    @pytest.mark.asyncio
    async def test_publishes_revision_requested_event(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "revision_requested",
                "student_uid": STUDENT_UID,
                "report_entity_uid": REPORT_UID,
            }]),
        )
        event_bus = _make_event_bus()
        service = _make_service(executor=executor, event_bus=event_bus)

        await service.request_revision(SUBMISSION_UID, TEACHER_UID, "Fix section 2")

        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert isinstance(event, SubmissionRevisionRequested)
        assert event.submission_uid == SUBMISSION_UID
        assert event.revision_notes == "Fix section 2"

    @pytest.mark.asyncio
    async def test_null_student_uid_defaults_to_empty(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "revision_requested",
                "student_uid": None,
                "report_entity_uid": REPORT_UID,
            }]),
        )
        event_bus = _make_event_bus()
        service = _make_service(executor=executor, event_bus=event_bus)

        await service.request_revision(SUBMISSION_UID, TEACHER_UID, "notes")

        event = event_bus.publish_async.call_args[0][0]
        assert event.student_uid == ""


# ========================================================================
# TestApproveReport
# ========================================================================


class TestApproveReport:
    @pytest.mark.asyncio
    async def test_success_no_linked_kus(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "completed",
                "student_uid": STUDENT_UID,
                "linked_ku_uids": [],
            }]),
        )
        service = _make_service(executor=executor)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value["approved"] is True
        assert result.value["mastered_ku_count"] == 0

    @pytest.mark.asyncio
    async def test_success_with_linked_kus_mastered(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "completed",
                "student_uid": STUDENT_UID,
                "linked_ku_uids": ["ku_math_001", "ku_math_002"],
            }]),
        )
        ku_service = MagicMock()
        ku_service.mark_mastered = AsyncMock(return_value=Result.ok(True))
        service = _make_service(executor=executor, ku_interaction_service=ku_service)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value["mastered_ku_count"] == 2
        assert ku_service.mark_mastered.await_count == 2

    @pytest.mark.asyncio
    async def test_partial_mastery_failure(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "completed",
                "student_uid": STUDENT_UID,
                "linked_ku_uids": ["ku_ok", "ku_fail"],
            }]),
        )
        ku_service = MagicMock()
        ku_service.mark_mastered = AsyncMock(side_effect=[
            Result.ok(True),
            Result.fail(Errors.database("mark_mastered", "failed")),
        ])
        service = _make_service(executor=executor, ku_interaction_service=ku_service)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value["mastered_ku_count"] == 1

    @pytest.mark.asyncio
    async def test_access_denied(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert "does not have review access" in str(result.error)

    @pytest.mark.asyncio
    async def test_main_query_db_error(self):
        db_error = Errors.database("execute_query", "failure")
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.fail(db_error),
        )
        service = _make_service(executor=executor)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_empty_records_returns_not_found(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([]),
        )
        service = _make_service(executor=executor)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert "not found" in str(result.error)

    @pytest.mark.asyncio
    async def test_publishes_submission_approved_event(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "completed",
                "student_uid": STUDENT_UID,
                "linked_ku_uids": [],
            }]),
        )
        event_bus = _make_event_bus()
        service = _make_service(executor=executor, event_bus=event_bus)

        await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert isinstance(event, SubmissionApproved)
        assert event.submission_uid == SUBMISSION_UID
        assert event.mastered_ku_count == 0

    @pytest.mark.asyncio
    async def test_no_mastery_without_ku_service(self):
        executor = _make_executor(
            Result.ok([{"has_access": True}]),
            Result.ok([{
                "uid": SUBMISSION_UID,
                "status": "completed",
                "student_uid": STUDENT_UID,
                "linked_ku_uids": ["ku_math_001"],
            }]),
        )
        service = _make_service(executor=executor, ku_interaction_service=None)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value["mastered_ku_count"] == 0


# ========================================================================
# TestGetReviewQueue
# ========================================================================


class TestGetReviewQueue:
    @pytest.mark.asyncio
    async def test_returns_items(self):
        records = [{
            "ku_uid": SUBMISSION_UID,
            "title": "Essay 1",
            "status": "submitted",
            "entity_type": "exercise_submission",
            "submitted_at": "2026-03-20T10:00:00",
            "student_uid": STUDENT_UID,
            "student_name": "Alice",
            "project_uid": EXERCISE_UID,
            "project_name": "Essay Exercise",
            "due_date": None,
            "shared_at": "2026-03-20T09:00:00",
            "feedback_count": 0,
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_review_queue(TEACHER_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["ku_uid"] == SUBMISSION_UID

    @pytest.mark.asyncio
    async def test_empty_queue(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        result = await service.get_review_queue(TEACHER_UID)

        assert not result.is_error
        assert result.value == []

    @pytest.mark.asyncio
    async def test_status_filter_passed_as_param(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        await service.get_review_queue(TEACHER_UID, status_filter="submitted")

        params = executor.execute_query.call_args[0][1]
        assert params["status_filter"] == "submitted"

    @pytest.mark.asyncio
    async def test_ku_type_filter_passed_as_param(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        await service.get_review_queue(TEACHER_UID, ku_type_filter="exercise_submission")

        params = executor.execute_query.call_args[0][1]
        assert params["ku_type_filter"] == "exercise_submission"

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "timeout")
        executor = _make_executor(Result.fail(db_error))
        service = _make_service(executor=executor)

        result = await service.get_review_queue(TEACHER_UID)

        assert result.is_error
        assert result.error is db_error


# ========================================================================
# TestGetReportHistory
# ========================================================================


class TestGetReportHistory:
    @pytest.mark.asyncio
    async def test_returns_history(self):
        records = [{
            "uid": REPORT_UID,
            "title": "Feedback: es_submission_001",
            "content": "Nice work",
            "status": "completed",
            "created_at": "2026-03-20T12:00:00",
            "teacher_uid": TEACHER_UID,
            "teacher_name": "Prof Smith",
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_report_history(SUBMISSION_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["uid"] == REPORT_UID

    @pytest.mark.asyncio
    async def test_empty_history(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        result = await service.get_report_history(SUBMISSION_UID)

        assert not result.is_error
        assert result.value == []

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "read failure")
        executor = _make_executor(Result.fail(db_error))
        service = _make_service(executor=executor)

        result = await service.get_report_history(SUBMISSION_UID)

        assert result.is_error
        assert result.error is db_error


# ========================================================================
# TestGetSubmissionDetail
# ========================================================================


class TestGetSubmissionDetail:
    @pytest.mark.asyncio
    async def test_returns_detail(self):
        records = [{
            "uid": SUBMISSION_UID,
            "title": "Essay 1",
            "content": "My essay content",
            "processed_content": "Processed content",
            "original_filename": "essay.pdf",
            "entity_type": "exercise_submission",
            "status": "submitted",
            "created_at": "2026-03-20T10:00:00",
            "student_uid": STUDENT_UID,
            "student_name": "Alice",
            "exercise_uid": EXERCISE_UID,
            "exercise_title": "Essay Exercise",
            "exercise_instructions": "Write an essay",
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_submission_detail(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value["uid"] == SUBMISSION_UID
        assert result.value["exercise_instructions"] == "Write an essay"

    @pytest.mark.asyncio
    async def test_not_found_when_no_access(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        result = await service.get_submission_detail(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert "not found or not shared with teacher" in str(result.error)

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "timeout")
        executor = _make_executor(Result.fail(db_error))
        service = _make_service(executor=executor)

        result = await service.get_submission_detail(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert result.error is db_error

    @pytest.mark.asyncio
    async def test_passes_correct_params(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        await service.get_submission_detail(SUBMISSION_UID, TEACHER_UID)

        params = executor.execute_query.call_args[0][1]
        assert params["submission_uid"] == SUBMISSION_UID
        assert params["teacher_uid"] == TEACHER_UID


# ========================================================================
# TestGetDashboardStats
# ========================================================================


class TestGetDashboardStats:
    @pytest.mark.asyncio
    async def test_returns_stats(self):
        records = [{
            "pending_count": 5,
            "total_submissions": 20,
            "total_students": 8,
            "total_exercises": 3,
            "total_groups": 2,
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_dashboard_stats(TEACHER_UID)

        assert not result.is_error
        assert result.value["pending_count"] == 5
        assert result.value["total_students"] == 8

    @pytest.mark.asyncio
    async def test_returns_zero_defaults_when_no_records(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        result = await service.get_dashboard_stats(TEACHER_UID)

        assert not result.is_error
        assert result.value["pending_count"] == 0
        assert result.value["total_submissions"] == 0
        assert result.value["total_students"] == 0
        assert result.value["total_exercises"] == 0
        assert result.value["total_groups"] == 0

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "timeout")
        executor = _make_executor(Result.fail(db_error))
        service = _make_service(executor=executor)

        result = await service.get_dashboard_stats(TEACHER_UID)

        assert result.is_error
        assert result.error is db_error


# ========================================================================
# TestGetExercisesWithSubmissionCounts
# ========================================================================


class TestGetExercisesWithSubmissionCounts:
    @pytest.mark.asyncio
    async def test_returns_exercises(self):
        records = [{
            "uid": EXERCISE_UID,
            "title": "Essay Exercise",
            "scope": "group",
            "created_at": "2026-03-01T09:00:00",
            "total_count": 10,
            "reviewed_count": 7,
            "pending_count": 3,
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_exercises_with_submission_counts(TEACHER_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["pending_count"] == 3

    @pytest.mark.asyncio
    async def test_empty_list(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        result = await service.get_exercises_with_submission_counts(TEACHER_UID)

        assert not result.is_error
        assert result.value == []

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        executor = _make_executor(Result.fail(db_error))
        service = _make_service(executor=executor)

        result = await service.get_exercises_with_submission_counts(TEACHER_UID)

        assert result.is_error


# ========================================================================
# TestGetSubmissionsForExercise
# ========================================================================


class TestGetSubmissionsForExercise:
    @pytest.mark.asyncio
    async def test_returns_submissions(self):
        records = [{
            "uid": SUBMISSION_UID,
            "title": "My Essay",
            "original_filename": "essay.pdf",
            "status": "submitted",
            "created_at": "2026-03-20T10:00:00",
            "student_uid": STUDENT_UID,
            "student_name": "Alice",
            "feedback_count": 1,
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_submissions_for_exercise(EXERCISE_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["feedback_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_list(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        result = await service.get_submissions_for_exercise(EXERCISE_UID)

        assert not result.is_error
        assert result.value == []

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        executor = _make_executor(Result.fail(db_error))
        service = _make_service(executor=executor)

        result = await service.get_submissions_for_exercise(EXERCISE_UID)

        assert result.is_error


# ========================================================================
# TestGetStudentsSummary
# ========================================================================


class TestGetStudentsSummary:
    @pytest.mark.asyncio
    async def test_returns_students(self):
        records = [{
            "student_uid": STUDENT_UID,
            "student_name": "Alice",
            "submission_count": 5,
            "reviewed_count": 3,
            "pending_count": 2,
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_students_summary(TEACHER_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["pending_count"] == 2

    @pytest.mark.asyncio
    async def test_empty_list(self):
        executor = _make_executor(Result.ok([]))
        service = _make_service(executor=executor)

        result = await service.get_students_summary(TEACHER_UID)

        assert not result.is_error
        assert result.value == []

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        executor = _make_executor(Result.fail(db_error))
        service = _make_service(executor=executor)

        result = await service.get_students_summary(TEACHER_UID)

        assert result.is_error


# ========================================================================
# TestGetStudentSubmissions
# ========================================================================


class TestGetStudentSubmissions:
    @pytest.mark.asyncio
    async def test_returns_submissions(self):
        records = [{
            "uid": SUBMISSION_UID,
            "title": "Essay 1",
            "original_filename": "essay.pdf",
            "status": "submitted",
            "created_at": "2026-03-20T10:00:00",
            "feedback_count": 0,
            "exercise_uid": EXERCISE_UID,
            "exercise_title": "Essay Exercise",
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_student_submissions(TEACHER_UID, STUDENT_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["exercise_uid"] == EXERCISE_UID

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        executor = _make_executor(Result.fail(db_error))
        service = _make_service(executor=executor)

        result = await service.get_student_submissions(TEACHER_UID, STUDENT_UID)

        assert result.is_error


# ========================================================================
# TestGetTeacherGroupsWithStats
# ========================================================================


class TestGetTeacherGroupsWithStats:
    @pytest.mark.asyncio
    async def test_returns_groups(self):
        records = [{
            "uid": GROUP_UID,
            "name": "Math 101",
            "description": "Intro to math",
            "is_active": True,
            "member_count": 15,
            "exercise_count": 4,
            "pending_count": 6,
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_teacher_groups_with_stats(TEACHER_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["member_count"] == 15

    @pytest.mark.asyncio
    async def test_null_counts_default_to_zero(self):
        records = [{
            "uid": GROUP_UID,
            "name": "Empty Group",
            "description": None,
            "is_active": True,
            "member_count": None,
            "exercise_count": None,
            "pending_count": None,
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_teacher_groups_with_stats(TEACHER_UID)

        assert not result.is_error
        assert result.value[0]["member_count"] == 0
        assert result.value[0]["exercise_count"] == 0
        assert result.value[0]["pending_count"] == 0

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        executor = _make_executor(Result.fail(db_error))
        service = _make_service(executor=executor)

        result = await service.get_teacher_groups_with_stats(TEACHER_UID)

        assert result.is_error


# ========================================================================
# TestGetGroupDetail
# ========================================================================


class TestGetGroupDetail:
    @pytest.mark.asyncio
    async def test_returns_members(self):
        records = [{
            "user_uid": STUDENT_UID,
            "user_name": "Alice",
            "role": "student",
            "joined_at": "2026-03-01T09:00:00",
            "submission_count": 5,
            "reviewed_count": 3,
            "pending_count": 2,
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_group_detail(GROUP_UID, TEACHER_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["user_uid"] == STUDENT_UID

    @pytest.mark.asyncio
    async def test_null_counts_default_to_zero(self):
        records = [{
            "user_uid": STUDENT_UID,
            "user_name": "Bob",
            "role": "student",
            "joined_at": "2026-03-01T09:00:00",
            "submission_count": None,
            "reviewed_count": None,
            "pending_count": None,
        }]
        executor = _make_executor(Result.ok(records))
        service = _make_service(executor=executor)

        result = await service.get_group_detail(GROUP_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value[0]["submission_count"] == 0
        assert result.value[0]["reviewed_count"] == 0
        assert result.value[0]["pending_count"] == 0

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        executor = _make_executor(Result.fail(db_error))
        service = _make_service(executor=executor)

        result = await service.get_group_detail(GROUP_UID, TEACHER_UID)

        assert result.is_error
