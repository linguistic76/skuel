"""
Assessment Service
==================

Teacher assessment workflow operations for the UserEntry domain.

Handles:
- Creating teacher assessments (ENTRY_REPORT entities) with authority verification
- Querying assessments received by a student
- Querying assessments authored by a teacher

Assessments are EntryReport entities with entity_type=ENTRY_REPORT. The student
owns the report — ``(student)-[:OWNS]->(report)`` is auto-created from
``user_uid`` at node creation and is THE visibility anchor for the student's
received-feedback reads — and the report is auto-shared via SHARES_WITH.

Moved from core/services/submissions/ per ADR-054.
"""

from datetime import datetime
from typing import Any, cast

from core.events import publish_event
from core.events.learning_loop_events import AssessmentCreated
from core.models.entity_types import SubmissionEntity
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.pipeline import ReportSource
from core.models.report.entry_report import EntryReport
from core.models.report.entry_report_dto import EntryReportDTO
from core.models.type_hints import UserUID
from core.ports.infrastructure_protocols import EventBusOperations
from core.ports.report_protocols import EntryReportBackendOperations
from core.ports.user_entry_protocols import UserEntryOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.user_entry.assessments")


def _get_created_at_key(submission: SubmissionEntity) -> datetime:
    """Get created_at from entity for sorting, with fallback to datetime.min."""
    return submission.created_at if submission.created_at else datetime.min


class AssessmentService:
    """
    Teacher assessment workflow operations.

    Standalone service (not BaseService) — receives backend and event_bus
    in constructor. Handles authority verification, auto-sharing with
    students, and assessment queries.
    """

    def __init__(
        self,
        backend: UserEntryOperations,
        report_backend: EntryReportBackendOperations,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        self.backend = backend
        # Canonical report-node creation goes through the EntryReport backend
        # so assessment nodes carry :Entity:EntryReport labels (not :UserEntry).
        # The UserEntry backend still serves the assessment's relationship/query ops.
        self.report_backend = report_backend
        self.event_bus = event_bus
        self.logger = logger

    @with_error_handling("create_assessment", error_type="database")
    async def create_assessment(
        self,
        teacher_uid: str,
        subject_uid: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Result[EntryReport]:
        """
        Create a teacher assessment (feedback) for a student.

        Creates a submission with entity_type=ENTRY_REPORT, auto-shares with student.
        Verifies teacher has authority over student via shared group membership.

        Args:
            teacher_uid: Teacher creating the assessment
            subject_uid: Student being assessed
            title: Assessment title
            content: Assessment content (markdown)
            metadata: Optional additional metadata

        Returns:
            Result containing the created submission, or forbidden error if no shared group
        """
        from core.models.enums.metadata_enums import Visibility

        # Verify teacher has authority over student (share an active group)
        authority_result = await self.backend.verify_teacher_authority(teacher_uid, subject_uid)

        if authority_result.is_error:
            self.logger.error(
                f"Failed to verify teacher-student authority: {authority_result.error}"
            )
            return Result.fail(Errors.database("create_assessment", str(authority_result.error)))

        authority_records = authority_result.value or []
        if not authority_records:
            return Result.fail(
                Errors.forbidden(
                    "create_assessment",
                    f"Teacher {teacher_uid} does not have authority over student {subject_uid} "
                    "(no shared group)",
                )
            )

        uid = UIDGenerator.generate_uid("er")

        assessment = EntryReport(
            uid=uid,
            title=title,
            entity_type=EntityType.ENTRY_REPORT,
            user_uid=UserUID(subject_uid),
            author_uid=teacher_uid,
            status=EntityStatus.COMPLETED,
            processor_type=ReportSource.HUMAN,
            content=content,
            subject_uid=subject_uid,
            created_by=teacher_uid,
            visibility=Visibility.SHARED,
            metadata=metadata or {},
        )

        # The student owns the report: create() auto-writes
        # (student)-[:OWNS]->(report) from user_uid=subject_uid, which is the
        # visibility anchor the /entry-reports listing reads by.
        result = await self.report_backend.create(assessment)
        if result.is_error:
            return Result.fail(result)

        # Auto-share with student
        share_result = await self.backend.auto_share_assessment_with_student(
            subject_uid, uid, datetime.now().isoformat()
        )

        if share_result.is_error:
            self.logger.error(f"Failed to auto-share assessment with student: {share_result.error}")
            return Result.fail(Errors.database("create_assessment", str(share_result.error)))

        if not (share_result.value or []):
            self.logger.error(f"SHARES_WITH not created for student {subject_uid}")
            return Result.fail(
                Errors.database("create_assessment", "Failed to auto-share assessment with student")
            )

        # Publish event
        event = AssessmentCreated(
            entity_uid=uid,
            teacher_uid=teacher_uid,
            subject_uid=subject_uid,
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(f"Created assessment {uid}: teacher={teacher_uid}, student={subject_uid}")
        return Result.ok(assessment)

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

    @with_error_handling("get_assessments_by_teacher", error_type="database")
    async def get_assessments_by_teacher(
        self, teacher_uid: str, limit: int = 50
    ) -> Result[list[SubmissionEntity]]:
        """
        Get assessments authored by a teacher.

        Args:
            teacher_uid: Teacher user UID
            limit: Maximum number of assessments to return

        Returns:
            Result containing list of ENTRY_REPORT entities
        """
        result = await self.backend.find_by(
            author_uid=teacher_uid,
            entity_type=EntityType.ENTRY_REPORT.value,
        )
        if result.is_error:
            return Result.fail(result)

        reports = result.value or []
        reports.sort(key=_get_created_at_key, reverse=True)
        return Result.ok(reports[:limit])
