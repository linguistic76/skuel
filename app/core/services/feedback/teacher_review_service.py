"""
Teacher Review Service
=======================

Manages the teacher review workflow for assigned Ku submissions.

Reuses SHARES_WITH infrastructure. When a student submits an entity against
an ASSIGNED Exercise, the entity is auto-shared with the teacher.
The teacher's review queue = Ku shared with them via role="teacher".

When providing feedback or requesting revision, a FEEDBACK_REPORT Entity nodes
is created and linked to the submission via FEEDBACK_FOR. This makes every
feedback round a first-class graph entity — searchable, queryable, and
supporting revision cycles.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
See: /docs/architecture/SUBMISSION_FEEDBACK_LOOP.md
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.submission_events import SubmissionReviewed, SubmissionRevisionRequested
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.ports import QueryExecutor

logger = get_logger("skuel.services.teacher_review")


class TeacherReviewService:
    """Service for teacher review of student submissions."""

    def __init__(
        self,
        executor: "QueryExecutor",
        ku_interaction_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize the teacher review service.

        Args:
            executor: Query executor for database operations
            ku_interaction_service: Optional KU interaction service for mastery updates
            event_bus: Optional event bus for publishing review events
        """
        self.executor = executor
        self.ku_interaction_service = ku_interaction_service
        self.event_bus = event_bus

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
        ku_type_filter: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get teacher's pending review queue.

        Returns Ku shared with the teacher via role="teacher",
        optionally filtered by status or ku_type. Includes count of
        existing feedback rounds per submission.

        Args:
            teacher_uid: Teacher UID
            status_filter: Optional status filter (e.g., "submitted")
            ku_type_filter: Optional ku_type filter (e.g., "submission", "task")

        Returns:
            Result containing list of review items
        """
        where_clauses = []
        params: dict[str, Any] = {"teacher_uid": teacher_uid}

        if status_filter:
            where_clauses.append("report.status = $status_filter")
            params["status_filter"] = status_filter

        if ku_type_filter:
            where_clauses.append("report.ku_type = $ku_type_filter")
            params["ku_type_filter"] = ku_type_filter

        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[r:SHARES_WITH {{role: 'teacher'}}]->(ku:Entity)
        {where_clause}
        OPTIONAL MATCH (student:User)-[:OWNS]->(ku)
        OPTIONAL MATCH (ku)-[:FULFILLS_EXERCISE]->(project:Entity {{ku_type: 'exercise'}})
        OPTIONAL MATCH (fb:Entity {{ku_type: 'feedback_report'}})-[:FEEDBACK_FOR]->(ku)
        WITH ku, student, project, r, count(fb) as feedback_count
        RETURN ku.uid as ku_uid,
               ku.title as title,
               ku.status as status,
               ku.ku_type as ku_type,
               ku.created_at as submitted_at,
               student.uid as student_uid,
               student.name as student_name,
               project.uid as project_uid,
               project.name as project_name,
               project.due_date as due_date,
               r.shared_at as shared_at,
               feedback_count
        ORDER BY ku.created_at DESC
        """

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        items = [
            {
                "ku_uid": record["ku_uid"],
                "title": record["title"],
                "status": record["status"],
                "ku_type": record["ku_type"],
                "submitted_at": record["submitted_at"],
                "student_uid": record["student_uid"],
                "student_name": record["student_name"],
                "project_uid": record["project_uid"],
                "project_name": record["project_name"],
                "due_date": record["due_date"],
                "shared_at": record["shared_at"],
                "feedback_count": record["feedback_count"],
            }
            for record in result.value
        ]

        return Result.ok(items)

    async def get_feedback_history(
        self,
        submission_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all FEEDBACK_REPORT nodes linked to a submission via FEEDBACK_FOR.

        Args:
            submission_uid: The submission Ku UID

        Returns:
            Result containing list of feedback items ordered by creation date
        """
        query = """
        MATCH (fb:Entity {ku_type: 'feedback_report'})-[:FEEDBACK_FOR]->(submission:Entity {uid: $submission_uid})
        OPTIONAL MATCH (teacher:User)-[:OWNS]->(fb)
        RETURN fb.uid as uid,
               fb.title as title,
               fb.content as content,
               fb.status as status,
               fb.created_at as created_at,
               teacher.uid as teacher_uid,
               teacher.name as teacher_name
        ORDER BY fb.created_at ASC
        """

        result = await self.executor.execute_query(query, {"submission_uid": submission_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

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

    async def submit_feedback(
        self,
        report_uid: str,
        teacher_uid: str,
        feedback: str,
    ) -> Result[dict[str, Any]]:
        """
        Submit teacher feedback for an entity.

        Creates a FEEDBACK_REPORT Entity nodes linked to the submission via FEEDBACK_FOR.
        Also writes feedback to submission's feedback field (denormalized for quick access)
        and sets submission status to COMPLETED.

        Args:
            report_uid: Submission Ku UID to provide feedback for
            teacher_uid: Teacher providing feedback
            feedback: Feedback text

        Returns:
            Result containing feedback Ku info
        """
        access_check = await self._verify_teacher_access(report_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check.expect_error())

        feedback_uid = UIDGenerator.generate_uid("ku")
        now = datetime.now().isoformat()

        # Create FEEDBACK_REPORT node, link via FEEDBACK_FOR, share with student,
        # and update submission status — all in one transaction
        query = """
        MATCH (submission:Entity {uid: $report_uid})
        OPTIONAL MATCH (student:User)-[:OWNS]->(submission)

        // Update submission with denormalized feedback
        SET submission.feedback = $feedback,
            submission.feedback_generated_at = datetime($now),
            submission.status = $completed_status,
            submission.updated_at = datetime($now)

        // Create FEEDBACK_REPORT Entity nodes
        CREATE (fb:Entity {
            uid: $feedback_uid,
            title: $title,
            ku_type: $ku_type,
            user_uid: $teacher_uid,
            status: $completed_status,
            processor_type: $processor_type,
            content: $feedback,
            created_by: $teacher_uid,
            created_at: datetime($now),
            updated_at: datetime($now)
        })

        // Teacher owns the feedback
        WITH submission, student, fb
        MATCH (teacher:User {uid: $teacher_uid})
        CREATE (teacher)-[:OWNS]->(fb)
        CREATE (fb)-[:FEEDBACK_FOR]->(submission)

        // Share feedback with student (if student exists)
        WITH submission, student, fb
        WHERE student IS NOT NULL
        CREATE (student)-[:SHARES_WITH {shared_at: datetime($now), role: 'student'}]->(fb)

        RETURN submission.uid as uid,
               submission.status as status,
               student.uid as student_uid,
               fb.uid as feedback_uid
        """

        result = await self.executor.execute_query(
            query,
            {
                "report_uid": report_uid,
                "feedback_uid": feedback_uid,
                "teacher_uid": teacher_uid,
                "feedback": feedback,
                "title": f"Feedback: {report_uid[:30]}",
                "ku_type": EntityType.FEEDBACK_REPORT.value,
                "completed_status": EntityStatus.COMPLETED.value,
                "processor_type": ProcessorType.HUMAN.value,
                "now": now,
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
        if not records:
            return Result.fail(Errors.not_found(f"Ku {report_uid} not found"))

        student_uid = records[0]["student_uid"] or ""
        logger.info(f"Teacher {teacher_uid} submitted feedback {feedback_uid} for Ku {report_uid}")

        await publish_event(
            self.event_bus,
            SubmissionReviewed(
                submission_uid=report_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                occurred_at=datetime.now(),
                metadata={"feedback_uid": feedback_uid},
            ),
            logger,
        )

        return Result.ok(
            {
                "ku_uid": records[0]["uid"],
                "status": records[0]["status"],
                "feedback_uid": feedback_uid,
                "feedback_submitted": True,
            }
        )

    async def request_revision(
        self,
        report_uid: str,
        teacher_uid: str,
        notes: str,
    ) -> Result[dict[str, Any]]:
        """
        Request revision for a student Ku.

        Creates a FEEDBACK_REPORT Entity nodes with revision notes, linked via FEEDBACK_FOR.
        Sets submission status to REVISION_REQUESTED.

        Args:
            report_uid: Ku UID needing revision
            teacher_uid: Teacher requesting revision
            notes: Revision notes/instructions

        Returns:
            Result containing feedback Ku info
        """
        access_check = await self._verify_teacher_access(report_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check.expect_error())

        feedback_uid = UIDGenerator.generate_uid("ku")
        now = datetime.now().isoformat()

        query = """
        MATCH (submission:Entity {uid: $report_uid})
        OPTIONAL MATCH (student:User)-[:OWNS]->(submission)

        // Update submission with revision status
        SET submission.feedback = $notes,
            submission.feedback_generated_at = datetime($now),
            submission.status = $revision_status,
            submission.updated_at = datetime($now)

        // Create FEEDBACK_REPORT Entity nodes for revision request
        CREATE (fb:Entity {
            uid: $feedback_uid,
            title: $title,
            ku_type: $ku_type,
            user_uid: $teacher_uid,
            status: $completed_status,
            processor_type: $processor_type,
            content: $notes,
            created_by: $teacher_uid,
            created_at: datetime($now),
            updated_at: datetime($now)
        })

        // Teacher owns the feedback
        WITH submission, student, fb
        MATCH (teacher:User {uid: $teacher_uid})
        CREATE (teacher)-[:OWNS]->(fb)
        CREATE (fb)-[:FEEDBACK_FOR]->(submission)

        // Share feedback with student (if student exists)
        WITH submission, student, fb
        WHERE student IS NOT NULL
        CREATE (student)-[:SHARES_WITH {shared_at: datetime($now), role: 'student'}]->(fb)

        RETURN submission.uid as uid,
               submission.status as status,
               student.uid as student_uid,
               fb.uid as feedback_uid
        """

        result = await self.executor.execute_query(
            query,
            {
                "report_uid": report_uid,
                "feedback_uid": feedback_uid,
                "teacher_uid": teacher_uid,
                "notes": notes,
                "title": f"Revision request: {report_uid[:30]}",
                "ku_type": EntityType.FEEDBACK_REPORT.value,
                "revision_status": EntityStatus.REVISION_REQUESTED.value,
                "completed_status": EntityStatus.COMPLETED.value,
                "processor_type": ProcessorType.HUMAN.value,
                "now": now,
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
        if not records:
            return Result.fail(Errors.not_found(f"Ku {report_uid} not found"))

        student_uid = records[0]["student_uid"] or ""
        logger.info(f"Teacher {teacher_uid} requested revision {feedback_uid} for Ku {report_uid}")

        await publish_event(
            self.event_bus,
            SubmissionRevisionRequested(
                submission_uid=report_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                occurred_at=datetime.now(),
                revision_notes=notes,
                metadata={"feedback_uid": feedback_uid},
            ),
            logger,
        )

        return Result.ok(
            {
                "ku_uid": records[0]["uid"],
                "status": records[0]["status"],
                "feedback_uid": feedback_uid,
                "revision_requested": True,
            }
        )

    async def approve_report(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Approve a student Ku (mark as COMPLETED).

        Also triggers mastery updates for any curriculum Ku linked via APPLIES_KNOWLEDGE.

        Args:
            report_uid: Ku UID to approve
            teacher_uid: Teacher approving

        Returns:
            Result containing updated Ku info
        """
        access_check = await self._verify_teacher_access(report_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check.expect_error())

        query = """
        MATCH (ku:Entity {uid: $report_uid})
        SET ku.status = $status,
            ku.updated_at = datetime($now)
        WITH ku
        OPTIONAL MATCH (student:User)-[:OWNS]->(ku)
        OPTIONAL MATCH (ku)-[:APPLIES_KNOWLEDGE]->(curriculum:Entity {ku_type: 'ku'})
        RETURN ku.uid as uid,
               ku.status as status,
               student.uid as student_uid,
               collect(curriculum.uid) as linked_ku_uids
        """

        now = datetime.now().isoformat()
        result = await self.executor.execute_query(
            query,
            {
                "report_uid": report_uid,
                "now": now,
                "status": EntityStatus.COMPLETED.value,
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
        if not records:
            return Result.fail(Errors.not_found(f"Ku {report_uid} not found"))

        record = records[0]
        student_uid = record["student_uid"] or ""
        linked_ku_uids = [uid for uid in (record["linked_ku_uids"] or []) if uid]

        # Update mastery for linked curriculum entities
        mastered_count = 0
        if self.ku_interaction_service and student_uid and linked_ku_uids:
            for linked_uid in linked_ku_uids:
                mastery_result = await self.ku_interaction_service.mark_mastered(
                    user_uid=student_uid,
                    ku_uid=linked_uid,
                    mastery_score=0.8,
                    method="ku_approval",
                )
                if mastery_result.is_ok:
                    mastered_count += 1
                else:
                    logger.warning(
                        f"Failed to update mastery for KU {linked_uid}: {mastery_result.error}"
                    )

            if mastered_count > 0:
                logger.info(f"Updated mastery for {mastered_count} KUs from Ku {report_uid}")

        logger.info(f"Teacher {teacher_uid} approved Ku {report_uid}")

        await publish_event(
            self.event_bus,
            SubmissionReviewed(
                submission_uid=report_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                occurred_at=datetime.now(),
            ),
            logger,
        )

        return Result.ok(
            {
                "ku_uid": record["uid"],
                "status": record["status"],
                "approved": True,
                "mastered_ku_count": mastered_count,
            }
        )

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    async def _verify_teacher_access(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[bool]:
        """Verify teacher has SHARES_WITH access to the entity."""
        query = """
        MATCH (teacher:User {uid: $teacher_uid})-[r:SHARES_WITH {role: 'teacher'}]->(ku:Entity {uid: $report_uid})
        RETURN true as has_access
        """

        result = await self.executor.execute_query(
            query,
            {"teacher_uid": teacher_uid, "report_uid": report_uid},
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.fail(
                Errors.not_found(
                    f"Teacher {teacher_uid} does not have review access to Ku {report_uid}"
                )
            )

        return Result.ok(True)
