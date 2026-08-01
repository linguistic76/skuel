"""
Teacher Review Service
=======================

Manages the teacher review workflow for assigned submissions.

Reuses SHARES_WITH infrastructure. When a student submits an entity against
an ASSIGNED Exercise, the entity is auto-shared with the teacher.
The teacher's review queue = submissions shared with them via role="teacher".

When providing a report or requesting revision, an ENTRY_REPORT Entity node
is created and linked to the submission via REPORT_FOR. This makes every
report round a first-class graph entity — searchable, queryable, and
supporting revision cycles.

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
See: /docs/architecture/LEARNING_LOOP_ARCHITECTURE.md
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from core.events import publish_event
from core.events.learning_loop_events import (
    ReportSubmitted,
    UserEntryApproved,
    UserEntryRevisionRequested,
)
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.learning_enums import AssessmentOutcome, MasteryImpact
from core.models.enums.pipeline import ReportSource
from core.models.type_hints import UserUID
from core.ports.query_types import (
    ExerciseWithSubmissionCounts,
    GroupMemberProgress,
    ReportApprovalResult,
    ReportSubmitResult,
    ReviewQueueItem,
    RevisionRequestResult,
    RevisionWithExerciseResult,
    StudentSubmissionItem,
    StudentSummaryItem,
    SubmissionDetailResult,
    SubmissionForExercise,
    TeacherDashboardStats,
    TeacherGroupStats,
)
from core.ports.report_protocols import (
    EntryReportBackendOperations,
    TeacherReviewExerciseQueries,
    TeacherReviewGroupQueries,
)
from core.ports.user_entry_protocols import UserEntryOperations
from core.utils.logging import get_logger
from core.utils.neo4j_props import coerce_int
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.ps.ps_mastery_service import PsMasteryService
    from core.services.report.report_mastery_service import ReportMasteryService

logger = get_logger("skuel.services.teacher_review")


class TeacherReviewService:
    """Service for teacher review of student submissions."""

    def __init__(
        self,
        user_entry_backend: UserEntryOperations,
        report_backend: EntryReportBackendOperations,
        exercise_backend: TeacherReviewExerciseQueries,
        group_backend: TeacherReviewGroupQueries,
        ku_interaction_service: "PsMasteryService",
        report_mastery_service: "ReportMasteryService",
        event_bus: "EventBusOperations",
    ) -> None:
        """
        Initialize the teacher review service.

        Args:
            user_entry_backend: Backend for submission queries
            exercise_backend: Backend for exercise queries
            group_backend: Backend for group queries
            ku_interaction_service: KU interaction service for mastery updates
            report_mastery_service: Explicit mastery propagation service
            event_bus: Event bus for publishing review events
        """
        self.user_entry_backend = user_entry_backend
        self.report_backend = report_backend
        self.exercise_backend = exercise_backend
        self.group_backend = group_backend
        self.ku_interaction_service = ku_interaction_service
        self.report_mastery_service = report_mastery_service
        self.event_bus = event_bus

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
        student_uid: str | None = None,
    ) -> Result[list[ReviewQueueItem]]:
        """
        Get teacher's pending review queue.

        Returns entries shared with the teacher's groups via SHARED_WITH_GROUP
        whose pipeline is ``teacher_review``. Empty when the teacher owns no
        groups or no entries have been shared — does not leak the existence
        of unrelated students' submissions.

        This is THE needs-review rule: the per-student page's Needs Review
        section calls this same method with ``student_uid`` set, so the queue
        and the student page always agree on what awaits review.

        Args:
            teacher_uid: Teacher UID
            status_filter: Optional single-status filter (e.g., "submitted").
                Defaults to ["submitted", "active"] when ``None``.
            student_uid: Optional student scope — restricts the queue to
                entries that student owns.

        Returns:
            Result containing list of review items (``ReviewQueueItem`` shape)
        """
        statuses = [status_filter] if status_filter else None
        result = await self.user_entry_backend.get_review_queue_by_groups(
            teacher_uid, statuses, student_uid
        )
        if result.is_error:
            return Result.fail(result)

        # Remap backend keys (entry_uid, exercise_title) to ReviewQueueItem
        # public shape (submission_uid, exercise_name) so UI consumers
        # (ui/teaching/types.queue_item_from_dict, scripts/export_submissions)
        # see a stable surface across the get_review_queue → by_groups rewire.
        # boundary: neo4j-rows — heterogeneous dict columns vary per query
        # (execute_query's own return type); viewed as dict[str, Any] so the typed
        # literal below builds without per-value casts.
        records: list[dict[str, Any]] = result.value
        items: list[ReviewQueueItem] = [
            {
                "submission_uid": record["entry_uid"],
                "title": record["title"],
                "status": record["status"],
                "entity_type": record["entity_type"],
                "submitted_at": record["submitted_at"],
                "student_uid": record["student_uid"],
                "student_name": record["student_name"],
                "exercise_uid": record["exercise_uid"],
                "exercise_name": record["exercise_title"],
                "due_date": record["due_date"],
                "original_filename": record.get("original_filename"),
                "feedback_count": record["feedback_count"],
            }
            for record in records
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

        Creates an ENTRY_REPORT Entity node linked to the submission via REPORT_FOR
        and transitions submission status to COMPLETED.

        Args:
            report_uid: Submission UID to provide report for
            teacher_uid: Teacher providing report
            feedback: EntryReport text (read from uploaded .md file)
            file_path: Optional path to the uploaded .md report file

        Returns:
            Result containing report info
        """
        access_check = await self._verify_teacher_has_group_access(report_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check)

        report_entity_uid = UIDGenerator.generate_uid("er")
        now = datetime.now().isoformat()

        allowed_from = [EntityStatus.SUBMITTED.value, EntityStatus.ACTIVE.value]
        result = await self.report_backend.create_report_node(
            {
                "report_uid": report_uid,
                "report_entity_uid": report_entity_uid,
                "author_uid": teacher_uid,
                "feedback": feedback,
                "report_file_path": file_path,
                "title": f"Feedback: {report_uid[:30]}",
                "entity_type": EntityType.ENTRY_REPORT.value,
                "submission_status": EntityStatus.COMPLETED.value,
                "completed_status": EntityStatus.COMPLETED.value,
                "processor_type": ReportSource.HUMAN.value,
                "assessment_outcome": AssessmentOutcome.APPROVED.value,
                "allowed_from_statuses": allowed_from,
                "visibility": "shared",
                "create_student_share": True,
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

        student_uid = str(records[0]["student_uid"] or "")
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

        Creates an ENTRY_REPORT Entity node with revision notes, linked via REPORT_FOR.
        Sets submission status to REVISION_REQUESTED.

        Args:
            report_uid: Submission UID needing revision
            teacher_uid: Teacher requesting revision
            notes: Revision notes/instructions

        Returns:
            Result containing revision info
        """
        access_check = await self._verify_teacher_has_group_access(report_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check)

        report_entity_uid = UIDGenerator.generate_uid("er")
        now = datetime.now().isoformat()

        allowed_from = [EntityStatus.SUBMITTED.value, EntityStatus.ACTIVE.value]
        result = await self.report_backend.create_report_node(
            {
                "report_uid": report_uid,
                "report_entity_uid": report_entity_uid,
                "author_uid": teacher_uid,
                "feedback": notes,
                "report_file_path": None,
                "title": f"Revision request: {report_uid[:30]}",
                "entity_type": EntityType.ENTRY_REPORT.value,
                "submission_status": EntityStatus.REVISION_REQUESTED.value,
                "completed_status": EntityStatus.COMPLETED.value,
                "processor_type": ReportSource.HUMAN.value,
                "assessment_outcome": AssessmentOutcome.NEEDS_REVISION.value,
                "allowed_from_statuses": allowed_from,
                "visibility": "shared",
                "create_student_share": True,
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

        student_uid = str(records[0]["student_uid"] or "")
        logger.info(
            f"Teacher {teacher_uid} requested revision {report_entity_uid} for submission {report_uid}"
        )

        await publish_event(
            self.event_bus,
            UserEntryRevisionRequested(
                entity_uid=report_uid,
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
        """Atomically create EntryReport + RevisedExercise in one transaction.

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
        access_check = await self._verify_teacher_has_group_access(submission_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check)

        from core.models.enums.learning_enums import FeedbackCategory
        from core.models.exercises.revised_exercise import FeedbackPoint, RevisedExercise

        report_entity_uid = UIDGenerator.generate_uid("er")
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

        # Build RevisedExercise entity — the backend serializes it to node
        # properties (computed fields overridden in Cypher)
        re_entity = RevisedExercise(
            uid=re_uid,
            entity_type=EntityType.REVISED_EXERCISE,
            title="",  # Overridden in Cypher
            user_uid=UserUID(teacher_uid),
            original_exercise_uid=original_exercise_uid,
            report_uid=report_entity_uid,
            instructions=notes,
            feedback_points=tuple(parsed_points),
            revision_rationale=revision_rationale,
            parent_entity_uid=report_entity_uid,
        )
        allowed_from = [EntityStatus.SUBMITTED.value, EntityStatus.ACTIVE.value]
        result = await self.report_backend.create_report_and_revised_exercise(
            {
                # Phase 1 params (EntryReport)
                "report_uid": submission_uid,
                "report_entity_uid": report_entity_uid,
                "author_uid": teacher_uid,
                "feedback": notes,
                "report_file_path": None,
                "title": f"Revision request: {submission_uid[:30]}",
                "entity_type": EntityType.ENTRY_REPORT.value,
                "submission_status": EntityStatus.REVISION_REQUESTED.value,
                "completed_status": EntityStatus.COMPLETED.value,
                "processor_type": ReportSource.HUMAN.value,
                "assessment_outcome": AssessmentOutcome.NEEDS_REVISION.value,
                "allowed_from_statuses": allowed_from,
                "now": now,
                # Phase 2 params (RevisedExercise) — re_props injected adapter-side
                "re_uid": re_uid,
                "original_exercise_uid": original_exercise_uid,
            },
            re_entity,
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
        student_uid = str(record["student_uid"] or "")
        revision_number = coerce_int(record["revision_number"])

        logger.info(
            f"Teacher {teacher_uid} atomically created report {report_entity_uid} "
            f"+ revised exercise {re_uid} (revision {revision_number}) "
            f"for submission {submission_uid}"
        )

        # Publish events after successful transaction
        await publish_event(
            self.event_bus,
            UserEntryRevisionRequested(
                entity_uid=submission_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                revision_notes=notes,
                metadata={"report_uid": report_entity_uid},
            ),
            logger,
        )

        from core.events.embedding_publisher import publish_embedding_requested
        from core.events.learning_loop_events import RevisedExerciseCreated

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

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(
            self.event_bus, EntityType.REVISED_EXERCISE, re_entity, logger
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
        access_check = await self._verify_teacher_has_group_access(report_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check)

        now = datetime.now().isoformat()
        allowed_from = [EntityStatus.REVISION_REQUESTED.value]
        result = await self.user_entry_backend.approve_and_get_linked_kus(
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
        student_uid = UserUID(str(record["student_uid"] or ""))
        raw_ku_uids = record["linked_ku_uids"]
        linked_ku_uids: list[str] = (
            [str(uid) for uid in raw_ku_uids if uid] if isinstance(raw_ku_uids, list) else []
        )

        # Resolve MasteryImpact from the linked Exercise (default MODERATE for backward compat)
        raw_impact = record.get("mastery_impact")
        impact = MasteryImpact.from_value(raw_impact)

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
            UserEntryApproved(
                entity_uid=report_uid,
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

        return Result.ok(cast("list[ExerciseWithSubmissionCounts]", items))

    async def get_submissions_for_exercise(
        self,
        exercise_uid: str,
        teacher_uid: str,
    ) -> Result[list[SubmissionForExercise]]:
        """
        Get submissions against a specific exercise, scoped to the teacher's classroom.

        Args:
            exercise_uid: Exercise UID to fetch submissions for
            teacher_uid: Requesting teacher — only submissions shared with a
                group this teacher owns are returned (cross-teacher isolation)

        Returns:
            Result containing list of submission dicts with student info
            and feedback count
        """
        result = await self.user_entry_backend.get_entries_for_exercise_review(
            exercise_uid, teacher_uid
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
                "student_uid": record["student_uid"],
                "student_name": record["student_name"],
                "feedback_count": record["feedback_count"],
            }
            for record in result.value
        ]

        return Result.ok(cast("list[SubmissionForExercise]", items))

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
        result = await self.user_entry_backend.get_students_summary(teacher_uid)
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

        return Result.ok(cast("list[StudentSummaryItem]", items))

    async def get_student_submissions(
        self,
        teacher_uid: str,
        student_uid: str,
    ) -> Result[list[StudentSubmissionItem]]:
        """
        Get all submissions owned by a student, gated by shared active group.

        Returns the student's submissions only when the teacher and student
        share an active group (``(teacher)-[:OWNS]->(g:Group {is_active:true})
        <-[:MEMBER_OF]-(student)``). Empty when no shared active group exists,
        which the route surface treats as a genuinely empty per-student
        history — does not leak the existence of unrelated students' work.

        Args:
            teacher_uid: Teacher UID (load-bearing; gates the read)
            student_uid: Student UID

        Returns:
            Result containing list of submission dicts with exercise context
            and feedback count
        """
        result = await self.user_entry_backend.get_student_entries_for_teacher(
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

        return Result.ok(cast("list[StudentSubmissionItem]", items))

    async def get_submission_detail(
        self,
        submission_uid: str,
        teacher_uid: str,
    ) -> Result[SubmissionDetailResult]:
        """
        Get full detail of a submission for teacher review.

        Gated by ``SHARED_WITH_GROUP`` at the backend layer: empty when the
        submission is not shared with any active group the teacher owns.
        Empty maps to ``Errors.not_found`` (404) so a teacher outside the
        student's group cannot distinguish "submission does not exist" from
        "exists but belongs to another teacher's student".

        Args:
            submission_uid: Submission UID
            teacher_uid: Teacher UID (load-bearing; gates the read)

        Returns:
            Result containing submission detail dict
        """
        result = await self.user_entry_backend.get_entry_detail_for_teacher(
            submission_uid, teacher_uid
        )
        if result.is_error:
            return Result.fail(result)

        # boundary: neo4j-rows — heterogeneous dict columns vary per query
        # (execute_query's own return type); viewed as dict[str, Any] so the typed
        # literal below builds without per-value casts.
        records: list[dict[str, Any]] = result.value
        if not records:
            return Result.fail(
                Errors.not_found(
                    f"Submission {submission_uid} not found or not shared with teacher"
                )
            )

        record = records[0]
        detail: SubmissionDetailResult = {
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
        return Result.ok(detail)

    async def get_dashboard_stats(
        self,
        teacher_uid: str,
    ) -> Result[TeacherDashboardStats]:
        """
        Get at-a-glance stats for the teacher dashboard.

        Returns pending review count, total submissions, distinct students,
        exercises owned, and groups owned.

        Args:
            teacher_uid: Teacher UID

        Returns:
            Result containing stats dict
        """
        result = await self.user_entry_backend.get_dashboard_stats(teacher_uid)
        if result.is_error:
            return Result.fail(result)

        # boundary: neo4j-rows — heterogeneous dict columns vary per query
        # (execute_query's own return type); viewed as dict[str, Any] so the typed
        # stat literal below builds without per-value casts.
        records: list[dict[str, Any]] = result.value
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

        return Result.ok(cast("list[TeacherGroupStats]", items))

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

        return Result.ok(cast("list[GroupMemberProgress]", items))

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    async def get_report_file_path(self, report_uid: str, teacher_uid: str) -> Result[str | None]:
        """Report file path, gated by the teacher's classroom access to the report.

        The role gate on the download route answers "may you review at all",
        never "whose feedback"; this answers the second question. Returns
        ``None`` when the report is missing or belongs to a submission outside
        the teacher's active groups, so the download route yields a 404 either
        way (a denied read must not read as a missing-file success either).

        Backend: UserEntryBackend.get_report_file_path (REPORT_FOR → owner →
        shared active group).
        """
        return await self.user_entry_backend.get_report_file_path(report_uid, teacher_uid)

    async def _verify_teacher_has_group_access(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[bool]:
        """Verify teacher shares an active group with the submission's owner.

        Maps empty backend results to ``Errors.not_found(...)`` (404) so a
        teacher outside the student's group cannot distinguish between
        "submission does not exist" and "submission exists but belongs to
        another teacher's student."
        """
        result = await self.user_entry_backend.verify_teacher_has_group_access(
            report_uid, teacher_uid
        )
        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.fail(
                Errors.not_found(
                    f"Teacher {teacher_uid} does not have review access to submission {report_uid}"
                )
            )

        return Result.ok(True)

    async def verify_teacher_authority(
        self,
        teacher_uid: str,
        student_uid: str,
    ) -> Result[bool]:
        """Verify the teacher shares an active group with the student."""
        result = await self.user_entry_backend.verify_teacher_authority(teacher_uid, student_uid)
        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.fail(
                Errors.forbidden(
                    action="verify_teacher_authority",
                    reason=f"Teacher {teacher_uid} does not have authority over student {student_uid}",
                )
            )

        return Result.ok(True)
