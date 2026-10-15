"""
RevisedExercise Service
========================

Reads of RevisedExercises — targeted revision instructions that address
specific feedback gaps in the four-phase learning loop.

The flow:
    Exercise → UserEntry → EntryReport → RevisedExercise → UserEntry v2 → ...

A teacher sends a RevisedExercise from the review page, beside the report it
answers (``TeacherReviewService.request_revision``, ADR-091 N7, N8); nothing
edits or deletes it afterwards (N2). The student submits a new UserEntry
against the RevisedExercise via FULFILLS_EXERCISE (anchored to the root
Exercise) plus FULFILLS_REVISED_EXERCISE.
"""

from typing import ClassVar

from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.exercises.revised_exercise_dto import RevisedExerciseDTO
from core.models.relationship_names import RelationshipName
from core.ports.curriculum_protocols import RevisedExerciseBackendOperations
from core.ports.query_types import RevisionChainResult
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


class RevisedExerciseService(BaseService[RevisedExerciseBackendOperations, RevisedExercise]):
    """
    Read service for RevisedExercises (targeted revision instructions).

    RevisedExercises are teacher-owned but student-targeted. They are stored
    as :Entity:RevisedExercise nodes with entity_type='revised_exercise'.
    ``get`` is inherited from CrudOperationsMixin (via BaseService); the
    revision itself is written by the review page's one door.
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
        # A turn-in against a revision reaches it by FULFILLS_REVISED_EXERCISE
        # (its FULFILLS_EXERCISE anchors on the root exercise); one whose
        # original is gone reaches it by FULFILLS_EXERCISE. One union pattern
        # collects both.
        (
            f"{RelationshipName.FULFILLS_EXERCISE.value}|{RelationshipName.FULFILLS_REVISED_EXERCISE.value}",
            NeoLabel.ENTITY.value,
            "submissions",
            "incoming",
        ),
    )

    def __init__(
        self,
        backend: RevisedExerciseBackendOperations,
    ) -> None:
        """Initialize with the RevisedExercise backend."""
        super().__init__(backend, "revised_exercises")
        self.backend = backend
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger
        logger.info("RevisedExerciseService initialized")

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
        return await self.backend.list_for_student(student_uid, teacher_uid)

    @with_error_handling("get_by_report_uid", error_type="database")
    async def get_by_report_uid(self, report_uid: str) -> Result[RevisedExercise | None]:
        """Get the RevisedExercise responding to a given report, if any."""
        return await self.backend.get_by_report_uid(report_uid)

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
