"""Tests for TeacherReviewService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events.learning_loop_events import (
    ReportSubmitted,
    UserEntryApproved,
    UserEntryRevisionRequested,
)
from core.services.report.teacher_review_service import TeacherReviewService
from core.utils.result_simplified import Errors, Result

TEACHER_UID = "user_teacher_abc"
STUDENT_UID = "user_student_xyz"
SUBMISSION_UID = "es_submission_001"
REPORT_UID = "sr_report_001"
EXERCISE_UID = "ex_exercise_001"
GROUP_UID = "group_class_001"


def _make_report_backend():
    backend = MagicMock()
    backend.create_report_node = AsyncMock(return_value=Result.ok([]))
    backend.create_report_and_revised_exercise = AsyncMock(return_value=Result.ok([]))
    return backend


def _make_user_entry_backend():
    backend = MagicMock()
    backend.get_review_queue_by_groups = AsyncMock(return_value=Result.ok([]))
    backend.approve_and_get_linked_kus = AsyncMock(return_value=Result.ok([]))
    backend.get_entries_for_exercise_review = AsyncMock(return_value=Result.ok([]))
    backend.get_students_summary = AsyncMock(return_value=Result.ok([]))
    backend.get_student_entries_for_teacher = AsyncMock(return_value=Result.ok([]))
    backend.get_entry_detail_for_teacher = AsyncMock(return_value=Result.ok([]))
    backend.get_dashboard_stats = AsyncMock(return_value=Result.ok([]))
    backend.verify_teacher_has_group_access = AsyncMock(return_value=Result.ok([]))
    return backend


def _make_exercise_backend():
    backend = MagicMock()
    backend.get_exercises_with_submission_counts = AsyncMock(return_value=Result.ok([]))
    return backend


def _make_group_backend():
    backend = MagicMock()
    backend.get_teacher_groups_with_stats = AsyncMock(return_value=Result.ok([]))
    backend.get_group_detail = AsyncMock(return_value=Result.ok([]))
    return backend


def _make_event_bus():
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    return bus


def _make_report_mastery_service():
    svc = MagicMock()
    svc.propagate_mastery = AsyncMock(return_value=Result.ok(0))
    return svc


def _make_service(
    user_entry_backend=None,
    report_backend=None,
    exercise_backend=None,
    group_backend=None,
    ku_interaction_service=None,
    report_mastery_service=None,
    event_bus=None,
):
    return TeacherReviewService(
        user_entry_backend=user_entry_backend or _make_user_entry_backend(),
        report_backend=report_backend or _make_report_backend(),
        exercise_backend=exercise_backend or _make_exercise_backend(),
        group_backend=group_backend or _make_group_backend(),
        ku_interaction_service=ku_interaction_service or MagicMock(),
        report_mastery_service=report_mastery_service or _make_report_mastery_service(),
        event_bus=event_bus or _make_event_bus(),
    )


# ========================================================================
# TestVerifyTeacherHasGroupAccess
# ========================================================================


class TestVerifyTeacherHasGroupAccess:
    @pytest.mark.asyncio
    async def test_access_granted(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        service = _make_service(user_entry_backend=backend)

        result = await service._verify_teacher_has_group_access(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value is True

    @pytest.mark.asyncio
    async def test_access_denied_empty_records(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend)

        result = await service._verify_teacher_has_group_access(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert "does not have review access" in str(result.error)

    @pytest.mark.asyncio
    async def test_access_check_propagates_db_error(self):
        db_error = Errors.database("execute_query", "connection lost")
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.fail(db_error)
        service = _make_service(user_entry_backend=backend)

        result = await service._verify_teacher_has_group_access(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert result.error is db_error

    @pytest.mark.asyncio
    async def test_access_check_uses_correct_params(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        service = _make_service(user_entry_backend=backend)

        await service._verify_teacher_has_group_access(SUBMISSION_UID, TEACHER_UID)

        backend.verify_teacher_has_group_access.assert_awaited_once_with(
            SUBMISSION_UID, TEACHER_UID
        )


# ========================================================================
# TestGroupMembershipRejection — cross-group teachers must not pass
# ========================================================================


class TestGroupMembershipRejection:
    """A teacher with no shared active group with the student must be rejected
    (404) on all four state-changing review endpoints.

    Empty backend result models the Cypher not matching the
    ``(teacher)-[:OWNS]->(g:Group)<-[:MEMBER_OF]-(student)`` join.
    """

    @pytest.mark.asyncio
    async def test_submit_report_rejects_teacher_without_shared_group(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend)

        result = await service.submit_report(SUBMISSION_UID, TEACHER_UID, "feedback")

        assert result.is_error
        assert "does not have review access" in str(result.error)

    @pytest.mark.asyncio
    async def test_request_revision_rejects_teacher_without_shared_group(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend)

        result = await service.request_revision(SUBMISSION_UID, TEACHER_UID, "notes")

        assert result.is_error
        assert "does not have review access" in str(result.error)

    @pytest.mark.asyncio
    async def test_approve_report_rejects_teacher_without_shared_group(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert "does not have review access" in str(result.error)


# ========================================================================
# TestSubmitReport
# ========================================================================


class TestSubmitReport:
    @pytest.mark.asyncio
    async def test_success(self):
        backend = _make_user_entry_backend()
        report_backend = _make_report_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        report_backend.create_report_node.return_value = Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": "completed",
                    "student_uid": STUDENT_UID,
                    "report_entity_uid": REPORT_UID,
                }
            ]
        )
        service = _make_service(user_entry_backend=backend, report_backend=report_backend)

        result = await service.submit_report(SUBMISSION_UID, TEACHER_UID, "Great work!")

        assert not result.is_error
        assert result.value["submission_uid"] == SUBMISSION_UID
        assert result.value["status"] == "completed"
        assert result.value["feedback_submitted"] is True
        assert "report_uid" in result.value

    @pytest.mark.asyncio
    async def test_access_denied(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend)

        result = await service.submit_report(SUBMISSION_UID, TEACHER_UID, "feedback")

        assert result.is_error
        assert "does not have review access" in str(result.error)

    @pytest.mark.asyncio
    async def test_main_query_db_error(self):
        db_error = Errors.database("execute_query", "write failure")
        backend = _make_user_entry_backend()
        report_backend = _make_report_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        report_backend.create_report_node.return_value = Result.fail(db_error)
        service = _make_service(user_entry_backend=backend, report_backend=report_backend)

        result = await service.submit_report(SUBMISSION_UID, TEACHER_UID, "feedback")

        assert result.is_error
        assert result.error is db_error

    @pytest.mark.asyncio
    async def test_empty_records_returns_invalid_transition(self):
        """Empty results after access check = status guard rejected the transition."""
        backend = _make_user_entry_backend()
        report_backend = _make_report_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        report_backend.create_report_node.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend, report_backend=report_backend)

        result = await service.submit_report(SUBMISSION_UID, TEACHER_UID, "feedback")

        assert result.is_error
        assert "reviewable status" in str(result.error)

    @pytest.mark.asyncio
    async def test_publishes_report_submitted_event(self):
        backend = _make_user_entry_backend()
        report_backend = _make_report_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        report_backend.create_report_node.return_value = Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": "completed",
                    "student_uid": STUDENT_UID,
                    "report_entity_uid": REPORT_UID,
                }
            ]
        )
        event_bus = _make_event_bus()
        service = _make_service(
            user_entry_backend=backend, report_backend=report_backend, event_bus=event_bus
        )

        await service.submit_report(SUBMISSION_UID, TEACHER_UID, "Good job")

        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert isinstance(event, ReportSubmitted)
        assert event.submission_uid == SUBMISSION_UID
        assert event.teacher_uid == TEACHER_UID
        assert event.student_uid == STUDENT_UID

    @pytest.mark.asyncio
    async def test_null_student_uid_defaults_to_empty(self):
        backend = _make_user_entry_backend()
        report_backend = _make_report_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        report_backend.create_report_node.return_value = Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": "completed",
                    "student_uid": None,
                    "report_entity_uid": REPORT_UID,
                }
            ]
        )
        event_bus = _make_event_bus()
        service = _make_service(
            user_entry_backend=backend, report_backend=report_backend, event_bus=event_bus
        )

        await service.submit_report(SUBMISSION_UID, TEACHER_UID, "feedback")

        event = event_bus.publish_async.call_args[0][0]
        assert event.student_uid == ""


# ========================================================================
# TestRequestRevision
# ========================================================================


class TestRequestRevision:
    @pytest.mark.asyncio
    async def test_success(self):
        backend = _make_user_entry_backend()
        report_backend = _make_report_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        report_backend.create_report_node.return_value = Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": "revision_requested",
                    "student_uid": STUDENT_UID,
                    "report_entity_uid": REPORT_UID,
                }
            ]
        )
        service = _make_service(user_entry_backend=backend, report_backend=report_backend)

        result = await service.request_revision(SUBMISSION_UID, TEACHER_UID, "Fix section 2")

        assert not result.is_error
        assert result.value["submission_uid"] == SUBMISSION_UID
        assert result.value["revision_requested"] is True
        assert "report_uid" in result.value

    @pytest.mark.asyncio
    async def test_access_denied(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend)

        result = await service.request_revision(SUBMISSION_UID, TEACHER_UID, "notes")

        assert result.is_error
        assert "does not have review access" in str(result.error)

    @pytest.mark.asyncio
    async def test_main_query_db_error(self):
        db_error = Errors.database("execute_query", "timeout")
        backend = _make_user_entry_backend()
        report_backend = _make_report_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        report_backend.create_report_node.return_value = Result.fail(db_error)
        service = _make_service(user_entry_backend=backend, report_backend=report_backend)

        result = await service.request_revision(SUBMISSION_UID, TEACHER_UID, "notes")

        assert result.is_error
        assert result.error is db_error

    @pytest.mark.asyncio
    async def test_empty_records_returns_invalid_transition(self):
        """Empty results after access check = status guard rejected the transition."""
        backend = _make_user_entry_backend()
        report_backend = _make_report_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        report_backend.create_report_node.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend, report_backend=report_backend)

        result = await service.request_revision(SUBMISSION_UID, TEACHER_UID, "notes")

        assert result.is_error
        assert "revisable status" in str(result.error)

    @pytest.mark.asyncio
    async def test_publishes_revision_requested_event(self):
        backend = _make_user_entry_backend()
        report_backend = _make_report_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        report_backend.create_report_node.return_value = Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": "revision_requested",
                    "student_uid": STUDENT_UID,
                    "report_entity_uid": REPORT_UID,
                }
            ]
        )
        event_bus = _make_event_bus()
        service = _make_service(
            user_entry_backend=backend, report_backend=report_backend, event_bus=event_bus
        )

        await service.request_revision(SUBMISSION_UID, TEACHER_UID, "Fix section 2")

        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert isinstance(event, UserEntryRevisionRequested)
        assert event.entity_uid == SUBMISSION_UID
        assert event.revision_notes == "Fix section 2"

    @pytest.mark.asyncio
    async def test_null_student_uid_defaults_to_empty(self):
        backend = _make_user_entry_backend()
        report_backend = _make_report_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        report_backend.create_report_node.return_value = Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": "revision_requested",
                    "student_uid": None,
                    "report_entity_uid": REPORT_UID,
                }
            ]
        )
        event_bus = _make_event_bus()
        service = _make_service(
            user_entry_backend=backend, report_backend=report_backend, event_bus=event_bus
        )

        await service.request_revision(SUBMISSION_UID, TEACHER_UID, "notes")

        event = event_bus.publish_async.call_args[0][0]
        assert event.student_uid == ""


# ========================================================================
# TestApproveReport
# ========================================================================


class TestApproveReport:
    @pytest.mark.asyncio
    async def test_success_no_linked_kus(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        backend.approve_and_get_linked_kus.return_value = Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": "completed",
                    "student_uid": STUDENT_UID,
                    "linked_ku_uids": [],
                }
            ]
        )
        service = _make_service(user_entry_backend=backend)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value["approved"] is True
        assert result.value["mastered_ku_count"] == 0

    @pytest.mark.asyncio
    async def test_success_with_linked_kus_mastered(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        backend.approve_and_get_linked_kus.return_value = Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": "completed",
                    "student_uid": STUDENT_UID,
                    "linked_ku_uids": ["ku_math_001", "ku_math_002"],
                }
            ]
        )
        mastery_service = _make_report_mastery_service()
        mastery_service.propagate_mastery = AsyncMock(return_value=Result.ok(2))
        service = _make_service(user_entry_backend=backend, report_mastery_service=mastery_service)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value["mastered_ku_count"] == 2
        mastery_service.propagate_mastery.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_partial_mastery_failure(self):
        """When propagate_mastery returns partial count, result reflects it."""
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        backend.approve_and_get_linked_kus.return_value = Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": "completed",
                    "student_uid": STUDENT_UID,
                    "linked_ku_uids": ["ku_ok", "ku_fail"],
                }
            ]
        )
        mastery_service = _make_report_mastery_service()
        mastery_service.propagate_mastery = AsyncMock(return_value=Result.ok(1))
        service = _make_service(user_entry_backend=backend, report_mastery_service=mastery_service)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value["mastered_ku_count"] == 1

    @pytest.mark.asyncio
    async def test_access_denied(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert "does not have review access" in str(result.error)

    @pytest.mark.asyncio
    async def test_main_query_db_error(self):
        db_error = Errors.database("execute_query", "failure")
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        backend.approve_and_get_linked_kus.return_value = Result.fail(db_error)
        service = _make_service(user_entry_backend=backend)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_empty_records_returns_invalid_transition(self):
        """Empty results after access check = status guard rejected the transition."""
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        backend.approve_and_get_linked_kus.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert "approvable status" in str(result.error)

    @pytest.mark.asyncio
    async def test_publishes_submission_approved_event(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        backend.approve_and_get_linked_kus.return_value = Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": "completed",
                    "student_uid": STUDENT_UID,
                    "linked_ku_uids": [],
                }
            ]
        )
        event_bus = _make_event_bus()
        service = _make_service(user_entry_backend=backend, event_bus=event_bus)

        await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert isinstance(event, UserEntryApproved)
        assert event.entity_uid == SUBMISSION_UID
        assert event.mastered_ku_count == 0

    @pytest.mark.asyncio
    async def test_no_mastery_without_ku_service(self):
        backend = _make_user_entry_backend()
        backend.verify_teacher_has_group_access.return_value = Result.ok([{"has_access": True}])
        backend.approve_and_get_linked_kus.return_value = Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": "completed",
                    "student_uid": STUDENT_UID,
                    "linked_ku_uids": ["ku_math_001"],
                }
            ]
        )
        service = _make_service(user_entry_backend=backend, ku_interaction_service=None)

        result = await service.approve_report(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value["mastered_ku_count"] == 0


# ========================================================================
# TestGetReviewQueue
# ========================================================================


class TestGetReviewQueue:
    @pytest.mark.asyncio
    async def test_returns_items(self):
        # Backend (get_review_queue_by_groups) returns rows keyed on
        # entry_uid + exercise_title; service remaps to ReviewQueueItem
        # shape (submission_uid + exercise_name).
        records = [
            {
                "entry_uid": SUBMISSION_UID,
                "title": "Essay 1",
                "status": "submitted",
                "entity_type": "user_entry",
                "submitted_at": "2026-03-20T10:00:00",
                "student_uid": STUDENT_UID,
                "student_name": "Alice",
                "exercise_uid": EXERCISE_UID,
                "exercise_title": "Essay Exercise",
                "due_date": None,
                "original_filename": None,
                "revision": 1,
                "group_uid": GROUP_UID,
                "feedback_count": 2,
            }
        ]
        backend = _make_user_entry_backend()
        backend.get_review_queue_by_groups.return_value = Result.ok(records)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_review_queue(TEACHER_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["submission_uid"] == SUBMISSION_UID
        assert result.value[0]["exercise_name"] == "Essay Exercise"
        assert result.value[0]["feedback_count"] == 2

    @pytest.mark.asyncio
    async def test_empty_queue(self):
        service = _make_service()

        result = await service.get_review_queue(TEACHER_UID)

        assert not result.is_error
        assert result.value == []

    @pytest.mark.asyncio
    async def test_status_filter_wrapped_as_list(self):
        backend = _make_user_entry_backend()
        service = _make_service(user_entry_backend=backend)

        await service.get_review_queue(TEACHER_UID, status_filter="submitted")

        backend.get_review_queue_by_groups.assert_awaited_once_with(
            TEACHER_UID, ["submitted"], None
        )

    @pytest.mark.asyncio
    async def test_no_status_filter_passes_none(self):
        backend = _make_user_entry_backend()
        service = _make_service(user_entry_backend=backend)

        await service.get_review_queue(TEACHER_UID)

        backend.get_review_queue_by_groups.assert_awaited_once_with(TEACHER_UID, None, None)

    @pytest.mark.asyncio
    async def test_student_scope_passed_through(self):
        """The per-student Needs Review surface reads the SAME queue query —
        the student scope must reach the backend, not be re-filtered in the
        service (that is how the queue/student-page drift was born)."""
        backend = _make_user_entry_backend()
        service = _make_service(user_entry_backend=backend)

        await service.get_review_queue(TEACHER_UID, student_uid=STUDENT_UID)

        backend.get_review_queue_by_groups.assert_awaited_once_with(TEACHER_UID, None, STUDENT_UID)

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "timeout")
        backend = _make_user_entry_backend()
        backend.get_review_queue_by_groups.return_value = Result.fail(db_error)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_review_queue(TEACHER_UID)

        assert result.is_error
        assert result.error is db_error

    @pytest.mark.asyncio
    async def test_cross_teacher_access_returns_empty_queue(self):
        """SECURITY: Teacher with no group sharing the entry sees empty queue.

        Backend ``get_review_queue_by_groups`` returns [] when the teacher
        does not own a group that has been ``SHARED_WITH_GROUP`` by any
        ``teacher_review`` UserEntry — modeling the cross-classroom case
        where the Cypher anchor ``(teacher)-[:OWNS]->(g:Group)
        <-[:SHARED_WITH_GROUP]-(entry)`` doesn't match.
        """
        backend = _make_user_entry_backend()
        backend.get_review_queue_by_groups.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend)

        result = await service.get_review_queue("user_other_teacher")

        assert not result.is_error
        assert result.value == []


# ========================================================================
# TestGetSubmissionDetail
# ========================================================================


class TestGetSubmissionDetail:
    @pytest.mark.asyncio
    async def test_returns_detail(self):
        records = [
            {
                "uid": SUBMISSION_UID,
                "title": "Essay 1",
                "content": "My essay content",
                "processed_content": "Processed content",
                "original_filename": "essay.pdf",
                "entity_type": "user_entry",
                "status": "submitted",
                "created_at": "2026-03-20T10:00:00",
                "student_uid": STUDENT_UID,
                "student_name": "Alice",
                "exercise_uid": EXERCISE_UID,
                "exercise_title": "Essay Exercise",
                "exercise_instructions": "Write an essay",
            }
        ]
        backend = _make_user_entry_backend()
        backend.get_entry_detail_for_teacher.return_value = Result.ok(records)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_submission_detail(SUBMISSION_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value["uid"] == SUBMISSION_UID
        assert result.value["exercise_instructions"] == "Write an essay"

    @pytest.mark.asyncio
    async def test_not_found_when_no_access(self):
        service = _make_service()

        result = await service.get_submission_detail(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert "not found or not shared with teacher" in str(result.error)

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "timeout")
        backend = _make_user_entry_backend()
        backend.get_entry_detail_for_teacher.return_value = Result.fail(db_error)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_submission_detail(SUBMISSION_UID, TEACHER_UID)

        assert result.is_error
        assert result.error is db_error

    @pytest.mark.asyncio
    async def test_passes_correct_params(self):
        backend = _make_user_entry_backend()
        service = _make_service(user_entry_backend=backend)

        await service.get_submission_detail(SUBMISSION_UID, TEACHER_UID)

        backend.get_entry_detail_for_teacher.assert_awaited_once_with(SUBMISSION_UID, TEACHER_UID)

    @pytest.mark.asyncio
    async def test_cross_teacher_access_returns_not_found(self):
        """SECURITY: Teacher outside the entry's group → 404 (no content leak).

        Backend ``get_entry_detail_for_teacher`` returns [] when the entry
        isn't SHARED_WITH_GROUP an active group the teacher owns. Service
        maps empty → ``Errors.not_found`` — indistinguishable from
        "submission does not exist", so cross-classroom probing can't
        confirm the entry's existence.
        """
        backend = _make_user_entry_backend()
        backend.get_entry_detail_for_teacher.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend)

        result = await service.get_submission_detail(SUBMISSION_UID, "user_other_teacher")

        assert result.is_error
        assert "not found or not shared with teacher" in str(result.error)


# ========================================================================
# TestGetDashboardStats
# ========================================================================


class TestGetDashboardStats:
    @pytest.mark.asyncio
    async def test_returns_stats(self):
        records = [
            {
                "pending_count": 5,
                "total_students": 8,
                "total_exercises": 3,
                "total_groups": 2,
            }
        ]
        backend = _make_user_entry_backend()
        backend.get_dashboard_stats.return_value = Result.ok(records)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_dashboard_stats(TEACHER_UID)

        assert not result.is_error
        assert result.value["pending_count"] == 5
        assert result.value["total_students"] == 8

    @pytest.mark.asyncio
    async def test_returns_zero_defaults_when_no_records(self):
        service = _make_service()

        result = await service.get_dashboard_stats(TEACHER_UID)

        assert not result.is_error
        assert result.value["pending_count"] == 0
        assert result.value["total_students"] == 0
        assert result.value["total_exercises"] == 0
        assert result.value["total_groups"] == 0

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "timeout")
        backend = _make_user_entry_backend()
        backend.get_dashboard_stats.return_value = Result.fail(db_error)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_dashboard_stats(TEACHER_UID)

        assert result.is_error
        assert result.error is db_error

    @pytest.mark.asyncio
    async def test_cross_teacher_sees_zero_pending_and_students(self):
        """SECURITY: Teacher with no SHARED_WITH_GROUP entries → zero counts.

        Backend Cypher returns a single record with all counts at 0 when the
        teacher owns no groups and/or no entries are shared with them — the
        Model-B scoping on ``pending_count`` and ``total_students`` makes
        cross-classroom probing useless (a teacher can't tell whether
        another classroom has activity).
        """
        records = [
            {
                "pending_count": 0,
                "total_students": 0,
                "total_exercises": 0,
                "total_groups": 0,
            }
        ]
        backend = _make_user_entry_backend()
        backend.get_dashboard_stats.return_value = Result.ok(records)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_dashboard_stats("user_other_teacher")

        assert not result.is_error
        assert result.value["pending_count"] == 0
        assert result.value["total_students"] == 0


# ========================================================================
# TestGetExercisesWithSubmissionCounts
# ========================================================================


class TestGetExercisesWithSubmissionCounts:
    @pytest.mark.asyncio
    async def test_returns_exercises(self):
        records = [
            {
                "uid": EXERCISE_UID,
                "title": "Essay Exercise",
                "scope": "group",
                "created_at": "2026-03-01T09:00:00",
                "total_count": 10,
                "reviewed_count": 7,
                "pending_count": 3,
            }
        ]
        backend = _make_exercise_backend()
        backend.get_exercises_with_submission_counts.return_value = Result.ok(records)
        service = _make_service(exercise_backend=backend)

        result = await service.get_exercises_with_submission_counts(TEACHER_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["pending_count"] == 3

    @pytest.mark.asyncio
    async def test_empty_list(self):
        service = _make_service()

        result = await service.get_exercises_with_submission_counts(TEACHER_UID)

        assert not result.is_error
        assert result.value == []

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        backend = _make_exercise_backend()
        backend.get_exercises_with_submission_counts.return_value = Result.fail(db_error)
        service = _make_service(exercise_backend=backend)

        result = await service.get_exercises_with_submission_counts(TEACHER_UID)

        assert result.is_error


# ========================================================================
# TestGetSubmissionsForExercise
# ========================================================================


class TestGetSubmissionsForExercise:
    @pytest.mark.asyncio
    async def test_returns_submissions(self):
        records = [
            {
                "uid": SUBMISSION_UID,
                "title": "My Essay",
                "original_filename": "essay.pdf",
                "status": "submitted",
                "created_at": "2026-03-20T10:00:00",
                "student_uid": STUDENT_UID,
                "student_name": "Alice",
                "feedback_count": 1,
            }
        ]
        backend = _make_user_entry_backend()
        backend.get_entries_for_exercise_review.return_value = Result.ok(records)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_submissions_for_exercise(EXERCISE_UID, TEACHER_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["feedback_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_list(self):
        service = _make_service()

        result = await service.get_submissions_for_exercise(EXERCISE_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value == []

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        backend = _make_user_entry_backend()
        backend.get_entries_for_exercise_review.return_value = Result.fail(db_error)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_submissions_for_exercise(EXERCISE_UID, TEACHER_UID)

        assert result.is_error


# ========================================================================
# TestGetStudentsSummary
# ========================================================================


class TestGetStudentsSummary:
    @pytest.mark.asyncio
    async def test_returns_students(self):
        records = [
            {
                "student_uid": STUDENT_UID,
                "student_name": "Alice",
                "submission_count": 5,
                "reviewed_count": 3,
                "pending_count": 2,
            }
        ]
        backend = _make_user_entry_backend()
        backend.get_students_summary.return_value = Result.ok(records)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_students_summary(TEACHER_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["pending_count"] == 2

    @pytest.mark.asyncio
    async def test_empty_list(self):
        service = _make_service()

        result = await service.get_students_summary(TEACHER_UID)

        assert not result.is_error
        assert result.value == []

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        backend = _make_user_entry_backend()
        backend.get_students_summary.return_value = Result.fail(db_error)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_students_summary(TEACHER_UID)

        assert result.is_error


# ========================================================================
# TestGetStudentSubmissions
# ========================================================================


class TestGetStudentSubmissions:
    @pytest.mark.asyncio
    async def test_returns_submissions(self):
        records = [
            {
                "uid": SUBMISSION_UID,
                "title": "Essay 1",
                "original_filename": "essay.pdf",
                "status": "submitted",
                "created_at": "2026-03-20T10:00:00",
                "feedback_count": 0,
                "exercise_uid": EXERCISE_UID,
                "exercise_title": "Essay Exercise",
            }
        ]
        backend = _make_user_entry_backend()
        backend.get_student_entries_for_teacher.return_value = Result.ok(records)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_student_submissions(TEACHER_UID, STUDENT_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["exercise_uid"] == EXERCISE_UID

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        backend = _make_user_entry_backend()
        backend.get_student_entries_for_teacher.return_value = Result.fail(db_error)
        service = _make_service(user_entry_backend=backend)

        result = await service.get_student_submissions(TEACHER_UID, STUDENT_UID)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_cross_teacher_access_returns_empty_list(self):
        """SECURITY: Teacher with no shared active group → empty student history.

        Backend ``get_student_entries_for_teacher`` returns [] when the
        Model-A anchor ``(teacher)-[:OWNS]->(g:Group {is_active:true})
        <-[:MEMBER_OF]-(student)`` doesn't match. Service surface returns
        an empty list — indistinguishable from a genuinely empty per-student
        history. No content leak across classrooms.
        """
        backend = _make_user_entry_backend()
        backend.get_student_entries_for_teacher.return_value = Result.ok([])
        service = _make_service(user_entry_backend=backend)

        result = await service.get_student_submissions("user_other_teacher", STUDENT_UID)

        assert not result.is_error
        assert result.value == []


# ========================================================================
# TestGetTeacherGroupsWithStats
# ========================================================================


class TestGetTeacherGroupsWithStats:
    @pytest.mark.asyncio
    async def test_returns_groups(self):
        records = [
            {
                "uid": GROUP_UID,
                "name": "Math 101",
                "description": "Intro to math",
                "is_active": True,
                "member_count": 15,
                "exercise_count": 4,
                "pending_count": 6,
            }
        ]
        backend = _make_group_backend()
        backend.get_teacher_groups_with_stats.return_value = Result.ok(records)
        service = _make_service(group_backend=backend)

        result = await service.get_teacher_groups_with_stats(TEACHER_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["member_count"] == 15

    @pytest.mark.asyncio
    async def test_null_counts_default_to_zero(self):
        records = [
            {
                "uid": GROUP_UID,
                "name": "Empty Group",
                "description": None,
                "is_active": True,
                "member_count": None,
                "exercise_count": None,
                "pending_count": None,
            }
        ]
        backend = _make_group_backend()
        backend.get_teacher_groups_with_stats.return_value = Result.ok(records)
        service = _make_service(group_backend=backend)

        result = await service.get_teacher_groups_with_stats(TEACHER_UID)

        assert not result.is_error
        assert result.value[0]["member_count"] == 0
        assert result.value[0]["exercise_count"] == 0
        assert result.value[0]["pending_count"] == 0

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        backend = _make_group_backend()
        backend.get_teacher_groups_with_stats.return_value = Result.fail(db_error)
        service = _make_service(group_backend=backend)

        result = await service.get_teacher_groups_with_stats(TEACHER_UID)

        assert result.is_error


# ========================================================================
# TestGetGroupDetail
# ========================================================================


class TestGetGroupDetail:
    @pytest.mark.asyncio
    async def test_returns_members(self):
        records = [
            {
                "user_uid": STUDENT_UID,
                "user_name": "Alice",
                "role": "student",
                "joined_at": "2026-03-01T09:00:00",
                "submission_count": 5,
                "reviewed_count": 3,
                "pending_count": 2,
            }
        ]
        backend = _make_group_backend()
        backend.get_group_detail.return_value = Result.ok(records)
        service = _make_service(group_backend=backend)

        result = await service.get_group_detail(GROUP_UID, TEACHER_UID)

        assert not result.is_error
        assert len(result.value) == 1
        assert result.value[0]["user_uid"] == STUDENT_UID

    @pytest.mark.asyncio
    async def test_null_counts_default_to_zero(self):
        records = [
            {
                "user_uid": STUDENT_UID,
                "user_name": "Bob",
                "role": "student",
                "joined_at": "2026-03-01T09:00:00",
                "submission_count": None,
                "reviewed_count": None,
                "pending_count": None,
            }
        ]
        backend = _make_group_backend()
        backend.get_group_detail.return_value = Result.ok(records)
        service = _make_service(group_backend=backend)

        result = await service.get_group_detail(GROUP_UID, TEACHER_UID)

        assert not result.is_error
        assert result.value[0]["submission_count"] == 0
        assert result.value[0]["reviewed_count"] == 0
        assert result.value[0]["pending_count"] == 0

    @pytest.mark.asyncio
    async def test_db_error_propagated(self):
        db_error = Errors.database("execute_query", "failure")
        backend = _make_group_backend()
        backend.get_group_detail.return_value = Result.fail(db_error)
        service = _make_service(group_backend=backend)

        result = await service.get_group_detail(GROUP_UID, TEACHER_UID)

        assert result.is_error
