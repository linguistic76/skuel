"""
RevisedExercise Service
========================

CRUD operations for RevisedExercises — targeted revision instructions that
address specific feedback gaps in the four-phase learning loop.

The flow:
    Exercise → UserEntry → EntryReport → RevisedExercise → UserEntry v2 → ...

A teacher creates a RevisedExercise after reviewing EntryReport, providing
targeted instructions for the student to address specific gaps. The student
submits a new UserEntry against the RevisedExercise via FULFILLS_EXERCISE
(anchored to the root Exercise) plus FULFILLS_REVISED_EXERCISE.

Implements CRUDOperations via BaseService inheritance (CrudOperationsMixin).
Overrides create/delete to add authority checks, relationships, events, and cascade.
"""

import contextlib
import dataclasses
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from core.events import publish_event
from core.events.embedding_publisher import publish_embedding_requested
from core.events.learning_loop_events import RevisedExerciseCreated
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.exercises.revised_exercise_dto import RevisedExerciseDTO
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID
from core.ports.curriculum_protocols import RevisedExerciseBackendOperations
from core.ports.query_types import RevisionChainResult
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations

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

    def __init__(
        self,
        backend: RevisedExerciseBackendOperations,
        event_bus: "EventBusOperations | None" = None,
    ) -> None:
        """Initialize with backend and optional event bus."""
        super().__init__(backend, "revised_exercises")
        self.backend = backend
        self.event_bus = event_bus
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger
        logger.info("RevisedExerciseService initialized")

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

        Access control: Verifies the student_uid owns the submission linked
        to the report (OWNS-based, per ADR-040). Teacher identity is
        role-gated at the route level.
        """
        teacher_uid = entity.user_uid

        # Required-field guard: these are nullable on the model (frozen-base
        # field-ordering forces defaults) but a RevisedExercise cannot be
        # created without them. Bind validated str locals for the rest of the flow.
        report_uid = entity.report_uid
        student_uid = entity.student_uid
        original_exercise_uid = entity.original_exercise_uid
        if not report_uid or not student_uid or not original_exercise_uid:
            return Result.fail(
                Errors.validation(
                    "RevisedExercise requires report_uid, student_uid, and original_exercise_uid.",
                    field="report_uid",
                )
            )

        # Verify teacher has review authority over this report/student
        auth_result = await self._verify_teacher_authority(teacher_uid, report_uid, student_uid)
        if auth_result.is_error:
            return Result.fail(auth_result)

        # Auto-resolve submission_uid from authority query result
        auth_records = auth_result.value
        submission_uid = entity.submission_uid
        if not submission_uid and auth_records:
            submission_uid = auth_records[0].get("submission_uid")

        # Auto-resolve expected_modality from original Exercise
        expected_modality = entity.expected_modality
        if not expected_modality and entity.original_exercise_uid:
            exercise_result = await self.backend.get(entity.original_exercise_uid)
            if exercise_result.is_ok and exercise_result.value:
                from core.models.enums.user_entry_enums import SubmissionModality

                raw_modality = exercise_result.value.get("expected_modality")
                if raw_modality:
                    with contextlib.suppress(ValueError):
                        expected_modality = SubmissionModality(raw_modality)

        # Next per-(exercise, student) ordinal — max+1, never a global count
        number_result = await self.backend.get_next_revision_number(
            original_exercise_uid, student_uid
        )
        if number_result.is_error:
            return Result.fail(number_result)
        revision_number = number_result.value

        # Enrich entity with computed fields. created_by feeds Shared-With-Me
        # sharer attribution — every SHARES_WITH writer must stamp it.
        display_title = entity.title or f"Revision {revision_number}"
        enriched = dataclasses.replace(
            entity,
            revision_number=revision_number,
            title=display_title,
            submission_uid=submission_uid,
            expected_modality=expected_modality,
            parent_entity_uid=EntityUID(report_uid),
            created_by=entity.created_by or teacher_uid,
        )

        result = await self.backend.create(enriched)
        if result.is_error:
            self.logger.error(f"Failed to create revised exercise: {result.error}")
            return result

        uid = enriched.uid

        # Create OWNS relationship (teacher → revised_exercise)
        owns_result = await self.backend.create_owns_relationship(teacher_uid, uid)
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
        share_result = await self.backend.auto_share_with_student(
            enriched.student_uid, uid, datetime.now().isoformat()
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
                student_uid=student_uid,
                original_exercise_uid=original_exercise_uid,
                report_uid=report_uid,
                revision_number=revision_number,
            ),
            self.logger,
        )

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(
            self.event_bus, EntityType.REVISED_EXERCISE, enriched, self.logger
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
    ) -> Result[list[dict[str, str]]]:
        """Verify the teacher has review authority over the feedback.

        Checks the graph path (OWNS-based, per ADR-040):
        - (EntryReport)-[:REPORT_FOR]->(UserEntry) exists
        - (Student)-[:OWNS]->(UserEntry)
        Teacher identity is role-gated at the route level.

        Returns the matched records (including submission_uid) on success.
        """
        result = await self.backend.verify_teacher_authority(teacher_uid, report_uid, student_uid)
        if result.is_error:
            return Result.fail(result)

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
        return Result.ok(records)

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
        result = await self.backend.list_for_student(student_uid, teacher_uid)
        if result.is_error:
            return Result.fail(result)

        exercises = []
        for record in result.value or []:
            props = record["re"]
            try:
                exercises.append(RevisedExercise(**props))
            except DATA_CONVERSION_EXCEPTIONS as exc:
                self.logger.warning(f"Failed to deserialize revised exercise: {exc}")

        return Result.ok(exercises)

    @with_error_handling("get_by_report_uid", error_type="database")
    async def get_by_report_uid(self, report_uid: str) -> Result[RevisedExercise | None]:
        """Get the RevisedExercise responding to a given report, if any."""
        result = await self.backend.get_by_report_uid(report_uid)
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        props = records[0]["re"]
        try:
            return Result.ok(RevisedExercise(**props))
        except DATA_CONVERSION_EXCEPTIONS as exc:
            self.logger.warning(
                f"Failed to deserialize revised exercise for report {report_uid}: {exc}"
            )
            return Result.ok(None)

    @with_error_handling("get_revision_chain", error_type="database")
    async def get_revision_chain(
        self, exercise_uid: str, teacher_uid: str, student_uid: str | None = None
    ) -> Result[list[RevisionChainResult]]:
        """List an exercise's revisions for the teacher's own classrooms.

        Scoped to students in active groups the teacher owns — the same
        audience the revision write uses (ADR-040; #887 read-scope class).
        An out-of-classroom read is an empty chain, indistinguishable from
        a nonexistent exercise.
        """
        return await self.backend.get_revision_chain(exercise_uid, teacher_uid, student_uid)
