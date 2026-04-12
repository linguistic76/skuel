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

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
See: /docs/architecture/LEARNING_LOOP_ARCHITECTURE.md
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
    RevisionWithExerciseResult,
    StudentSubmissionItem,
    StudentSummaryItem,
    SubmissionForExercise,
    TeacherGroupStats,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from adapters.persistence.neo4j.backends.collab_backends import GroupBackend
    from adapters.persistence.neo4j.backends.exercise_backends import ExerciseBackend
    from adapters.persistence.neo4j.backends.submissions_backend import SubmissionsBackend
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.ps.ps_mastery_service import PsMasteryService
    from core.services.report.report_mastery_service import ReportMasteryService

logger = get_logger("skuel.services.teacher_review")


class TeacherReviewService:
    """Service for teacher review of student submissions."""

    def __init__(
        self,
        submissions_backend: "SubmissionsBackend",
        exercise_backend: "ExerciseBackend",
        group_backend: "GroupBackend",
        ku_interaction_service: "PsMasteryService",
        report_mastery_service: "ReportMasteryService",
        event_bus: "EventBusOperations",
    ) -> None:
        """
        Initialize the teacher review service.

        Args:
            submissions_backend: Backend for submission queries
            exercise_backend: Backend for exercise queries
            group_backend: Backend for group queries
            ku_interaction_service: KU interaction service for mastery updates
            report_mastery_service: Explicit mastery propagation service
            event_bus: Event bus for publishing review events
        """
        self.submissions_backend = submissions_backend
        self.exercise_backend = exercise_backend
        self.group_backend = group_backend
        self.ku_interaction_service = ku_interaction_service
        self.report_mastery_service = report_mastery_service
        self.event_bus = event_bus

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
        entity_type_filter: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get teacher's pending review queue.

        Returns all student submissions (via OWNS), optionally filtered by
        status or entity_type. Includes count of existing feedback rounds per
        submission. Defaults to submitted+active statuses when no filter given.

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
                "submission_uid": record["submission_uid"],
                "title": record["title"],
                "status": record["status"],
                "entity_type": record["entity_type"],
                "submitted_at": record["submitted_at"],
                "student_uid": record["student_uid"],
                "student_name": record["student_name"],
                "exercise_uid": record["exercise_uid"],
                "exercise_name": record["exercise_name"],
                "due_date": record["due_date"],
                "original_filename": record.get("original_filename"),
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
        file_path: str | None = None,
    ) -> Result[ReportSubmitResult]:
        """
        Submit teacher report for an entity.

        Creates an EXERCISE_REPORT Entity node linked to the submission via REPORT_FOR.
        Also writes report to submission's report field (denormalized for quick access)
        and sets submission status to COMPLETED.

        Args:
            report_uid: Submission UID to provide report for
            teacher_uid: Teacher providing report
            feedback: ExerciseReport text (read from uploaded .md file)
            file_path: Optional path to the uploaded .md report file

        Returns:
            Result containing report info
        """
        access_check = await self._verify_teacher_access(report_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check)

        report_entity_uid = UIDGenerator.generate_uid("sr")
        now = datetime.now().isoformat()

        allowed_from = [EntityStatus.SUBMITTED.value, EntityStatus.ACTIVE.value]
        result = await self.submissions_backend.create_report_node(
            {
                "report_uid": report_uid,
                "report_entity_uid": report_entity_uid,
                "teacher_uid": teacher_uid,
                "feedback": feedback,
                "report_file_path": file_path,
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
                "submission_uid": str(records[0]["uid"]),
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

        allowed_from = [EntityStatus.SUBMITTED.value, EntityStatus.ACTIVE.value]
        result = await self.submissions_backend.create_report_node(
            {
                "report_uid": report_uid,
                "report_entity_uid": report_entity_uid,
                "teacher_uid": teacher_uid,
                "feedback": notes,
                "report_file_path": None,
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
                "submission_uid": str(records[0]["uid"]),
                "status": str(records[0]["status"]),
                "report_uid": report_entity_uid,
                "revision_requested": True,
                "student_uid": str(student_uid),
            }
        )

    async def request_revision_with_exercise(
        self,
        submission_uid: str,
        teacher_uid: str,
        notes: str,
        original_exercise_uid: str,
        feedback_points: list[dict[str, str]],
        revision_rationale: str | None,
    ) -> Result[RevisionWithExerciseResult]:
        """Atomically create ExerciseReport + RevisedExercise in one transaction.

        Combines the two-phase revision request into a single backend call.
        If anything fails, no partial state is left behind — the student never
        sees "Revision Requested" without revision instructions.

        Args:
            submission_uid: Submission UID needing revision
            teacher_uid: Teacher requesting revision
            notes: Revision instructions text
            original_exercise_uid: UID of the original Exercise
            feedback_points: List of {category, detail} dicts
            revision_rationale: Why this revision was created
        """
        access_check = await self._verify_teacher_access(submission_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check)

        from core.models.enums.learning_enums import FeedbackCategory
        from core.models.exercises.revised_exercise import FeedbackPoint, RevisedExercise
        from core.utils.embedding_text_builder import build_embedding_text
        from core.utils.neo4j_mapper import to_neo4j_node

        report_entity_uid = UIDGenerator.generate_uid("sr")
        re_uid = UIDGenerator.generate_uid("re")
        now = datetime.now().isoformat()

        # Parse feedback points into domain objects for embedding text
        parsed_points: list[FeedbackPoint] = []
        for fp in feedback_points:
            try:
                cat = FeedbackCategory(fp["category"])
                parsed_points.append(FeedbackPoint(category=cat, detail=fp["detail"]))
            except ValueError:
                pass  # Skip invalid categories

        # Build RevisedExercise entity for to_neo4j_node (computed fields overridden in Cypher)
        re_entity = RevisedExercise(
            uid=re_uid,
            entity_type=EntityType.REVISED_EXERCISE,
            title="",  # Overridden in Cypher
            user_uid=teacher_uid,
            original_exercise_uid=original_exercise_uid,
            report_uid=report_entity_uid,
            instructions=notes,
            feedback_points=tuple(parsed_points),
            revision_rationale=revision_rationale,
            parent_entity_uid=report_entity_uid,
        )
        re_props = to_neo4j_node(re_entity)

        allowed_from = [EntityStatus.SUBMITTED.value, EntityStatus.ACTIVE.value]
        result = await self.submissions_backend.create_report_and_revised_exercise(
            {
                # Phase 1 params (ExerciseReport)
                "report_uid": submission_uid,
                "report_entity_uid": report_entity_uid,
                "teacher_uid": teacher_uid,
                "feedback": notes,
                "report_file_path": None,
                "title": f"Revision request: {submission_uid[:30]}",
                "entity_type": EntityType.EXERCISE_REPORT.value,
                "submission_status": EntityStatus.REVISION_REQUESTED.value,
                "completed_status": EntityStatus.COMPLETED.value,
                "processor_type": ProcessorType.HUMAN.value,
                "assessment_outcome": AssessmentOutcome.NEEDS_REVISION.value,
                "allowed_from_statuses": allowed_from,
                "now": now,
                # Phase 2 params (RevisedExercise)
                "re_props": re_props,
                "re_uid": re_uid,
                "original_exercise_uid": original_exercise_uid,
            }
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records:
            return Result.fail(
                Errors.validation(
                    message=(
                        f"Cannot request revision: submission {submission_uid} is not in a "
                        f"revisable status (expected one of {allowed_from})"
                    ),
                    field="status",
                )
            )

        record = records[0]
        student_uid = record["student_uid"] or ""
        revision_number = int(record["revision_number"])

        logger.info(
            f"Teacher {teacher_uid} atomically created report {report_entity_uid} "
            f"+ revised exercise {re_uid} (revision {revision_number}) "
            f"for submission {submission_uid}"
        )

        # Publish events after successful transaction
        await publish_event(
            self.event_bus,
            SubmissionRevisionRequested(
                submission_uid=submission_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                revision_notes=notes,
                metadata={"report_uid": report_entity_uid},
            ),
            logger,
        )

        from core.events import RevisedExerciseEmbeddingRequested
        from core.events.submission_events import RevisedExerciseCreated

        await publish_event(
            self.event_bus,
            RevisedExerciseCreated(
                revised_exercise_uid=re_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                original_exercise_uid=original_exercise_uid,
                report_uid=report_entity_uid,
                revision_number=revision_number,
            ),
            logger,
        )

        embedding_text = build_embedding_text(EntityType.REVISED_EXERCISE, re_entity)
        if embedding_text:
            await publish_event(
                self.event_bus,
                RevisedExerciseEmbeddingRequested(
                    entity_uid=re_uid,
                    entity_type="revised_exercise",
                    embedding_text=embedding_text,
                    user_uid=teacher_uid,
                    requested_at=datetime.now(),
                ),
                logger,
            )

        return Result.ok(
            {
                "submission_uid": str(record["uid"]),
                "status": str(record["status"]),
                "report_uid": report_entity_uid,
                "revised_exercise_uid": re_uid,
                "student_uid": str(student_uid),
                "revision_number": revision_number,
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

        # Explicitly propagate mastery using ReportMasteryService
        propagate_result = await self.report_mastery_service.propagate_mastery(
            submission_uid=report_uid,
            user_uid=student_uid,
            linked_ku_uids=linked_ku_uids,
            mastery_impact=impact,
            method="ku_approval",
        )
        mastered_count = propagate_result.value if propagate_result.is_ok else 0

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
                "submission_uid": str(record["uid"]),
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
        Get all submissions owned by a student (admin oversight view).

        Returns every submission regardless of exercise scope or sharing status.
        The SHARES_WITH filter is intentionally absent here — this view is for
        admin/teacher oversight of a student's full submission history.

        Args:
            teacher_uid: Teacher UID (retained for access control context)
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
                "file_path": record.get("file_path"),
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
                    "total_students": 0,
                    "total_exercises": 0,
                    "total_groups": 0,
                }
            )

        record = records[0]
        return Result.ok(
            {
                "pending_count": record["pending_count"] or 0,
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

    async def get_report_file_path(self, report_uid: str) -> Result[str | None]:
        """Get the report_file_path for an ExerciseReport node by UID."""
        return await self.submissions_backend.get_report_file_path(report_uid)

    async def _verify_teacher_access(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[bool]:
        """Verify the submission is owned by a student (not the teacher themselves)."""
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
