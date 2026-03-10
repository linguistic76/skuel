"""
Exercise Service
=================

CRUD operations for Exercises (instruction templates for the core educational loop).

An Exercise is the shared, transparent instruction template:
- Teacher/admin creates exercise with visible instructions
- Instructions are editable and always shown to the user (no black box)
- User controls which LLM model to use
- scope=PERSONAL: user's own feedback template
- scope=ASSIGNED: teacher assigns to a group via FOR_GROUP relationship

When a student submits work against an ASSIGNED exercise, the submission handler
creates the FULFILLS_EXERCISE relationship and auto-shares with the teacher.

Formerly AssignmentService — renamed to Exercise for domain clarity.
"""

import json
import os
from datetime import date, datetime
from typing import Any, ClassVar

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityType, ProcessorType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.submissions_enums import ExerciseScope
from core.models.exercises.exercise import Exercise
from core.models.exercises.exercise_dto import ExerciseDTO
from core.models.relationship_names import RelationshipName
from core.ports import get_enum_value
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger(__name__)

_UNSET: Any = object()  # Sentinel for "argument not provided"


class ExerciseService(BaseService):
    """
    Simple CRUD service for Exercises (instruction templates).

    No complex logic - just create, read, update, delete operations.
    Exercises are stored as :Entity nodes with entity_type=EntityType.EXERCISE in Neo4j.
    """

    _config = DomainConfig(
        dto_class=ExerciseDTO,
        model_class=Exercise,
        entity_label="Entity",
        search_fields=("title", "instructions"),
        search_order_by="created_at",
        user_ownership_relationship=RelationshipName.OWNS,
    )

    # Graph enrichment for graph_aware_faceted_search (SearchRouter integration)
    _graph_enrichment_patterns: ClassVar[
        tuple[tuple[str, str, str] | tuple[str, str, str, str], ...]
    ] = (
        (RelationshipName.REQUIRES_KNOWLEDGE.value, NeoLabel.ENTITY.value, "required_knowledge"),
        (RelationshipName.FOR_GROUP.value, NeoLabel.GROUP.value, "for_groups"),
        (
            RelationshipName.FULFILLS_EXERCISE.value,
            NeoLabel.ENTITY.value,
            "submissions",
            "incoming",
        ),
    )

    def __init__(self, backend: Any) -> None:
        """
        Initialize with backend.

        Args:
            backend: UniversalNeo4jBackend[Exercise] instance - REQUIRED
        """
        super().__init__(backend, "exercises")
        self.backend = backend
        self.logger = logger
        logger.info("ExerciseService initialized")

    @property
    def entity_label(self) -> str:
        """Return the graph label for Exercise entities."""
        return "Entity"

    # ========================================================================
    # CREATE
    # ========================================================================

    @with_error_handling("create_exercise", error_type="database")
    async def create_exercise(
        self,
        user_uid: str,
        name: str,
        instructions: str,
        model: str = "claude-sonnet-4-6",
        context_notes: list[str] | None = None,
        domain: Domain | None = None,
        scope: ExerciseScope = ExerciseScope.PERSONAL,
        due_date: date | None = None,
        processor_type: ProcessorType = ProcessorType.LLM,
        group_uid: str | None = None,
        form_schema: list[dict[str, Any]] | None = None,
    ) -> Result[Exercise]:
        """
        Create a new Exercise.

        For ASSIGNED scope (teacher exercises):
        - group_uid is required
        - Creates a FOR_GROUP relationship to the target group

        Args:
            user_uid: User who owns this exercise
            name: Display name
            instructions: Plain text instructions for LLM
            model: LLM model to use
            context_notes: Optional reference materials
            domain: Optional domain categorization
            scope: PERSONAL (default) or ASSIGNED (teacher exercise)
            due_date: Due date for ASSIGNED scope
            processor_type: LLM, HUMAN, or HYBRID
            group_uid: Target group UID for ASSIGNED scope

        Returns:
            Result[Exercise] - The created exercise
        """
        if scope == ExerciseScope.ASSIGNED and not group_uid:
            return Result.fail(
                Errors.validation("group_uid is required for assigned exercises", field="group_uid")
            )

        uid = UIDGenerator.generate_uid("ex", name)

        exercise = Exercise(
            uid=uid,
            entity_type=EntityType.EXERCISE,
            title=name,
            instructions=instructions,
            model=model,
            context_notes=tuple(context_notes) if context_notes else (),
            domain=domain,
            scope=scope,
            due_date=due_date,
            group_uid=group_uid,
            enrichment_mode=None,
            form_schema=tuple(form_schema) if form_schema else None,
        )

        result = await self.backend.create(exercise)

        if result.is_error:
            self.logger.error(f"Failed to create exercise: {result.error}")
            return result

        # Create OWNS relationship (user → exercise)
        owns_result = await self.backend.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})
            MATCH (e:Entity {{uid: $exercise_uid}})
            MERGE (u)-[:{RelationshipName.OWNS.value}]->(e)
            RETURN true as success
            """,
            {"user_uid": user_uid, "exercise_uid": uid},
        )
        if owns_result.is_error:
            self.logger.warning(f"Failed to create OWNS relationship: {owns_result.error}")

        # Create FOR_GROUP relationship for ASSIGNED scope
        if scope == ExerciseScope.ASSIGNED and group_uid:
            rel_result = await self.backend.execute_query(
                f"""
                MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
                MATCH (group:Group {{uid: $group_uid}})
                MERGE (exercise)-[:{RelationshipName.FOR_GROUP}]->(group)
                RETURN true as success
                """,
                {"exercise_uid": uid, "group_uid": group_uid},
            )
            if rel_result.is_error:
                self.logger.warning(f"Failed to create FOR_GROUP relationship: {rel_result.error}")
            else:
                self.logger.info(f"FOR_GROUP relationship created: {uid} -> {group_uid}")

        self.logger.info(f"Exercise created: {uid} - {name} (scope={scope.value})")
        return Result.ok(exercise)

    # ========================================================================
    # READ
    # ========================================================================

    @with_error_handling("get_exercise", error_type="database")
    async def get_exercise(self, uid: str) -> Result[Exercise]:
        """Get a specific Exercise by UID."""
        result = await self.backend.get(uid)
        if result.is_error:
            return result
        if result.value is None:
            return Result.fail(Errors.not_found(resource="Exercise", identifier=uid))
        return Result.ok(result.value)

    @with_error_handling("list_user_exercises", error_type="database")
    async def list_user_exercises(
        self, user_uid: str, active_only: bool = True
    ) -> Result[list[Exercise]]:
        """List personal exercises owned by a user via OWNS relationship."""
        result = await self.backend.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(e:Exercise)
            RETURN e
            ORDER BY e.created_at DESC
            """,
            {"user_uid": user_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        exercises = []
        for record in result.value or []:
            props = record["e"]
            try:
                exercise = Exercise(**props)
                exercises.append(exercise)
            except Exception as exc:
                self.logger.warning(f"Failed to deserialize exercise: {exc}")

        self.logger.info(f"Found {len(exercises)} exercises for user {user_uid}")
        return Result.ok(exercises)

    # ========================================================================
    # UPDATE
    # ========================================================================

    @with_error_handling("update_exercise", error_type="database")
    async def update_exercise(
        self,
        uid: str,
        name: str | None = None,
        instructions: str | None = None,
        model: str | None = None,
        context_notes: list[str] | None = None,
        domain: Domain | None = None,
        is_active: bool | None = None,
        metadata: dict[str, Any] | None = None,
        form_schema: Any = _UNSET,
    ) -> Result[Exercise]:
        """
        Update an Exercise. Only provided fields will be updated.

        form_schema uses _UNSET sentinel so None means "clear the schema"
        while omitting the argument means "don't change it".
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return get_result
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Exercise", identifier=uid))

        updates: dict[str, Any] = {}
        if name is not None:
            updates["title"] = name
        if instructions is not None:
            updates["instructions"] = instructions
        if model is not None:
            updates["model"] = model
        if context_notes is not None:
            updates["context_notes"] = context_notes
        if domain is not None:
            updates["domain"] = get_enum_value(domain)
        if metadata is not None:
            updates["metadata"] = json.dumps(metadata)
        if form_schema is not _UNSET:
            # None clears the schema, list sets it (serialized as JSON for Neo4j)
            updates["form_schema"] = json.dumps(form_schema) if form_schema else None

        updates["updated_at"] = datetime.now().isoformat()

        result = await self.backend.update(uid, updates)
        if result.is_error:
            self.logger.error(f"Failed to update exercise {uid}: {result.error}")
            return result

        self.logger.info(f"Exercise updated: {uid}")
        return result

    # ========================================================================
    # EXERCISE QUERIES (ADR-040)
    # ========================================================================

    @with_error_handling("list_group_exercises", error_type="database")
    async def list_group_exercises(self, group_uid: str) -> Result[list[Exercise]]:
        """
        Get all ASSIGNED exercises for a group.

        Args:
            group_uid: Group UID

        Returns:
            Result containing list of assigned exercises
        """
        result = await self.backend.find_by(
            group_uid=group_uid, scope="assigned", entity_type=EntityType.EXERCISE.value
        )
        if result.is_error:
            return result

        exercises = result.value or []
        self.logger.info(f"Found {len(exercises)} exercises for group {group_uid}")
        return Result.ok(exercises)

    @with_error_handling("get_student_exercises", error_type="database")
    async def get_student_exercises(self, user_uid: str) -> Result[list[Exercise]]:
        """
        Get all exercises for a student (via MEMBER_OF -> Group <- FOR_GROUP -> Exercise).

        Args:
            user_uid: Student UID

        Returns:
            Result containing list of assigned exercises
        """
        result = await self.backend.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            MATCH (exercise:Entity {{entity_type: 'exercise'}})-[:{RelationshipName.FOR_GROUP}]->(group)
            WHERE exercise.scope = 'assigned'
            RETURN exercise
            ORDER BY exercise.due_date ASC, exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        exercises = []
        for record in result.value or []:
            props = record["exercise"]
            try:
                exercise = Exercise(**props)
                exercises.append(exercise)
            except Exception as e:
                self.logger.warning(f"Failed to deserialize exercise: {e}")

        self.logger.info(f"Found {len(exercises)} exercises for student {user_uid}")
        return Result.ok(exercises)

    @with_error_handling("get_student_exercises_with_status", error_type="database")
    async def get_student_exercises_with_status(
        self, user_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get assigned exercises with submission status for the student assignments page.

        Returns exercise properties enriched with has_submission flag and group_name.
        """
        result = await self.backend.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            MATCH (exercise:Entity {{entity_type: 'exercise'}})-[:{RelationshipName.FOR_GROUP}]->(group)
            WHERE exercise.scope = 'assigned'
            OPTIONAL MATCH (user)-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            RETURN exercise, sub IS NOT NULL AS has_submission, group.title AS group_name
            ORDER BY exercise.due_date ASC, exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        exercises = []
        for record in result.value or []:
            props = dict(record["exercise"])
            props["has_submission"] = record.get("has_submission", False)
            props["group_name"] = record.get("group_name", "")
            exercises.append(props)

        self.logger.info(f"Found {len(exercises)} exercises with status for student {user_uid}")
        return Result.ok(exercises)

    # ========================================================================
    # FILE-BASED EXERCISE LOADING
    # ========================================================================

    async def seed_default_project(
        self,
        instructions_path: str | None = None,
        project_uid: str = "jp.transcript_default",
        model: str = "gpt-4o",
    ) -> Result[Exercise]:
        """Load/update default transcript project from instructions file.

        Called at startup to ensure default exercises exist.
        Encapsulates file resolution, system user ownership, and idempotent create/update.
        """
        from pathlib import Path

        path = instructions_path or os.getenv(
            "SKUEL_TRANSCRIPT_INSTRUCTIONS_PATH",
            str(Path(__file__).parents[3] / "data" / "instructions - transcripts 0.md"),
        )

        return await self.load_project_from_file(
            file_path=path,
            user_uid="user_system",
            project_uid=project_uid,
            model=model,
        )

    async def load_project_from_file(
        self, file_path: str, user_uid: str, project_uid: str | None = None, model: str = "gpt-4o"
    ) -> Result[Exercise]:
        """
        Load or update an Exercise from a markdown instructions file.
        """
        try:
            from pathlib import Path

            path = Path(file_path)
            if not path.exists():
                return Result.fail(
                    Errors.validation(
                        f"Instructions file not found: {file_path}", field="file_path"
                    )
                )

            instructions = path.read_text(encoding="utf-8")
            name = path.stem.replace("instructions - ", "").replace("instructions-", "").title()
            if not name or name == "Instructions":
                name = path.stem.title()

            if project_uid:
                existing = await self.backend.get(project_uid)
                if existing.is_ok and existing.value:
                    result = await self.update_exercise(
                        uid=project_uid, instructions=instructions, model=model
                    )
                    self.logger.info(f"Exercise updated from file: {project_uid} - {file_path}")
                    return result
                else:
                    exercise_result = await self.create_exercise(
                        user_uid=user_uid,
                        name=name,
                        instructions=instructions,
                        model=model,
                    )
                    if exercise_result.is_error:
                        return exercise_result
                    # Override UID if specified
                    await self.update_exercise(
                        uid=exercise_result.value.uid,
                        metadata={"source_file": str(file_path)},
                    )
                    self.logger.info(
                        f"Exercise created from file: {exercise_result.value.uid} - {file_path}"
                    )
                    return exercise_result
            else:
                exercise_result = await self.create_exercise(
                    user_uid=user_uid,
                    name=name,
                    instructions=instructions,
                    model=model,
                )
                if exercise_result.is_ok:
                    await self.update_exercise(
                        uid=exercise_result.value.uid,
                        metadata={"source_file": str(file_path)},
                    )
                    self.logger.info(
                        f"Exercise created from file: {exercise_result.value.uid} - {file_path}"
                    )
                return exercise_result

        except Exception as e:
            self.logger.error(f"Error loading exercise from file {file_path}: {e}")
            return Result.fail(
                Errors.system(
                    f"Failed to load exercise from file: {e!s}",
                    operation="load_project_from_file",
                )
            )

    # ========================================================================
    # DELETE
    # ========================================================================

    @with_error_handling("delete_exercise", error_type="database")
    async def delete_exercise(self, uid: str) -> Result[bool]:
        """Delete an Exercise."""
        result = await self.backend.delete(uid)
        if result.is_error:
            return result
        self.logger.info(f"Exercise deleted: {uid}")
        return Result.ok(True)

    async def deactivate_exercise(self, uid: str) -> Result[Exercise]:
        """Soft-delete by archiving exercise."""
        updates: dict[str, Any] = {
            "status": "archived",
            "updated_at": datetime.now().isoformat(),
        }
        return await self.backend.update(uid, updates)

    # ========================================================================
    # CURRICULUM LINKING
    # ========================================================================

    @with_error_handling("link_to_curriculum", error_type="database")
    async def link_to_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """
        Link an exercise to a curriculum KU via REQUIRES_KNOWLEDGE.

        This declares that the exercise requires understanding of the
        curriculum knowledge unit — completing the learning pipeline:
        Curriculum → Exercise → Submission → Feedback

        Args:
            exercise_uid: Exercise UID (entity_type='exercise')
            curriculum_uid: Curriculum KU UID (entity_type='ku')

        Returns:
            Result[bool] - True if relationship created
        """
        result = await self.backend.link_to_curriculum(exercise_uid, curriculum_uid)
        if result.is_ok:
            self.logger.info(f"Linked exercise {exercise_uid} to curriculum {curriculum_uid}")
        return result

    @with_error_handling("unlink_from_curriculum", error_type="database")
    async def unlink_from_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """
        Remove REQUIRES_KNOWLEDGE relationship between exercise and curriculum KU.

        Args:
            exercise_uid: Exercise UID
            curriculum_uid: Curriculum KU UID

        Returns:
            Result[bool] - True if relationship removed
        """
        result = await self.backend.unlink_from_curriculum(exercise_uid, curriculum_uid)
        if result.is_ok:
            self.logger.info(f"Unlinked exercise {exercise_uid} from curriculum {curriculum_uid}")
        return result

    @with_error_handling("get_required_knowledge", error_type="database")
    async def get_required_knowledge(self, exercise_uid: str) -> Result[list[dict[str, Any]]]:
        """
        Get all curriculum KUs required by an exercise.

        Args:
            exercise_uid: Exercise UID

        Returns:
            Result containing list of curriculum KU summaries
        """
        result = await self.backend.get_required_knowledge(exercise_uid)
        if result.is_ok:
            self.logger.info(
                f"Found {len(result.value or [])} required knowledge items for exercise {exercise_uid}"
            )
        return result

    @with_error_handling("get_exercise_for_submission", error_type="database")
    async def get_exercise_for_submission(
        self, submission_uid: str
    ) -> Result[dict[str, Any] | None]:
        """Get the exercise that a submission fulfills via FULFILLS_EXERCISE relationship."""
        return await self.backend.get_exercise_for_submission(submission_uid)

    @with_error_handling("get_exercises_for_curriculum", error_type="database")
    async def get_exercises_for_curriculum(
        self, curriculum_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all exercises that require a specific curriculum KU.

        Enables the reverse lookup: "what exercises practice this knowledge?"

        Args:
            curriculum_uid: Curriculum KU UID

        Returns:
            Result containing list of exercise summaries
        """
        result = await self.backend.execute_query(
            f"""
            MATCH (exercise:Entity {{entity_type: 'exercise'}})
                  -[:{RelationshipName.REQUIRES_KNOWLEDGE}]->
                  (curriculum:Entity {{uid: $curriculum_uid}})
            RETURN exercise.uid as uid,
                   exercise.title as title,
                   exercise.scope as scope,
                   exercise.due_date as due_date,
                   exercise.status as status,
                   exercise.form_schema as form_schema
            ORDER BY exercise.created_at DESC
            """,
            {"curriculum_uid": curriculum_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        exercises = [dict(record) for record in (result.value or [])]
        self.logger.info(f"Found {len(exercises)} exercises for curriculum {curriculum_uid}")
        return Result.ok(exercises)
