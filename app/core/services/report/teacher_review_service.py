"""
Teacher Review Service
=======================

Manages the teacher review workflow for assigned Ku submissions.

Reuses SHARES_WITH infrastructure. When a student submits an entity against
an ASSIGNED Exercise, the entity is auto-shared with the teacher.
The teacher's review queue = Ku shared with them via role="teacher".

When providing a report or requesting revision, a SUBMISSION_REPORT Entity nodes
is created and linked to the submission via REPORT_FOR. This makes every
report round a first-class graph entity — searchable, queryable, and
supporting revision cycles.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
See: /docs/architecture/SUBMISSION_FEEDBACK_LOOP.md
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
        optionally filtered by status or entity_type. Includes count of
        existing feedback rounds per submission.

        Args:
            teacher_uid: Teacher UID
            status_filter: Optional status filter (e.g., "submitted")
            ku_type_filter: Optional entity_type filter (e.g., "submission", "task")

        Returns:
            Result containing list of review items
        """
        where_clauses = []
        params: dict[str, Any] = {"teacher_uid": teacher_uid}

        if status_filter:
            where_clauses.append("report.status = $status_filter")
            params["status_filter"] = status_filter

        if ku_type_filter:
            where_clauses.append("report.entity_type = $ku_type_filter")
            params["ku_type_filter"] = ku_type_filter

        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[r:SHARES_WITH {{role: 'teacher'}}]->(ku:Entity:Submission)
        {where_clause}
        OPTIONAL MATCH (student:User)-[:OWNS]->(ku)
        OPTIONAL MATCH (ku)-[:FULFILLS_EXERCISE]->(project:Entity:Exercise)
        OPTIONAL MATCH (fb:Entity:SubmissionReport)-[:REPORT_FOR]->(ku)
        WITH ku, student, project, r, count(fb) as feedback_count
        RETURN ku.uid as ku_uid,
               ku.title as title,
               ku.status as status,
               ku.entity_type as entity_type,
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
                "entity_type": record["entity_type"],
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

    async def get_report_history(
        self,
        submission_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all SUBMISSION_REPORT nodes linked to a submission via REPORT_FOR.

        Args:
            submission_uid: The submission Ku UID

        Returns:
            Result containing list of report items ordered by creation date
        """
        query = """
        MATCH (fb:Entity:SubmissionReport)-[:REPORT_FOR]->(submission:Entity:Submission {uid: $submission_uid})
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

    async def submit_report(
        self,
        report_uid: str,
        teacher_uid: str,
        feedback: str,
    ) -> Result[dict[str, Any]]:
        """
        Submit teacher report for an entity.

        Creates a SUBMISSION_REPORT Entity nodes linked to the submission via REPORT_FOR.
        Also writes report to submission's report field (denormalized for quick access)
        and sets submission status to COMPLETED.

        Args:
            report_uid: Submission Ku UID to provide report for
            teacher_uid: Teacher providing report
            feedback: SubmissionReport text

        Returns:
            Result containing report Ku info
        """
        access_check = await self._verify_teacher_access(report_uid, teacher_uid)
        if access_check.is_error:
            return Result.fail(access_check.expect_error())

        report_entity_uid = UIDGenerator.generate_uid("ku")
        now = datetime.now().isoformat()

        # Create SUBMISSION_REPORT node, link via REPORT_FOR, share with student,
        # and update submission status — all in one transaction
        query = """
        MATCH (submission:Entity {uid: $report_uid})
        OPTIONAL MATCH (student:User)-[:OWNS]->(submission)

        // Update submission with denormalized report content
        SET submission.report_content = $feedback,
            submission.report_generated_at = datetime($now),
            submission.status = $completed_status,
            submission.updated_at = datetime($now)

        // Create SUBMISSION_REPORT Entity nodes
        CREATE (fb:Entity {
            uid: $report_entity_uid,
            title: $title,
            entity_type: $entity_type,
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
        CREATE (fb)-[:REPORT_FOR]->(submission)

        // Share feedback with student (if student exists)
        WITH submission, student, fb
        WHERE student IS NOT NULL
        CREATE (student)-[:SHARES_WITH {shared_at: datetime($now), role: 'student'}]->(fb)

        RETURN submission.uid as uid,
               submission.status as status,
               student.uid as student_uid,
               fb.uid as report_entity_uid
        """

        result = await self.executor.execute_query(
            query,
            {
                "report_uid": report_uid,
                "report_entity_uid": report_entity_uid,
                "teacher_uid": teacher_uid,
                "feedback": feedback,
                "title": f"Feedback: {report_uid[:30]}",
                "entity_type": EntityType.SUBMISSION_REPORT.value,
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
        logger.info(f"Teacher {teacher_uid} submitted report {report_entity_uid} for Ku {report_uid}")

        await publish_event(
            self.event_bus,
            ReportSubmitted(
                submission_uid=report_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                report_uid=report_entity_uid,
                occurred_at=datetime.now(),
            ),
            logger,
        )

        return Result.ok(
            {
                "ku_uid": records[0]["uid"],
                "status": records[0]["status"],
                "report_uid": report_entity_uid,
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

        Creates a SUBMISSION_REPORT Entity nodes with revision notes, linked via REPORT_FOR.
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

        report_entity_uid = UIDGenerator.generate_uid("ku")
        now = datetime.now().isoformat()

        query = """
        MATCH (submission:Entity {uid: $report_uid})
        OPTIONAL MATCH (student:User)-[:OWNS]->(submission)

        // Update submission with revision status
        SET submission.report_content = $notes,
            submission.report_generated_at = datetime($now),
            submission.status = $revision_status,
            submission.updated_at = datetime($now)

        // Create SUBMISSION_REPORT Entity nodes for revision request
        CREATE (fb:Entity {
            uid: $report_entity_uid,
            title: $title,
            entity_type: $entity_type,
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
        CREATE (fb)-[:REPORT_FOR]->(submission)

        // Share feedback with student (if student exists)
        WITH submission, student, fb
        WHERE student IS NOT NULL
        CREATE (student)-[:SHARES_WITH {shared_at: datetime($now), role: 'student'}]->(fb)

        RETURN submission.uid as uid,
               submission.status as status,
               student.uid as student_uid,
               fb.uid as report_entity_uid
        """

        result = await self.executor.execute_query(
            query,
            {
                "report_uid": report_uid,
                "report_entity_uid": report_entity_uid,
                "teacher_uid": teacher_uid,
                "notes": notes,
                "title": f"Revision request: {report_uid[:30]}",
                "entity_type": EntityType.SUBMISSION_REPORT.value,
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
        logger.info(f"Teacher {teacher_uid} requested revision {report_entity_uid} for Ku {report_uid}")

        await publish_event(
            self.event_bus,
            SubmissionRevisionRequested(
                submission_uid=report_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                occurred_at=datetime.now(),
                revision_notes=notes,
                metadata={"report_uid": report_entity_uid},
            ),
            logger,
        )

        return Result.ok(
            {
                "ku_uid": records[0]["uid"],
                "status": records[0]["status"],
                "report_uid": report_entity_uid,
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
        OPTIONAL MATCH (ku)-[:APPLIES_KNOWLEDGE]->(curriculum:Entity:Ku)
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
            SubmissionApproved(
                submission_uid=report_uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                occurred_at=datetime.now(),
                mastered_ku_count=mastered_count,
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

    async def get_exercises_with_submission_counts(
        self,
        teacher_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get teacher's exercises with submission and reviewed counts.

        Args:
            teacher_uid: Teacher UID

        Returns:
            Result containing list of exercise dicts with uid, title, scope,
            created_at, total_count, reviewed_count, pending_count
        """
        query = """
        MATCH (user:User {uid: $teacher_uid})-[:OWNS]->(exercise:Entity:Exercise)
        OPTIONAL MATCH (s:Entity:Submission)-[:FULFILLS_EXERCISE]->(exercise)
        WITH exercise, count(s) AS total_count,
             count(CASE WHEN s.status = 'completed' THEN 1 END) AS reviewed_count
        RETURN exercise.uid AS uid, exercise.title AS title,
               exercise.scope AS scope, exercise.created_at AS created_at,
               total_count, reviewed_count,
               total_count - reviewed_count AS pending_count
        ORDER BY exercise.created_at DESC
        """

        result = await self.executor.execute_query(query, {"teacher_uid": teacher_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

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
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all submissions against a specific exercise.

        Args:
            exercise_uid: Exercise UID to fetch submissions for

        Returns:
            Result containing list of submission dicts with student info
            and feedback count
        """
        query = """
        MATCH (s:Entity:Submission)-[:FULFILLS_EXERCISE]->(e:Entity:Exercise {uid: $exercise_uid})
        OPTIONAL MATCH (student:User)-[:OWNS]->(s)
        OPTIONAL MATCH (fb:Entity:SubmissionReport)-[:REPORT_FOR]->(s)
        WITH s, student, count(fb) AS feedback_count
        RETURN s.uid AS uid, s.title AS title,
               s.original_filename AS original_filename, s.status AS status,
               s.created_at AS created_at, student.uid AS student_uid,
               student.name AS student_name, feedback_count
        ORDER BY s.created_at DESC
        """

        result = await self.executor.execute_query(query, {"exercise_uid": exercise_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

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
    ) -> Result[list[dict[str, Any]]]:
        """
        Get students who have shared work with this teacher, with counts.

        Args:
            teacher_uid: Teacher UID

        Returns:
            Result containing list of student dicts with submission_count,
            reviewed_count, pending_count, ordered by pending descending
        """
        query = """
        MATCH (teacher:User {uid: $teacher_uid})-[:SHARES_WITH {role: 'teacher'}]->(ku:Entity:Submission)
        OPTIONAL MATCH (student:User)-[:OWNS]->(ku)
        WITH student, count(ku) AS submission_count,
             count(CASE WHEN ku.status = 'completed' THEN 1 END) AS reviewed_count
        WHERE student IS NOT NULL
        RETURN student.uid AS student_uid, student.name AS student_name,
               submission_count, reviewed_count,
               submission_count - reviewed_count AS pending_count
        ORDER BY pending_count DESC, submission_count DESC
        """

        result = await self.executor.execute_query(query, {"teacher_uid": teacher_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

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
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all submissions from a student that were shared with this teacher.

        Args:
            teacher_uid: Teacher UID
            student_uid: Student UID

        Returns:
            Result containing list of submission dicts with exercise context
            and feedback count
        """
        query = """
        MATCH (teacher:User {uid: $teacher_uid})-[:SHARES_WITH {role: 'teacher'}]->(ku:Entity:Submission)
        MATCH (student:User {uid: $student_uid})-[:OWNS]->(ku)
        OPTIONAL MATCH (fb:Entity:SubmissionReport)-[:REPORT_FOR]->(ku)
        OPTIONAL MATCH (ku)-[:FULFILLS_EXERCISE]->(ex:Entity:Exercise)
        WITH ku, count(fb) AS feedback_count, ex
        RETURN ku.uid AS uid, ku.title AS title,
               ku.original_filename AS original_filename, ku.status AS status,
               ku.created_at AS created_at,
               feedback_count, ex.uid AS exercise_uid, ex.title AS exercise_title
        ORDER BY ku.created_at DESC
        """

        result = await self.executor.execute_query(
            query, {"teacher_uid": teacher_uid, "student_uid": student_uid}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

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
        query = """
        MATCH (teacher:User {uid: $teacher_uid})-[:SHARES_WITH {role: 'teacher'}]->(s:Entity:Submission {uid: $submission_uid})
        OPTIONAL MATCH (student:User)-[:OWNS]->(s)
        OPTIONAL MATCH (s)-[:FULFILLS_EXERCISE]->(ex:Entity:Exercise)
        RETURN s.uid AS uid,
               s.title AS title,
               s.content AS content,
               s.processed_content AS processed_content,
               s.original_filename AS original_filename,
               s.entity_type AS entity_type,
               s.status AS status,
               s.created_at AS created_at,
               student.uid AS student_uid,
               student.name AS student_name,
               ex.uid AS exercise_uid,
               ex.title AS exercise_title,
               ex.instructions AS exercise_instructions
        """

        result = await self.executor.execute_query(
            query, {"submission_uid": submission_uid, "teacher_uid": teacher_uid}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

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
        query = """
        MATCH (teacher:User {uid: $teacher_uid})
        OPTIONAL MATCH (teacher)-[:SHARES_WITH {role: 'teacher'}]->(ku:Entity:Submission)
        OPTIONAL MATCH (student:User)-[:OWNS]->(ku)
        OPTIONAL MATCH (teacher)-[:OWNS]->(ex:Entity:Exercise)
        OPTIONAL MATCH (teacher)-[:OWNS]->(g:Group)
        RETURN
          count(CASE WHEN ku.status IN ['submitted', 'active', 'revision_requested'] THEN 1 END) AS pending_count,
          count(DISTINCT ku) AS total_submissions,
          count(DISTINCT student) AS total_students,
          count(DISTINCT ex) AS total_exercises,
          count(DISTINCT g) AS total_groups
        """

        result = await self.executor.execute_query(query, {"teacher_uid": teacher_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

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
    ) -> Result[list[dict[str, Any]]]:
        """
        Get teacher's groups with member, exercise, and pending submission counts.

        Args:
            teacher_uid: Teacher UID

        Returns:
            Result containing list of group stat dicts
        """
        query = """
        MATCH (teacher:User {uid: $teacher_uid})-[:OWNS]->(g:Group)
        OPTIONAL MATCH (member:User)-[:MEMBER_OF]->(g)
        OPTIONAL MATCH (ex:Entity:Exercise)-[:FOR_GROUP]->(g)
        OPTIONAL MATCH (sub:Entity:Submission)-[:FULFILLS_EXERCISE]->(ex)
          WHERE sub.status NOT IN ['completed', 'archived']
        RETURN g.uid AS uid,
               g.name AS name,
               g.description AS description,
               g.is_active AS is_active,
               count(DISTINCT member) AS member_count,
               count(DISTINCT ex) AS exercise_count,
               count(DISTINCT sub) AS pending_count
        ORDER BY g.created_at DESC
        """

        result = await self.executor.execute_query(query, {"teacher_uid": teacher_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

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
    ) -> Result[list[dict[str, Any]]]:
        """
        Get members of a teacher's group with their submission progress.

        Access-checked: only succeeds if teacher owns the group.

        Args:
            group_uid: Group UID
            teacher_uid: Teacher UID (ownership checked)

        Returns:
            Result containing list of member dicts with progress stats
        """
        query = """
        MATCH (teacher:User {uid: $teacher_uid})-[:OWNS]->(g:Group {uid: $group_uid})
        MATCH (member:User)-[r:MEMBER_OF]->(g)
        OPTIONAL MATCH (teacher)-[:SHARES_WITH {role: 'teacher'}]->(sub:Entity:Submission)
          WHERE (member)-[:OWNS]->(sub)
        RETURN member.uid AS user_uid,
               member.name AS user_name,
               r.role AS role,
               r.joined_at AS joined_at,
               count(sub) AS submission_count,
               count(CASE WHEN sub.status = 'completed' THEN 1 END) AS reviewed_count,
               count(CASE WHEN sub.status IN ['submitted', 'active', 'revision_requested'] THEN 1 END) AS pending_count
        ORDER BY r.joined_at
        """

        result = await self.executor.execute_query(
            query, {"group_uid": group_uid, "teacher_uid": teacher_uid}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

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
