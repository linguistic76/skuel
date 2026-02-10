"""
Teacher Review Service
=======================

Manages the teacher review workflow for assigned Ku submissions.

Reuses SHARES_WITH infrastructure. When a student submits a Ku against
an ASSIGNED KuProject, the Ku is auto-shared with the teacher.
The teacher's review queue = Ku shared with them via role="teacher".

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from datetime import datetime
from typing import Any

from neo4j import Driver

from core.models.enums.ku_enums import KuStatus
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.teacher_review")


class TeacherReviewService:
    """Service for teacher review of student Ku submissions."""

    def __init__(
        self,
        driver: Driver,
        ku_interaction_service: Any | None = None,
    ) -> None:
        """
        Initialize the teacher review service.

        Args:
            driver: Neo4j driver for database operations
            ku_interaction_service: Optional KU interaction service for mastery updates
        """
        self.driver = driver
        self.ku_interaction_service = ku_interaction_service

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get teacher's pending review queue.

        Returns Ku shared with the teacher via role="teacher",
        optionally filtered by status.

        Args:
            teacher_uid: Teacher UID
            status_filter: Optional status filter (e.g., "submitted")

        Returns:
            Result containing list of review items
        """
        status_clause = ""
        params: dict[str, Any] = {"teacher_uid": teacher_uid}

        if status_filter:
            status_clause = "AND ku.status = $status_filter"
            params["status_filter"] = status_filter

        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[r:SHARES_WITH {{role: 'teacher'}}]->(ku:Ku)
        WHERE true {status_clause}
        OPTIONAL MATCH (student:User)-[:OWNS]->(ku)
        OPTIONAL MATCH (ku)-[:FULFILLS_PROJECT]->(project:KuProject)
        RETURN ku.uid as ku_uid,
               ku.title as title,
               ku.status as status,
               ku.created_at as submitted_at,
               student.uid as student_uid,
               student.name as student_name,
               project.uid as project_uid,
               project.name as project_name,
               project.due_date as due_date,
               r.shared_at as shared_at
        ORDER BY ku.created_at DESC
        """

        try:
            records, _, _ = await self.driver.execute_query(query, **params)

            items = [
                {
                    "ku_uid": record["ku_uid"],
                    "title": record["title"],
                    "status": record["status"],
                    "submitted_at": record["submitted_at"],
                    "student_uid": record["student_uid"],
                    "student_name": record["student_name"],
                    "project_uid": record["project_uid"],
                    "project_name": record["project_name"],
                    "due_date": record["due_date"],
                    "shared_at": record["shared_at"],
                }
                for record in records
            ]

            return Result.ok(items)

        except Exception as e:
            logger.error(f"Error fetching review queue: {e}")
            return Result.fail(Errors.database("get_review_queue", str(e)))

    async def submit_feedback(
        self,
        ku_uid: str,
        teacher_uid: str,
        feedback: str,
    ) -> Result[dict[str, Any]]:
        """
        Submit teacher feedback for a Ku.

        Updates the Ku's feedback field and sets status to COMPLETED.

        Args:
            ku_uid: Ku to provide feedback for
            teacher_uid: Teacher providing feedback
            feedback: Feedback text

        Returns:
            Result containing updated Ku info
        """
        access_check = await self._verify_teacher_access(ku_uid, teacher_uid)
        if access_check.is_error:
            return access_check

        query = """
        MATCH (ku:Ku {uid: $ku_uid})
        SET ku.feedback = $feedback,
            ku.feedback_generated_at = datetime($now),
            ku.status = $status,
            ku.updated_at = datetime($now)
        RETURN ku.uid as uid, ku.status as status
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                ku_uid=ku_uid,
                feedback=feedback,
                now=datetime.now().isoformat(),
                status=KuStatus.COMPLETED.value,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Ku {ku_uid} not found"))

            logger.info(f"Teacher {teacher_uid} submitted feedback for Ku {ku_uid}")
            return Result.ok(
                {
                    "ku_uid": records[0]["uid"],
                    "status": records[0]["status"],
                    "feedback_submitted": True,
                }
            )

        except Exception as e:
            logger.error(f"Error submitting feedback: {e}")
            return Result.fail(Errors.database("submit_feedback", str(e)))

    async def request_revision(
        self,
        ku_uid: str,
        teacher_uid: str,
        notes: str,
    ) -> Result[dict[str, Any]]:
        """
        Request revision for a student Ku.

        Sets status to REVISION_REQUESTED and stores revision notes.

        Args:
            ku_uid: Ku needing revision
            teacher_uid: Teacher requesting revision
            notes: Revision notes/instructions

        Returns:
            Result containing updated Ku info
        """
        access_check = await self._verify_teacher_access(ku_uid, teacher_uid)
        if access_check.is_error:
            return access_check

        query = """
        MATCH (ku:Ku {uid: $ku_uid})
        SET ku.feedback = $notes,
            ku.feedback_generated_at = datetime($now),
            ku.status = $status,
            ku.updated_at = datetime($now)
        RETURN ku.uid as uid, ku.status as status
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                ku_uid=ku_uid,
                notes=notes,
                now=datetime.now().isoformat(),
                status=KuStatus.REVISION_REQUESTED.value,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Ku {ku_uid} not found"))

            logger.info(f"Teacher {teacher_uid} requested revision for Ku {ku_uid}")
            return Result.ok(
                {
                    "ku_uid": records[0]["uid"],
                    "status": records[0]["status"],
                    "revision_requested": True,
                }
            )

        except Exception as e:
            logger.error(f"Error requesting revision: {e}")
            return Result.fail(Errors.database("request_revision", str(e)))

    async def approve_ku(
        self,
        ku_uid: str,
        teacher_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Approve a student Ku (mark as COMPLETED).

        Also triggers mastery updates for any curriculum Ku linked via APPLIES_KNOWLEDGE.

        Args:
            ku_uid: Ku to approve
            teacher_uid: Teacher approving

        Returns:
            Result containing updated Ku info
        """
        access_check = await self._verify_teacher_access(ku_uid, teacher_uid)
        if access_check.is_error:
            return access_check

        query = """
        MATCH (ku:Ku {uid: $ku_uid})
        SET ku.status = $status,
            ku.updated_at = datetime($now)
        WITH ku
        OPTIONAL MATCH (student:User)-[:OWNS]->(ku)
        OPTIONAL MATCH (ku)-[:APPLIES_KNOWLEDGE]->(curriculum:Ku {ku_type: 'curriculum'})
        RETURN ku.uid as uid,
               ku.status as status,
               student.uid as student_uid,
               collect(curriculum.uid) as linked_ku_uids
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                ku_uid=ku_uid,
                now=datetime.now().isoformat(),
                status=KuStatus.COMPLETED.value,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Ku {ku_uid} not found"))

            record = records[0]
            student_uid = record["student_uid"]
            linked_ku_uids = [uid for uid in (record["linked_ku_uids"] or []) if uid]

            # Update mastery for linked curriculum Ku
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
                    logger.info(
                        f"Updated mastery for {mastered_count} KUs from Ku {ku_uid}"
                    )

            logger.info(f"Teacher {teacher_uid} approved Ku {ku_uid}")
            return Result.ok(
                {
                    "ku_uid": record["uid"],
                    "status": record["status"],
                    "approved": True,
                    "mastered_ku_count": mastered_count,
                }
            )

        except Exception as e:
            logger.error(f"Error approving Ku: {e}")
            return Result.fail(Errors.database("approve_ku", str(e)))

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    async def _verify_teacher_access(
        self,
        ku_uid: str,
        teacher_uid: str,
    ) -> Result[bool]:
        """Verify teacher has SHARES_WITH access to the Ku."""
        query = """
        MATCH (teacher:User {uid: $teacher_uid})-[r:SHARES_WITH {role: 'teacher'}]->(ku:Ku {uid: $ku_uid})
        RETURN true as has_access
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                teacher_uid=teacher_uid,
                ku_uid=ku_uid,
            )

            if not records:
                return Result.fail(
                    Errors.not_found(
                        f"Teacher {teacher_uid} does not have review access to Ku {ku_uid}"
                    )
                )

            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error verifying teacher access: {e}")
            return Result.fail(Errors.database("verify_teacher_access", str(e)))
