"""
RevisedExercise Service
========================

CRUD operations for RevisedExercises — targeted revision instructions that
address specific feedback gaps in the five-phase learning loop.

The flow:
    Exercise → Submission → SubmissionFeedback → RevisedExercise → Submission v2 → ...

A teacher creates a RevisedExercise after reviewing SubmissionFeedback, providing
targeted instructions for the student to address specific gaps. The student
submits against the RevisedExercise via FULFILLS_EXERCISE (same relationship
as regular Exercise submissions).
"""

from datetime import datetime
from typing import Any, ClassVar

from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.exercises.revised_exercise_dto import RevisedExerciseDTO
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger(__name__)


class RevisedExerciseService(BaseService):
    """
    CRUD service for RevisedExercises (targeted revision instructions).

    RevisedExercises are teacher-owned but student-targeted. They are stored
    as :Entity:RevisedExercise nodes with entity_type='revised_exercise'.
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
            RelationshipName.RESPONDS_TO_FEEDBACK.value,
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
    # CREATE
    # ========================================================================

    @with_error_handling("verify_teacher_authority", error_type="database")
    async def _verify_teacher_authority(
        self,
        teacher_uid: str,
        feedback_uid: str,
        student_uid: str,
    ) -> Result[bool]:
        """Verify the teacher has review authority over the feedback.

        Checks the graph path:
        - (Feedback)-[:FEEDBACK_FOR]->(Submission) exists
        - (Teacher)-[:SHARES_WITH {role:'teacher'}]->(Submission)
        - (Student)-[:OWNS]->(Submission)
        """
        result = await self.backend.execute_query(
            """
            MATCH (fb:Entity {uid: $feedback_uid})-[:FEEDBACK_FOR]->(submission:Entity)
            MATCH (teacher:User {uid: $teacher_uid})-[:SHARES_WITH {role: 'teacher'}]->(submission)
            MATCH (student:User {uid: $student_uid})-[:OWNS]->(submission)
            RETURN submission.uid AS submission_uid
            """,
            {
                "feedback_uid": feedback_uid,
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
                    field="feedback_uid",
                )
            )
        return Result.ok(True)

    @with_error_handling("create_revised_exercise", error_type="database")
    async def create_revised_exercise(
        self,
        teacher_uid: str,
        original_exercise_uid: str,
        feedback_uid: str,
        student_uid: str,
        instructions: str,
        title: str | None = None,
        model: str = "claude-sonnet-4-6",
        context_notes: list[str] | None = None,
        feedback_points_addressed: list[str] | None = None,
        revision_rationale: str | None = None,
    ) -> Result[RevisedExercise]:
        """
        Create a new RevisedExercise.

        Creates the entity plus three relationships:
        - OWNS (teacher → revised_exercise)
        - RESPONDS_TO_FEEDBACK (revised_exercise → feedback)
        - REVISES_EXERCISE (revised_exercise → original exercise)

        Access control: Verifies the teacher has SHARES_WITH {role:'teacher'}
        on the submission linked to the feedback, and the student_uid owns
        that submission.

        Args:
            teacher_uid: Teacher who creates this revision
            original_exercise_uid: UID of the original Exercise
            feedback_uid: UID of the SubmissionFeedback this addresses
            student_uid: UID of the student this targets
            instructions: Revision instructions
            title: Display title (auto-generated if not provided)
            model: LLM model to use
            context_notes: Optional reference materials
            feedback_points_addressed: Specific feedback points targeted
            revision_rationale: Why this revision was created

        Returns:
            Result[RevisedExercise] - The created revised exercise
        """
        # Verify teacher has review authority over this feedback/student
        auth_result = await self._verify_teacher_authority(teacher_uid, feedback_uid, student_uid)
        if auth_result.is_error:
            return Result.fail(auth_result.expect_error())

        # Determine revision number from existing chain
        chain_result = await self.backend.get_revision_chain(original_exercise_uid)
        revision_number = 1
        if chain_result.is_ok and chain_result.value:
            revision_number = len(chain_result.value) + 1

        display_title = title or f"Revision {revision_number}"
        uid = UIDGenerator.generate_uid("re", display_title)

        revised_exercise = RevisedExercise(
            uid=uid,
            entity_type=EntityType.REVISED_EXERCISE,
            title=display_title,
            user_uid=teacher_uid,
            revision_number=revision_number,
            original_exercise_uid=original_exercise_uid,
            feedback_uid=feedback_uid,
            student_uid=student_uid,
            instructions=instructions,
            model=model,
            context_notes=tuple(context_notes) if context_notes else (),
            feedback_points_addressed=(
                tuple(feedback_points_addressed) if feedback_points_addressed else ()
            ),
            revision_rationale=revision_rationale,
        )

        result = await self.backend.create(revised_exercise)
        if result.is_error:
            self.logger.error(f"Failed to create revised exercise: {result.error}")
            return result

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

        # Create RESPONDS_TO_FEEDBACK relationship
        feedback_result = await self.backend.link_to_feedback(uid, feedback_uid)
        if feedback_result.is_error:
            self.logger.warning(f"Failed to create RESPONDS_TO_FEEDBACK: {feedback_result.error}")

        # Create REVISES_EXERCISE relationship
        exercise_result = await self.backend.link_to_exercise(uid, original_exercise_uid)
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
                "student_uid": student_uid,
                "re_uid": uid,
                "shared_at": datetime.now().isoformat(),
            },
        )
        if share_result.is_error:
            self.logger.warning(f"Failed to auto-share with student: {share_result.error}")

        self.logger.info(
            f"RevisedExercise created: {uid} (revision {revision_number} "
            f"of {original_exercise_uid} for {student_uid})"
        )

        # Publish event for downstream coordination (notifications, dashboard)
        from core.events import publish_event
        from core.events.submission_events import RevisedExerciseCreated

        await publish_event(
            self.event_bus,
            RevisedExerciseCreated(
                revised_exercise_uid=uid,
                teacher_uid=teacher_uid,
                student_uid=student_uid,
                original_exercise_uid=original_exercise_uid,
                feedback_uid=feedback_uid,
                revision_number=revision_number,
                occurred_at=datetime.now(),
            ),
            self.logger,
        )

        # Publish embedding request (background worker generates async)
        from core.utils.embedding_text_builder import build_embedding_text

        embedding_text = build_embedding_text(EntityType.REVISED_EXERCISE, revised_exercise)
        if embedding_text:
            from core.events import RevisedExerciseEmbeddingRequested

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

        return Result.ok(revised_exercise)

    # ========================================================================
    # READ
    # ========================================================================

    @with_error_handling("get_revised_exercise", error_type="database")
    async def get_revised_exercise(self, uid: str) -> Result[RevisedExercise]:
        """Get a specific RevisedExercise by UID."""
        result = await self.backend.get(uid)
        if result.is_error:
            return result
        if result.value is None:
            return Result.fail(Errors.not_found(resource="RevisedExercise", identifier=uid))
        return Result.ok(result.value)

    @with_error_handling("list_for_teacher", error_type="database")
    async def list_for_teacher(self, teacher_uid: str) -> Result[list[RevisedExercise]]:
        """List all revised exercises owned by a teacher."""
        result = await self.backend.execute_query(
            f"""
            MATCH (u:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(re:RevisedExercise)
            RETURN re
            ORDER BY re.created_at DESC
            """,
            {"teacher_uid": teacher_uid},
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        exercises = []
        for record in result.value or []:
            props = record["re"]
            try:
                exercises.append(RevisedExercise(**props))
            except Exception as exc:
                self.logger.warning(f"Failed to deserialize revised exercise: {exc}")

        return Result.ok(exercises)

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
            except Exception as exc:
                self.logger.warning(f"Failed to deserialize revised exercise: {exc}")

        return Result.ok(exercises)

    @with_error_handling("get_revision_chain", error_type="database")
    async def get_revision_chain(self, exercise_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all revisions in the chain for an original exercise."""
        return await self.backend.get_revision_chain(exercise_uid)

    # ========================================================================
    # UPDATE
    # ========================================================================

    @with_error_handling("update_revised_exercise", error_type="database")
    async def update_revised_exercise(
        self,
        uid: str,
        instructions: str | None = None,
        title: str | None = None,
        model: str | None = None,
        context_notes: list[str] | None = None,
        feedback_points_addressed: list[str] | None = None,
        revision_rationale: str | None = None,
    ) -> Result[RevisedExercise]:
        """Update a RevisedExercise. Only provided fields will be updated."""
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return get_result
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="RevisedExercise", identifier=uid))

        updates: dict[str, Any] = {}
        if title is not None:
            updates["title"] = title
        if instructions is not None:
            updates["instructions"] = instructions
        if model is not None:
            updates["model"] = model
        if context_notes is not None:
            updates["context_notes"] = context_notes
        if feedback_points_addressed is not None:
            updates["feedback_points_addressed"] = feedback_points_addressed
        if revision_rationale is not None:
            updates["revision_rationale"] = revision_rationale

        updates["updated_at"] = datetime.now().isoformat()

        result = await self.backend.update(uid, updates)
        if result.is_error:
            self.logger.error(f"Failed to update revised exercise {uid}: {result.error}")
            return result

        self.logger.info(f"RevisedExercise updated: {uid}")
        return result

    # ========================================================================
    # DELETE
    # ========================================================================

    @with_error_handling("delete_revised_exercise", error_type="database")
    async def delete_revised_exercise(self, uid: str) -> Result[bool]:
        """Delete a RevisedExercise."""
        result = await self.backend.delete(uid)
        if result.is_error:
            return result
        self.logger.info(f"RevisedExercise deleted: {uid}")
        return Result.ok(True)
