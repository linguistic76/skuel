"""
Assessment Service
==================

Read the teacher-authored assessments (HUMAN EntryReports) a student has
received, for the UserEntry domain.

Assessments are EntryReport entities with entity_type=ENTRY_REPORT. The student
owns the report — ``(student)-[:OWNS]->(report)`` is THE visibility anchor for
the student's received-feedback reads. Teacher-authored feedback is *written*
by ``TeacherReviewService`` (submission-anchored review); this service serves
the student's received-feedback query behind the ``AssessmentOperations`` port.

Moved from core/services/submissions/ per ADR-054.
"""

from typing import Any, cast

from core.models.report.entry_report import EntryReport
from core.models.report.entry_report_dto import EntryReportDTO
from core.ports.user_entry_protocols import UserEntryOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.user_entry.assessments")


class AssessmentService:
    """
    Read a student's received teacher assessments.

    Standalone service (not BaseService) — receives the UserEntry backend in
    the constructor and serves the received-feedback query behind the
    ``AssessmentOperations`` port.
    """

    def __init__(self, backend: UserEntryOperations) -> None:
        self.backend = backend
        self.logger = logger

    @with_error_handling("get_assessments_for_student", error_type="database")
    async def get_assessments_for_student(
        self, student_uid: str, limit: int = 50
    ) -> Result[list[EntryReport]]:
        """
        Get assessments received by a student.

        Args:
            student_uid: Student user UID
            limit: Maximum number of assessments to return

        Returns:
            Result containing list of ENTRY_REPORT entities
        """
        result = await self.backend.get_assessments_for_student_raw(student_uid, limit)

        if result.is_error:
            return Result.fail(result)

        reports = []
        for record in result.value or []:
            # record["report"] is a nested node-map; the flat Neo4jProperties
            # alias can't express nested dicts. boundary: neo4j-node-map
            node = cast("dict[str, Any]", record["report"])
            dto = EntryReportDTO.from_dict(node)
            reports.append(EntryReport.from_dto(dto))
        return Result.ok(reports)
