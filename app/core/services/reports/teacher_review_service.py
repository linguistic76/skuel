"""
Teacher Review Service
=======================

Manages the teacher review workflow for assigned reports.

Reuses SHARES_WITH infrastructure. When a student submits a report against
an ASSIGNED ReportProject, the report is auto-shared with the teacher.
The teacher's review queue = reports shared with them via role="teacher".

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from datetime import datetime
from typing import Any

from neo4j import Driver

from core.models.enums.report_enums import ReportStatus
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.teacher_review")


class TeacherReviewService:
    """Service for teacher review of student assignment submissions."""

    def __init__(self, driver: Driver) -> None:
        """
        Initialize the teacher review service.

        Args:
            driver: Neo4j driver for database operations
        """
        self.driver = driver

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get teacher's pending review queue.

        Returns reports shared with the teacher via role="teacher",
        optionally filtered by status.

        Args:
            teacher_uid: Teacher UID
            status_filter: Optional status filter (e.g., "manual_review")

        Returns:
            Result containing list of review items
        """
        status_clause = ""
        params: dict[str, Any] = {"teacher_uid": teacher_uid}

        if status_filter:
            status_clause = "AND report.status = $status_filter"
            params["status_filter"] = status_filter

        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[r:SHARES_WITH {{role: 'teacher'}}]->(report:Report)
        WHERE true {status_clause}
        OPTIONAL MATCH (student:User)-[:OWNS]->(report)
        OPTIONAL MATCH (report)-[:FULFILLS_PROJECT]->(project:ReportProject)
        RETURN report.uid as report_uid,
               report.title as title,
               report.status as status,
               report.created_at as submitted_at,
               student.uid as student_uid,
               student.name as student_name,
               project.uid as project_uid,
               project.name as project_name,
               project.due_date as due_date,
               r.shared_at as shared_at
        ORDER BY report.created_at DESC
        """

        try:
            records, _, _ = await self.driver.execute_query(query, **params)

            items = [
                {
                    "report_uid": record["report_uid"],
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
        report_uid: str,
        teacher_uid: str,
        feedback: str,
    ) -> Result[dict[str, Any]]:
        """
        Submit teacher feedback for a report.

        Updates the report's feedback field and sets status to COMPLETED.

        Args:
            report_uid: Report to provide feedback for
            teacher_uid: Teacher providing feedback
            feedback: Feedback text

        Returns:
            Result containing updated report info
        """
        # Verify teacher has SHARES_WITH access
        access_check = await self._verify_teacher_access(report_uid, teacher_uid)
        if access_check.is_error:
            return access_check

        query = """
        MATCH (report:Report {uid: $report_uid})
        SET report.feedback = $feedback,
            report.feedback_generated_at = datetime($now),
            report.status = $status,
            report.updated_at = datetime($now)
        RETURN report.uid as uid, report.status as status
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                report_uid=report_uid,
                feedback=feedback,
                now=datetime.now().isoformat(),
                status=ReportStatus.COMPLETED.value,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Report {report_uid} not found"))

            logger.info(f"Teacher {teacher_uid} submitted feedback for report {report_uid}")
            return Result.ok(
                {
                    "report_uid": records[0]["uid"],
                    "status": records[0]["status"],
                    "feedback_submitted": True,
                }
            )

        except Exception as e:
            logger.error(f"Error submitting feedback: {e}")
            return Result.fail(Errors.database("submit_feedback", str(e)))

    async def request_revision(
        self,
        report_uid: str,
        teacher_uid: str,
        notes: str,
    ) -> Result[dict[str, Any]]:
        """
        Request revision for a student report.

        Sets status to REVISION_REQUESTED and stores revision notes.

        Args:
            report_uid: Report needing revision
            teacher_uid: Teacher requesting revision
            notes: Revision notes/instructions

        Returns:
            Result containing updated report info
        """
        access_check = await self._verify_teacher_access(report_uid, teacher_uid)
        if access_check.is_error:
            return access_check

        query = """
        MATCH (report:Report {uid: $report_uid})
        SET report.feedback = $notes,
            report.feedback_generated_at = datetime($now),
            report.status = $status,
            report.updated_at = datetime($now)
        RETURN report.uid as uid, report.status as status
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                report_uid=report_uid,
                notes=notes,
                now=datetime.now().isoformat(),
                status=ReportStatus.REVISION_REQUESTED.value,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Report {report_uid} not found"))

            logger.info(f"Teacher {teacher_uid} requested revision for report {report_uid}")
            return Result.ok(
                {
                    "report_uid": records[0]["uid"],
                    "status": records[0]["status"],
                    "revision_requested": True,
                }
            )

        except Exception as e:
            logger.error(f"Error requesting revision: {e}")
            return Result.fail(Errors.database("request_revision", str(e)))

    async def approve_report(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Approve a student report (mark as COMPLETED).

        Args:
            report_uid: Report to approve
            teacher_uid: Teacher approving

        Returns:
            Result containing updated report info
        """
        access_check = await self._verify_teacher_access(report_uid, teacher_uid)
        if access_check.is_error:
            return access_check

        query = """
        MATCH (report:Report {uid: $report_uid})
        SET report.status = $status,
            report.updated_at = datetime($now)
        RETURN report.uid as uid, report.status as status
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                report_uid=report_uid,
                now=datetime.now().isoformat(),
                status=ReportStatus.COMPLETED.value,
            )

            if not records:
                return Result.fail(Errors.not_found(f"Report {report_uid} not found"))

            logger.info(f"Teacher {teacher_uid} approved report {report_uid}")
            return Result.ok(
                {
                    "report_uid": records[0]["uid"],
                    "status": records[0]["status"],
                    "approved": True,
                }
            )

        except Exception as e:
            logger.error(f"Error approving report: {e}")
            return Result.fail(Errors.database("approve_report", str(e)))

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    async def _verify_teacher_access(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[bool]:
        """Verify teacher has SHARES_WITH access to the report."""
        query = """
        MATCH (teacher:User {uid: $teacher_uid})-[r:SHARES_WITH {role: 'teacher'}]->(report:Report {uid: $report_uid})
        RETURN true as has_access
        """

        try:
            records, _, _ = await self.driver.execute_query(
                query,
                teacher_uid=teacher_uid,
                report_uid=report_uid,
            )

            if not records:
                return Result.fail(
                    Errors.not_found(
                        f"Teacher {teacher_uid} does not have review access to report {report_uid}"
                    )
                )

            return Result.ok(True)

        except Exception as e:
            logger.error(f"Error verifying teacher access: {e}")
            return Result.fail(Errors.database("verify_teacher_access", str(e)))
