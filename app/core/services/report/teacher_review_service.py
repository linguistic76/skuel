"""
Teacher Review Service
=======================

Manages the teacher review workflow for assigned submissions.

Reuses SHARES_WITH infrastructure. When a student submits an entity against
an ASSIGNED Exercise, the entity is auto-shared with the teacher.
The teacher's review queue = submissions shared with them via role="teacher".

When providing a report or requesting revision, an EXERCISE_REPORT Entity node
is created and linked to the submission via REPORT_FOR. This makes every
report round a first-class graph entity — searchable, queryable, and
supporting revision cycles.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
See: /docs/architecture/FOUR_PHASED_LEARNING_LOOP.md
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.submission_events import (
    ReportSubmitted,
    SubmissionApproved,
    SubmissionRevisionRequested,
)
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.enums.learning_enums import AssessmentOutcome, MasteryImpact
from core.ports.query_types import (
    ExerciseWithSubmissionCounts,
    GroupMemberProgress,
    ReportApprovalResult,
    ReportHistoryItem,
    ReportSubmitResult,
    RevisionRequestResult,
    StudentSubmissionItem,
    StudentSummaryItem,
    SubmissionForExercise,
    TeacherGroupStats,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import (
        ExerciseBackend,
        GroupBackend,
        SubmissionsBackend,
    )
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.ps.ps_mastery_service import PsMasteryService

logger = get_logger("skuel.services.teacher_review")


class TeacherReviewService:
    """Service for teacher review of student submissions."""

    def __init__(
        self,
        submissions_backend: "SubmissionsBackend",
        exercise_backend: "ExerciseBackend",
        group_backend: "GroupBackend",
        ku_interaction_service: "PsMasteryService",
        event_bus: "EventBusOperations",
    ) -> None:
        """
        Initialize the teacher review service.

        Args:
            submissions_backend: Backend for submission queries
            exercise_backend: Backend for exercise queries
            group_backend: Backend for group queries
            ku_interaction_service: KU interaction service for mastery updates
            event_bus: Event bus for publishing review events
        """
        self.submissions_backend = submissions_backend
        self.exercise_backend = exercise_backend
        self.group_backend = group_backend
        self.ku_interaction_service = ku_interaction_service
        self.event_bus = event_bus

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
        entity_type_filter: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get teacher's pending review queue.

        Returns submissions shared with the teacher via role="teacher",
        optionally filtered by status or entity_type. Includes count of
        existing feedback rounds per submission.

        Args:
            teacher_uid: Teacher UID
            status_filter: Optional status filter (e.g., "submitted")
            entity_type_filter: Optional entity_type filter (e.g., "exercise_submission")

        Returns:
            Result containing list of review items
        """
        result = await self.submissions_backend.get_review_queue(
            teacher_uid, status_filter, entity_type_filter
        )
        if result.is_error:
            return Result.fail(result)

        items = [
            {
                "ku_uid": record["ku_uid"],
                "title": record["title"],
                "status": record["status"],
                "entity_type": record["entity_type"],
                "submitted_at": record["submitted_at"],
                "student_uid": record["student_uid"],
                "student_name": record["student_name"],
                "exercise_uid": record["exercise_uid"],
                "exercise_name": record["exercise_name"],
                "due_date": record["due_date"],
                "shared_at": record["shared_at"],
                "feedback_count": record["feedback_count"],
            }
            for record in result.value
        ]

        return Result.ok(items)

    async def get_report_history(
        self,
        submission_uid: str,
    ) -> Result[list[ReportHistoryItem]]:
        """
        Get all EXERCISE_REPORT nodes linked to a submission via REPORT_FOR.

        Args:
            submission_uid: The submission UID

        Returns:
            Result containing list of report items ordered by creation date
        """
        result = await self.submissions_backend.get_report_history(submission_uid)
        if result.is_error:
            return Result.fail(result)

        items = [
            {
                "uid": record["uid"],
                "title": record["title"],
                "content": record["content"],
                "status": record["status"],
                "created_at": record["created_at"],
                "teacher_uid": record["teacher_uid"],
                "teacher_name": record["teacher_name"],
            }
            for record in result.value
        ]

        return Result.ok(items)

    async def submit_report(
        self,
        report_uid: str,
        teacher_uid: str,
        feedback: str,
    ) -> Result[ReportSubmitResult]:
        """
        Submit teacher report for an entity.

        Creates an EXERCISE_REPORT Entity node linked to the submission via REPORT_FOR.
        Also writes report to submission's report field (denormalized for quick access)
        and sets submission status to COMPLETED.

        Args:
            report_uid: Submission UID to provide report for
            teacher_uid: Teacher providing report
            feedback: ExerciseReport text

        Returns:
            Result containing report info
        """
        access_check = await self._verify_teacher_access(report_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check)

        report_entity_uid = UIDGenerator.generate_uid("sr")
        now = datetime.now().isoformat()

        allowed_from = [EntityStatus.PROCESSING.value]
        result = await self.submissions_backend.create_report_node(
            {
                "report_uid": report_uid,
                "report_entity_uid": report_entity_uid,
                "teacher_uid": teacher_uid,
                "feedback": feedback,
                "title": f"Feedback: {report_uid[:30]}",
                "entity_type": EntityType.EXERCISE_REPORT.value,
                "submission_status": EntityStatus.COMPLETED.value,
                "completed_status": EntityStatus.COMPLETED.value,
                "processor_type": ProcessorType.HUMAN.value,
                "assessment_outcome": AssessmentOutcome.APPROVED.value,
                "allowed_from_statuses": allowed_from,
                "now": now,
            }
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records:
            return Result.fail(
                Errors.validation(
                    message=(
                        f"Cannot submit report: submission {report_uid} is not in a "
                        f"reviewable status (expected one of {allowed_from})"
                    ),
                    field="status",
                )
            )

        student_uid = records[0]["student_uid"] or ""
        logger.info(
            f"Teacher {teacher_uid} submitted report {report_entity_uid} for submission {report_uid}"
        )

        await publish_event(
            self.event_bus,
            ReportSubmitted(
                submission_uid=report_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                report_uid=report_entity_uid,
            ),
            logger,
        )

        return Result.ok(
            {
                "ku_uid": str(records[0]["uid"]),
                "status": str(records[0]["status"]),
                "report_uid": report_entity_uid,
                "feedback_submitted": True,
            }
        )

    async def request_revision(
        self,
        report_uid: str,
        teacher_uid: str,
        notes: str,
    ) -> Result[RevisionRequestResult]:
        """
        Request revision for a student submission.

        Creates an EXERCISE_REPORT Entity node with revision notes, linked via REPORT_FOR.
        Sets submission status to REVISION_REQUESTED.

        Args:
            report_uid: Submission UID needing revision
            teacher_uid: Teacher requesting revision
            notes: Revision notes/instructions

        Returns:
            Result containing revision info
        """
        access_check = await self._verify_teacher_access(report_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check)

        report_entity_uid = UIDGenerator.generate_uid("sr")
        now = datetime.now().isoformat()

        allowed_from = [EntityStatus.COMPLETED.value]
        result = await self.submissions_backend.create_report_node(
            {
                "report_uid": report_uid,
                "report_entity_uid": report_entity_uid,
                "teacher_uid": teacher_uid,
                "feedback": notes,
                "title": f"Revision request: {report_uid[:30]}",
                "entity_type": EntityType.EXERCISE_REPORT.value,
                "submission_status": EntityStatus.REVISION_REQUESTED.value,
                "completed_status": EntityStatus.COMPLETED.value,
                "processor_type": ProcessorType.HUMAN.value,
                "assessment_outcome": AssessmentOutcome.NEEDS_REVISION.value,
                "allowed_from_statuses": allowed_from,
                "now": now,
            }
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records:
            return Result.fail(
                Errors.validation(
                    message=(
                        f"Cannot request revision: submission {report_uid} is not in a "
                        f"revisable status (expected one of {allowed_from})"
                    ),
                    field="status",
                )
            )

        student_uid = records[0]["student_uid"] or ""
        logger.info(
            f"Teacher {teacher_uid} requested revision {report_entity_uid} for submission {report_uid}"
        )

        await publish_event(
            self.event_bus,
            SubmissionRevisionRequested(
                submission_uid=report_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                revision_notes=notes,
                metadata={"report_uid": report_entity_uid},
            ),
            logger,
        )

        return Result.ok(
            {
                "ku_uid": str(records[0]["uid"]),
                "status": str(records[0]["status"]),
                "report_uid": report_entity_uid,
                "revision_requested": True,
            }
        )

    async def approve_report(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[ReportApprovalResult]:
        """
        Approve a student submission (mark as COMPLETED).

        Also triggers mastery updates for any curriculum Ku linked via APPLIES_KNOWLEDGE.

        Args:
            report_uid: Submission UID to approve
            teacher_uid: Teacher approving

        Returns:
            Result containing updated submission info
        """
        access_check = await self._verify_teacher_access(report_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check)

        now = datetime.now().isoformat()
        allowed_from = [EntityStatus.REVISION_REQUESTED.value]
        result = await self.submissions_backend.approve_and_get_linked_kus(
            report_uid, now, EntityStatus.COMPLETED.value, allowed_from
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records:
            return Result.fail(
                Errors.validation(
                    message=(
                        f"Cannot approve: submission {report_uid} is not in an "
                        f"approvable status (expected one of {allowed_from})"
                    ),
                    field="status",
                )
            )

        record = records[0]
        student_uid = record["student_uid"] or ""
        raw_ku_uids = record["linked_ku_uids"]
        linked_ku_uids: list[str] = (
            [str(uid) for uid in raw_ku_uids if uid] if isinstance(raw_ku_uids, list) else []
        )

        # Resolve MasteryImpact from the linked Exercise (default MODERATE for backward compat)
        raw_impact = record.get("mastery_impact")
        try:
            impact = MasteryImpact(raw_impact) if raw_impact else MasteryImpact.MODERATE
        except ValueError:
            impact = MasteryImpact.MODERATE
        teacher_score = impact.get_teacher_score()

        # Update mastery for linked curriculum entities
        mastered_count = 0
        if self.ku_interaction_service and student_uid and linked_ku_uids:
            for linked_uid in linked_ku_uids:
                mastery_result = await self.ku_interaction_service.mark_mastered(
                    user_uid=student_uid,
                    ku_uid=linked_uid,
                    mastery_score=teacher_score,
                    method="ku_approval",
                )
                if mastery_result.is_ok:
                    mastered_count += 1
                else:
                    logger.warning(
                        f"Failed to update mastery for KU {linked_uid}: {mastery_result.error}"
                    )

            if mastered_count > 0:
                logger.info(
                    f"Updated mastery for {mastered_count} KUs from submission {report_uid}"
                )

        logger.info(f"Teacher {teacher_uid} approved submission {report_uid}")

        await publish_event(
            self.event_bus,
            SubmissionApproved(
                submission_uid=report_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                mastered_ku_count=mastered_count,
            ),
            logger,
        )

        return Result.ok(
            {
                "ku_uid": str(record["uid"]),
                "status": str(record["status"]),
                "approved": True,
                "mastered_ku_count": mastered_count,
            }
        )

    async def get_exercises_with_submission_counts(
        self,
        teacher_uid: str,
    ) -> Result[list[ExerciseWithSubmissionCounts]]:
        """
        Get teacher's exercises with submission and reviewed counts.

        Args:
            teacher_uid: Teacher UID

        Returns:
            Result containing list of exercise dicts with uid, title, scope,
            created_at, total_count, reviewed_count, pending_count
        """
        result = await self.exercise_backend.get_exercises_with_submission_counts(teacher_uid)
        if result.is_error:
            return Result.fail(result)

        items = [
            {
                "uid": record["uid"],
                "title": record["title"],
                "scope": record["scope"],
                "created_at": record["created_at"],
                "total_count": record["total_count"],
                "reviewed_count": record["reviewed_count"],
                "pending_count": record["pending_count"],
            }
            for record in result.value
        ]

        return Result.ok(items)

    async def get_submissions_for_exercise(
        self,
        exercise_uid: str,
    ) -> Result[list[SubmissionForExercise]]:
        """
        Get all submissions against a specific exercise.

        Args:
            exercise_uid: Exercise UID to fetch submissions for

        Returns:
            Result containing list of submission dicts with student info
            and feedback count
        """
        result = await self.submissions_backend.get_submissions_for_exercise_review(exercise_uid)
        if result.is_error:
            return Result.fail(result)

        items = [
            {
                "uid": record["uid"],
                "title": record["title"],
                "original_filename": record["original_filename"],
                "status": record["status"],
                "created_at": record["created_at"],
                "student_uid": record["student_uid"],
                "student_name": record["student_name"],
                "feedback_count": record["feedback_count"],
            }
            for record in result.value
        ]

        return Result.ok(items)

    async def get_students_summary(
        self,
        teacher_uid: str,
    ) -> Result[list[StudentSummaryItem]]:
        """
        Get students who have shared work with this teacher, with counts.

        Args:
            teacher_uid: Teacher UID

        Returns:
            Result containing list of student dicts with submission_count,
            reviewed_count, pending_count, ordered by pending descending
        """
        result = await self.submissions_backend.get_students_summary(teacher_uid)
        if result.is_error:
            return Result.fail(result)

        items = [
            {
                "student_uid": record["student_uid"],
                "student_name": record["student_name"],
                "submission_count": record["submission_count"],
                "reviewed_count": record["reviewed_count"],
                "pending_count": record["pending_count"],
            }
            for record in result.value
        ]

        return Result.ok(items)

    async def get_student_submissions(
        self,
        teacher_uid: str,
        student_uid: str,
    ) -> Result[list[StudentSubmissionItem]]:
        """
        Get all submissions from a student that were shared with this teacher.

        Args:
            teacher_uid: Teacher UID
            student_uid: Student UID

        Returns:
            Result containing list of submission dicts with exercise context
            and feedback count
        """
        result = await self.submissions_backend.get_student_submissions_for_teacher(
            teacher_uid, student_uid
        )
        if result.is_error:
            return Result.fail(result)

        items = [
            {
                "uid": record["uid"],
                "title": record["title"],
                "original_filename": record["original_filename"],
                "status": record["status"],
                "created_at": record["created_at"],
                "feedback_count": record["feedback_count"],
                "exercise_uid": record["exercise_uid"],
                "exercise_title": record["exercise_title"],
            }
            for record in result.value
        ]

        return Result.ok(items)

    async def get_submission_detail(
        self,
        submission_uid: str,
        teacher_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Get full detail of a submission for teacher review.

        Verifies teacher has SHARES_WITH access. Returns submission content,
        student info, and linked exercise (if any).

        Args:
            submission_uid: Submission UID
            teacher_uid: Teacher UID (access checked)

        Returns:
            Result containing submission detail dict
        """
        result = await self.submissions_backend.get_submission_detail_for_teacher(
            submission_uid, teacher_uid
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records:
            return Result.fail(
                Errors.not_found(
                    f"Submission {submission_uid} not found or not shared with teacher"
                )
            )

        record = records[0]
        return Result.ok(
            {
                "uid": record["uid"],
                "title": record["title"],
                "content": record["content"],
                "processed_content": record["processed_content"],
                "original_filename": record["original_filename"],
                "entity_type": record["entity_type"],
                "status": record["status"],
                "created_at": record["created_at"],
                "student_uid": record["student_uid"],
                "student_name": record["student_name"],
                "exercise_uid": record["exercise_uid"],
                "exercise_title": record["exercise_title"],
                "exercise_instructions": record["exercise_instructions"],
            }
        )

    async def get_dashboard_stats(
        self,
        teacher_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Get at-a-glance stats for the teacher dashboard.

        Returns pending review count, total submissions, distinct students,
        exercises owned, and groups owned.

        Args:
            teacher_uid: Teacher UID

        Returns:
            Result containing stats dict
        """
        result = await self.submissions_backend.get_dashboard_stats(teacher_uid)
        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records:
            return Result.ok(
                {
                    "pending_count": 0,
                    "total_submissions": 0,
                    "total_students": 0,
                    "total_exercises": 0,
                    "total_groups": 0,
                }
            )

        record = records[0]
        return Result.ok(
            {
                "pending_count": record["pending_count"] or 0,
                "total_submissions": record["total_submissions"] or 0,
                "total_students": record["total_students"] or 0,
                "total_exercises": record["total_exercises"] or 0,
                "total_groups": record["total_groups"] or 0,
            }
        )

    async def get_teacher_groups_with_stats(
        self,
        teacher_uid: str,
    ) -> Result[list[TeacherGroupStats]]:
        """
        Get teacher's groups with member, exercise, and pending submission counts.

        Args:
            teacher_uid: Teacher UID

        Returns:
            Result containing list of group stat dicts
        """
        result = await self.group_backend.get_teacher_groups_with_stats(teacher_uid)
        if result.is_error:
            return Result.fail(result)

        items = [
            {
                "uid": record["uid"],
                "name": record["name"],
                "description": record["description"],
                "is_active": record["is_active"],
                "member_count": record["member_count"] or 0,
                "exercise_count": record["exercise_count"] or 0,
                "pending_count": record["pending_count"] or 0,
            }
            for record in result.value
        ]

        return Result.ok(items)

    async def get_group_detail(
        self,
        group_uid: str,
        teacher_uid: str,
    ) -> Result[list[GroupMemberProgress]]:
        """
        Get members of a teacher's group with their submission progress.

        Access-checked: only succeeds if teacher owns the group.

        Args:
            group_uid: Group UID
            teacher_uid: Teacher UID (ownership checked)

        Returns:
            Result containing list of member progress items
        """
        result = await self.group_backend.get_group_detail(group_uid, teacher_uid)
        if result.is_error:
            return Result.fail(result)

        items = [
            {
                "user_uid": record["user_uid"],
                "user_name": record["user_name"],
                "role": record["role"],
                "joined_at": record["joined_at"],
                "submission_count": record["submission_count"] or 0,
                "reviewed_count": record["reviewed_count"] or 0,
                "pending_count": record["pending_count"] or 0,
            }
            for record in result.value
        ]

        return Result.ok(items)

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    async def _verify_teacher_access(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[bool]:
        """Verify teacher has SHARES_WITH access to the entity."""
        result = await self.submissions_backend.verify_teacher_access(report_uid, teacher_uid)
        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.fail(
                Errors.not_found(
                    f"Teacher {teacher_uid} does not have review access to submission {report_uid}"
                )
            )

        return Result.ok(True)
