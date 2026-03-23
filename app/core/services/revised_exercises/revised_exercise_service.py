"""
RevisedExercise Service
========================

CRUD operations for RevisedExercises — targeted revision instructions that
address specific feedback gaps in the five-phase learning loop.

The flow:
    Exercise → Submission → SubmissionReport → RevisedExercise → Submission v2 → ...

A teacher creates a RevisedExercise after reviewing SubmissionReport, providing
targeted instructions for the student to address specific gaps. The student
submits against the RevisedExercise via FULFILLS_EXERCISE (same relationship
as regular Exercise submissions).

Implements CRUDOperations via BaseService inheritance (CrudOperationsMixin).
Overrides create/delete to add authority checks, relationships, events, and cascade.
"""

import dataclasses
from datetime import datetime
from typing import Any, ClassVar

from core.events import RevisedExerciseEmbeddingRequested, publish_event
from core.events.submission_events import RevisedExerciseCreated
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.exercises.revised_exercise_dto import RevisedExerciseDTO
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class RevisedExerciseService(BaseService):
    """
    CRUD service for RevisedExercises (targeted revision instructions).

    RevisedExercises are teacher-owned but student-targeted. They are stored
    as :Entity:RevisedExercise nodes with entity_type='revised_exercise'.

    Inherits CRUDOperations from CrudOperationsMixin (via BaseService):
    create, get, update, delete, list, get_for_user, update_for_user, delete_for_user.

    Overrides create/delete to add authority verification, graph relationships,
    auto-sharing, and domain events.
    """

    _config = DomainConfig(
        dto_class=RevisedExerciseDTO,
        model_class=RevisedExercise,
        entity_label="Entity",
        search_fields=("title", "instructions"),
        search_order_by="created_at",
        user_ownership_relationship=RelationshipName.OWNS,
    )

    # Graph enrichment for graph_aware_faceted_search (SearchRouter integration)
    _graph_enrichment_patterns: ClassVar[
        tuple[tuple[str, str, str] | tuple[str, str, str, str], ...]
    ] = (
        (
            RelationshipName.RESPONDS_TO_REPORT.value,
            NeoLabel.ENTITY.value,
            "responds_to_feedback",
        ),
        (RelationshipName.REVISES_EXERCISE.value, NeoLabel.ENTITY.value, "revises_exercise"),
        (
            RelationshipName.FULFILLS_EXERCISE.value,
            NeoLabel.ENTITY.value,
            "submissions",
            "incoming",
        ),
    )

    def __init__(self, backend: Any, event_bus: Any | None = None) -> None:
        """Initialize with backend and optional event bus."""
        super().__init__(backend, "revised_exercises")
        self.backend = backend
        self.event_bus = event_bus
        self.logger = logger
        logger.info("RevisedExerciseService initialized")

    @property
    def entity_label(self) -> str:
        """Return the graph label for RevisedExercise entities."""
        return "Entity"

    # ========================================================================
    # CRUD OVERRIDES (authority checks, relationships, events)
    # ========================================================================

    async def create(self, entity: RevisedExercise) -> Result[RevisedExercise]:
        """
        Create a new RevisedExercise with authority verification and relationships.

        Creates the entity plus three relationships:
        - OWNS (teacher → revised_exercise)
        - RESPONDS_TO_REPORT (revised_exercise → report)
        - REVISES_EXERCISE (revised_exercise → original exercise)

        Also auto-shares with the student and publishes domain events.

        Access control: Verifies the teacher has SHARES_WITH {role:'teacher'}
        on the submission linked to the report, and the student_uid owns
        that submission.
        """
        teacher_uid = entity.user_uid

        # Verify teacher has review authority over this report/student
        auth_result = await self._verify_teacher_authority(
            teacher_uid, entity.report_uid, entity.student_uid
        )
        if auth_result.is_error:
            return Result.fail(auth_result.expect_error())

        # Determine revision number from existing chain
        chain_result = await self.backend.get_revision_chain(entity.original_exercise_uid)
        revision_number = 1
        if chain_result.is_ok and chain_result.value:
            revision_number = len(chain_result.value) + 1

        # Enrich entity with computed revision_number and default title
        display_title = entity.title or f"Revision {revision_number}"
        enriched = dataclasses.replace(
            entity,
            revision_number=revision_number,
            title=display_title,
        )

        result = await self.backend.create(enriched)
        if result.is_error:
            self.logger.error(f"Failed to create revised exercise: {result.error}")
            return result

        uid = enriched.uid

        # Create OWNS relationship (teacher → revised_exercise)
        owns_result = await self.backend.execute_query(
            f"""
            MATCH (u:User {{uid: $teacher_uid}})
            MATCH (re:Entity {{uid: $re_uid}})
            MERGE (u)-[:{RelationshipName.OWNS.value}]->(re)
            RETURN true as success
            """,
            {"teacher_uid": teacher_uid, "re_uid": uid},
        )
        if owns_result.is_error:
            self.logger.warning(f"Failed to create OWNS relationship: {owns_result.error}")

        # Create RESPONDS_TO_REPORT relationship
        feedback_result = await self.backend.link_to_report(uid, enriched.report_uid)
        if feedback_result.is_error:
            self.logger.warning(f"Failed to create RESPONDS_TO_REPORT: {feedback_result.error}")

        # Create REVISES_EXERCISE relationship
        exercise_result = await self.backend.link_to_exercise(uid, enriched.original_exercise_uid)
        if exercise_result.is_error:
            self.logger.warning(f"Failed to create REVISES_EXERCISE: {exercise_result.error}")

        # Auto-share with student so it appears in their "Shared With Me" inbox.
        # Same pattern as assignment auto-sharing (ADR-040).
        share_result = await self.backend.execute_query(
            f"""
            MATCH (student:User {{uid: $student_uid}})
            MATCH (re:Entity {{uid: $re_uid}})
            MERGE (student)-[r:{RelationshipName.SHARES_WITH.value}]->(re)
            ON CREATE SET r.shared_at = $shared_at, r.role = 'student'
            SET re.visibility = 'shared'
            RETURN true as success
            """,
            {
                "student_uid": enriched.student_uid,
                "re_uid": uid,
                "shared_at": datetime.now().isoformat(),
            },
        )
        if share_result.is_error:
            self.logger.warning(f"Failed to auto-share with student: {share_result.error}")

        self.logger.info(
            f"RevisedExercise created: {uid} (revision {revision_number} "
            f"of {enriched.original_exercise_uid} for {enriched.student_uid})"
        )

        # Publish event for downstream coordination (notifications, dashboard)
        await publish_event(
            self.event_bus,
            RevisedExerciseCreated(
                revised_exercise_uid=uid,
                teacher_uid=teacher_uid,
                student_uid=enriched.student_uid,
                original_exercise_uid=enriched.original_exercise_uid,
                report_uid=enriched.report_uid,
                revision_number=revision_number,
                occurred_at=datetime.now(),
            ),
            self.logger,
        )

        # Publish embedding request (background worker generates async)
        embedding_text = build_embedding_text(EntityType.REVISED_EXERCISE, enriched)
        if embedding_text:
            now = datetime.now()
            await publish_event(
                self.event_bus,
                RevisedExerciseEmbeddingRequested(
                    entity_uid=uid,
                    entity_type="revised_exercise",
                    embedding_text=embedding_text,
                    user_uid=teacher_uid,
                    requested_at=now,
                    occurred_at=now,
                ),
                self.logger,
            )

        return Result.ok(enriched)

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """Delete a RevisedExercise with cascade to remove all relationships."""
        result = await super().delete(uid, cascade=True)
        if result.is_error:
            return result
        self.logger.info(f"RevisedExercise deleted: {uid}")
        return result

    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================

    @with_error_handling("verify_teacher_authority", error_type="database")
    async def _verify_teacher_authority(
        self,
        teacher_uid: str,
        report_uid: str,
        student_uid: str,
    ) -> Result[bool]:
        """Verify the teacher has review authority over the feedback.

        Checks the graph path:
        - (SubmissionReport)-[:REPORT_FOR]->(Submission) exists
        - (Teacher)-[:SHARES_WITH {role:'teacher'}]->(Submission)
        - (Student)-[:OWNS]->(Submission)
        """
        result = await self.backend.execute_query(
            """
            MATCH (fb:Entity {uid: $report_uid})-[:REPORT_FOR]->(submission:Entity)
            MATCH (teacher:User {uid: $teacher_uid})-[:SHARES_WITH {role: 'teacher'}]->(submission)
            MATCH (student:User {uid: $student_uid})-[:OWNS]->(submission)
            RETURN submission.uid AS submission_uid
            """,
            {
                "report_uid": report_uid,
                "teacher_uid": teacher_uid,
                "student_uid": student_uid,
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        if not records:
            return Result.fail(
                Errors.validation(
                    "Teacher does not have review authority over this feedback. "
                    "The feedback must be linked to a submission that is shared "
                    "with the teacher and owned by the specified student.",
                    field="report_uid",
                )
            )
        return Result.ok(True)

    # ========================================================================
    # DOMAIN-SPECIFIC QUERIES (not part of CRUDOperations)
    # ========================================================================

    @with_error_handling("list_for_student", error_type="database")
    async def list_for_student(
        self, student_uid: str, teacher_uid: str | None = None
    ) -> Result[list[RevisedExercise]]:
        """List revised exercises targeting a specific student.

        Args:
            student_uid: The student whose revisions to list.
            teacher_uid: If provided, only return revisions owned by this teacher.
                Used by teacher-facing routes to prevent cross-teacher leakage.
                Omitted for student-facing routes (students see all their own revisions).
        """
        if teacher_uid:
            query = f"""
            MATCH (u:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(re:RevisedExercise {{student_uid: $student_uid}})
            RETURN re
            ORDER BY re.created_at DESC
            """
            params = {"student_uid": student_uid, "teacher_uid": teacher_uid}
        else:
            query = """
            MATCH (re:RevisedExercise {student_uid: $student_uid})
            RETURN re
            ORDER BY re.created_at DESC
            """
            params = {"student_uid": student_uid}

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        exercises = []
        for record in result.value or []:
            props = record["re"]
            try:
                exercises.append(RevisedExercise(**props))
            except DATA_CONVERSION_EXCEPTIONS as exc:
                self.logger.warning(f"Failed to deserialize revised exercise: {exc}")

        return Result.ok(exercises)

    @with_error_handling("get_revision_chain", error_type="database")
    async def get_revision_chain(self, exercise_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all revisions in the chain for an original exercise."""
        return await self.backend.get_revision_chain(exercise_uid)
