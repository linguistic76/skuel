"""
Assessment Service
==================

Teacher assessment workflow operations extracted from SubmissionsCoreService.

Handles:
- Creating teacher assessments (EXERCISE_REPORT entities) with authority verification
- Querying assessments received by a student
- Querying assessments authored by a teacher

Assessments are SubmissionReport entities with entity_type=EXERCISE_REPORT,
linked to students via ASSESSMENT_OF relationships and auto-shared via SHARES_WITH.
"""

from datetime import datetime
from typing import Any

from core.events import publish_event
from core.events.submission_events import AssessmentCreated
from core.models.entity import Entity
from core.models.entity_types import SubmissionEntity
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.report.submission_report import SubmissionReport
from core.models.submissions.submission_dto import SubmissionDTO
from core.ports import BackendOperations
from core.ports.infrastructure_protocols import EventBusOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.submissions.assessments")


def _get_created_at_key(submission: SubmissionEntity) -> datetime:
    """Get created_at from entity for sorting, with fallback to datetime.min."""
    return submission.created_at if submission.created_at else datetime.min


class AssessmentService:
    """
    Teacher assessment workflow operations.

    Standalone service (not BaseService) — receives backend and event_bus
    in constructor. Handles authority verification, ASSESSMENT_OF relationship
    creation, auto-sharing with students, and assessment queries.
    """

    def __init__(
        self,
        backend: BackendOperations[SubmissionEntity],
        event_bus: EventBusOperations | None = None,
    ) -> None:
        self.backend = backend
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
    ) -> Result[SubmissionReport]:
        """
        Create a teacher assessment (feedback) for a student.

        Creates a submission with entity_type=EXERCISE_REPORT, auto-shares with student.
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
        authority_result = await self.backend.verify_teacher_authority(teacher_uid, subject_uid)  # type: ignore[attr-defined]

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

        uid = UIDGenerator.generate_uid("sr")

        assessment = SubmissionReport(
            uid=uid,
            title=title,
            entity_type=EntityType.EXERCISE_REPORT,
            user_uid=teacher_uid,
            status=EntityStatus.COMPLETED,
            processor_type=ProcessorType.HUMAN,
            content=content,
            subject_uid=subject_uid,
            created_by=teacher_uid,
            visibility=Visibility.SHARED,
            metadata=metadata,
        )

        result = await self.backend.create(assessment)
        if result.is_error:
            return Result.fail(result)

        # Create ASSESSMENT_OF relationship
        assess_result = await self.backend.create_assessment_relationship(uid, subject_uid)  # type: ignore[attr-defined]

        if assess_result.is_error:
            self.logger.error(f"Failed to create ASSESSMENT_OF relationship: {assess_result.error}")
            return Result.fail(Errors.database("create_assessment", str(assess_result.error)))

        if not (assess_result.value or []):
            self.logger.error(f"ASSESSMENT_OF not created: student {subject_uid} not found")
            return Result.fail(
                Errors.database("create_assessment", "Failed to create ASSESSMENT_OF relationship")
            )

        # Auto-share with student
        share_result = await self.backend.auto_share_assessment_with_student(  # type: ignore[attr-defined]
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
            submission_uid=uid,
            teacher_uid=teacher_uid,
            subject_uid=subject_uid,
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(f"Created assessment {uid}: teacher={teacher_uid}, student={subject_uid}")
        return Result.ok(assessment)

    @with_error_handling("get_assessments_for_student", error_type="database")
    async def get_assessments_for_student(
        self, student_uid: str, limit: int = 50
    ) -> Result[list[SubmissionEntity]]:
        """
        Get assessments received by a student.

        Args:
            student_uid: Student user UID
            limit: Maximum number of assessments to return

        Returns:
            Result containing list of EXERCISE_REPORT entities
        """
        result = await self.backend.get_assessments_for_student_raw(student_uid, limit)  # type: ignore[attr-defined]

        if result.is_error:
            return Result.fail(result)

        reports = []
        for record in result.value or []:
            node = record["report"]
            dto = SubmissionDTO.from_dict(node)
            reports.append(Entity.from_dto(dto))
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
            Result containing list of EXERCISE_REPORT entities
        """
        result = await self.backend.find_by(
            user_uid=teacher_uid,
            entity_type=EntityType.EXERCISE_REPORT.value,
        )
        if result.is_error:
            return Result.fail(result)

        reports = result.value or []
        reports.sort(key=_get_created_at_key, reverse=True)
        return Result.ok(reports[:limit])
