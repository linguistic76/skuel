"""
Exercise Service
=================

CRUD operations for Exercises (instruction templates for the core educational loop).

An Exercise is the shared, transparent instruction template:
- Teacher/admin creates exercise with visible instructions
- Instructions are editable and always shown to the user (no black box)
- User controls which LLM model to use
- scope=PERSONAL: user's own feedback template
- scope=ASSIGNED: teacher assigns to a group via SHARED_WITH_GROUP relationship
  (unified sharing, ADR-053; supersedes the retired FOR_GROUP edge)

When a student submits work against an ASSIGNED exercise, the submission handler
creates the FULFILLS_EXERCISE relationship and auto-shares with the teacher.

Formerly AssignmentService — renamed to Exercise for domain clarity.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, ClassVar

from core.constants import ExerciseTimeEstimate
from core.models.enums import Domain
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import ReportSource
from core.models.enums.user_entry_enums import ExerciseScope
from core.models.exercises.exercise import Exercise
from core.models.exercises.exercise_dto import ExerciseDTO
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.ports import get_enum_value
from core.ports.query_types import (
    CurriculumExerciseResult,
    ExerciseStatusRow,
    RequiredKnowledgeResult,
)
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.filtered_context import build_filtered_context
from core.utils.decorators import with_error_handling
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, FILE_IO_EXCEPTIONS
from core.utils.list_helpers import SortConfig, apply_entity_sort
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_created_at_attr, get_title_lower
from core.utils.uid_generator import UIDGenerator

logger = get_logger(__name__)

_UNSET: Any = object()  # Sentinel for "argument not provided"

if TYPE_CHECKING:
    from datetime import date

    from core.models.context_types import ContextualExercise
    from core.ports.query_types import ListContext
    from core.services.user.unified_user_context import RichUserContext


def _compute_exercise_stats(all_exercises: list[Any]) -> dict[str, int | float]:
    """Compute pre-filter stats from the full exercise set."""
    total = len(all_exercises)
    return {
        "total": total,
        "active": total,
        "personal": sum(
            1 for e in all_exercises if getattr(e, "scope", None) == ExerciseScope.PERSONAL
        ),
        "assigned": sum(
            1 for e in all_exercises if getattr(e, "scope", None) == ExerciseScope.ASSIGNED
        ),
        "assessment": sum(
            1 for e in all_exercises if getattr(e, "scope", None) == ExerciseScope.ASSESSMENT
        ),
    }


_EXERCISE_SORT_CONFIG: SortConfig = {
    "title": (get_title_lower, False),
    "created_at": (get_created_at_attr, True),
}


def _apply_exercise_sort(exercises: list[Any], sort_by: str) -> list[Any]:
    """Sort exercises using declarative config."""
    return apply_entity_sort(exercises, sort_by, _EXERCISE_SORT_CONFIG, "title")


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
        (RelationshipName.SHARED_WITH_GROUP.value, NeoLabel.GROUP.value, "shared_groups"),
        (
            RelationshipName.FULFILLS_EXERCISE.value,
            NeoLabel.ENTITY.value,
            "submissions",
            "incoming",
        ),
    )

    def __init__(self, backend: Any, sharing_service: Any = None) -> None:
        """
        Initialize with backend.

        Args:
            backend: UniversalNeo4jBackend[Exercise] instance - REQUIRED
            sharing_service: UnifiedSharingService — wired after bootstrap
                to avoid a circular construction order between Exercise and
                sharing services. Required before any ASSIGNED exercise is
                created.
        """
        super().__init__(backend, "exercises")
        self.backend = backend
        self.sharing_service = sharing_service
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger
        logger.info("ExerciseService initialized")

    # ========================================================================
    # CREATE
    # ========================================================================

    @with_error_handling("create_exercise", error_type="database")
    async def create_exercise(
        self,
        user_uid: UserUID,
        name: str,
        instructions: str,
        model: str = "claude-sonnet-4-6",
        context_notes: list[str] | None = None,
        domain: Domain | None = None,
        scope: ExerciseScope = ExerciseScope.PERSONAL,
        due_date: date | None = None,
        processor_type: ReportSource = ReportSource.LLM,
        group_uid: str | None = None,
        form_schema: list[dict[str, Any]] | None = None,
        scoring_rubric: list[dict[str, Any]] | None = None,
        pass_threshold: float | None = None,
    ) -> Result[Exercise]:
        """
        Create a new Exercise.

        For ASSIGNED scope (teacher exercises):
        - group_uid is required
        - Creates a SHARED_WITH_GROUP relationship to the target group

        For ASSESSMENT scope (formal tests):
        - scoring_rubric is required
        - pass_threshold defaults to 0.7 if not specified

        Args:
            user_uid: User who owns this exercise
            name: Display name
            instructions: Plain text instructions for LLM
            model: LLM model to use
            context_notes: Optional reference materials
            domain: Optional domain categorization
            scope: PERSONAL (default), ASSIGNED (teacher exercise), or ASSESSMENT (formal test)
            due_date: Due date for ASSIGNED/ASSESSMENT scope
            processor_type: LLM, HUMAN, or HYBRID
            group_uid: Target group UID for ASSIGNED scope
            form_schema: Optional inline form definition
            scoring_rubric: Assessment criteria with weights (required for ASSESSMENT)
            pass_threshold: Minimum score to pass (0.0-1.0, default 0.7 for ASSESSMENT)

        Returns:
            Result[Exercise] - The created exercise
        """
        if scope == ExerciseScope.ASSIGNED and not group_uid:
            return Result.fail(
                Errors.validation("group_uid is required for assigned exercises", field="group_uid")
            )
        if scope == ExerciseScope.ASSESSMENT and not scoring_rubric:
            return Result.fail(
                Errors.validation(
                    "scoring_rubric is required for assessment exercises",
                    field="scoring_rubric",
                )
            )

        uid = UIDGenerator.generate_uid("ex", name)

        # Default pass_threshold to 0.7 for assessments
        if scope == ExerciseScope.ASSESSMENT and pass_threshold is None:
            pass_threshold = 0.7

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
            scoring_rubric=tuple(scoring_rubric) if scoring_rubric else None,
            pass_threshold=pass_threshold,
        )

        result = await self.backend.create(exercise)

        if result.is_error:
            self.logger.error(f"Failed to create exercise: {result.error}")
            return result

        # Create OWNS relationship (user → exercise)
        owns_result = await self.backend.create_owns_relationship(user_uid, uid)
        if owns_result.is_error:
            self.logger.warning(f"Failed to create OWNS relationship: {owns_result.error}")

        # Share assigned exercises with the target group via the unified
        # SHARED_WITH_GROUP mechanism (ADR-053). FOR_GROUP has been retired.
        if scope == ExerciseScope.ASSIGNED and group_uid:
            if self.sharing_service is None:
                self.logger.error(
                    "ExerciseService.sharing_service not wired; ASSIGNED exercise "
                    f"{uid} was not shared with group {group_uid}"
                )
            else:
                share_result = await self.sharing_service.share_with_group(
                    entity_uid=uid,
                    owner_uid=user_uid,
                    group_uid=group_uid,
                    share_version="original",
                )
                if share_result.is_error:
                    self.logger.warning(
                        f"Failed to share exercise {uid} with group {group_uid}: "
                        f"{share_result.expect_error()}"
                    )
                else:
                    self.logger.info(f"SHARED_WITH_GROUP created: {uid} -> {group_uid}")

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

    async def list_all(self, limit: int = 500) -> Result[list[Exercise]]:
        """List all Exercise entities (admin/shared curriculum view)."""
        return await self.backend.list(limit=limit, sort_by="title")

    @with_error_handling("list_user_exercises", error_type="database")
    async def list_user_exercises(
        self, user_uid: UserUID, active_only: bool = True
    ) -> Result[list[Exercise]]:
        """List personal exercises owned by a user via OWNS relationship."""
        result = await self.backend.get_user_exercises(user_uid)

        if result.is_error:
            return Result.fail(result)

        exercises = []
        for record in result.value or []:
            props = record["e"]
            try:
                exercise = Exercise(**props)
                exercises.append(exercise)
            except DATA_CONVERSION_EXCEPTIONS as exc:
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
            updates["metadata"] = metadata
        if form_schema is not _UNSET:
            updates["form_schema"] = form_schema if form_schema else None

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
    async def get_student_exercises(self, user_uid: UserUID) -> Result[list[Exercise]]:
        """
        Get all exercises for a student (via MEMBER_OF -> Group <- SHARED_WITH_GROUP -> Exercise).

        Args:
            user_uid: Student UID

        Returns:
            Result containing list of assigned exercises
        """
        result = await self.backend.get_student_exercises(user_uid)

        if result.is_error:
            return Result.fail(result)

        exercises = []
        for record in result.value or []:
            props = record["exercise"]
            try:
                exercise = Exercise(**props)
                exercises.append(exercise)
            except DATA_CONVERSION_EXCEPTIONS as e:
                self.logger.warning(f"Failed to deserialize exercise: {e}")

        self.logger.info(f"Found {len(exercises)} exercises for student {user_uid}")
        return Result.ok(exercises)

    @with_error_handling("get_student_exercises_with_status", error_type="database")
    async def get_student_exercises_with_status(
        self, user_uid: UserUID
    ) -> Result[list[ExerciseStatusRow]]:
        """Get exercises with submission + report status for the library exercises tab.

        Combines two sources:
        - Assigned exercises (scope=assigned, via SHARED_WITH_GROUP → group membership)
        - PathStep-linked exercises (scope=personal, via RELATED_TO from enrolled PathSteps)

        Returns exercise properties enriched with has_submission, submission_uid,
        submission_status, has_report, report_uid, report_outcome, and group_name.
        """
        assigned_result = await self.backend.get_student_exercises_with_status(user_uid)
        if assigned_result.is_error:
            return Result.fail(assigned_result)

        ps_result = await self.backend.get_enrolled_ps_exercises_with_status(user_uid)
        if ps_result.is_error:
            return Result.fail(ps_result)

        seen_uids: set[str] = set()
        exercises: list[ExerciseStatusRow] = []

        for record in (assigned_result.value or []) + (ps_result.value or []):
            props = dict(record["exercise"])
            uid = props.get("uid", "")
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            row: ExerciseStatusRow = {
                "uid": uid,
                "title": props.get("title", ""),
                "description": props.get("description"),
                "due_date": props.get("due_date"),
                "group_name": record.get("group_name") or "",
                "has_submission": bool(record.get("has_submission", False)),
                "submission_uid": record.get("submission_uid"),
                "submission_status": record.get("submission_status"),
                "has_report": bool(record.get("has_report", False)),
                "report_uid": record.get("report_uid"),
                "report_outcome": record.get("report_outcome"),
            }
            exercises.append(row)

        self.logger.info(f"Found {len(exercises)} exercises with status for student {user_uid}")
        return Result.ok(exercises)

    @with_error_handling("get_exercises_for_path_step_with_status", error_type="database")
    async def get_exercises_for_path_step_with_status(
        self, ps_uid: str, user_uid: UserUID
    ) -> Result[list[ExerciseStatusRow]]:
        """Get exercises linked to a specific PathStep with submission/feedback status.

        Used by the PathStep detail page to render exercises with status pills
        and contextual action links (Submit / View Submission / View Report).
        """
        result = await self.backend.get_ps_exercises_with_status(ps_uid, user_uid)
        if result.is_error:
            return Result.fail(result)

        exercises: list[ExerciseStatusRow] = []
        for record in result.value or []:
            props = dict(record["exercise"])
            uid = props.get("uid", "")
            row: ExerciseStatusRow = {
                "uid": uid,
                "title": props.get("title", ""),
                "description": props.get("description"),
                "due_date": props.get("due_date"),
                "group_name": record.get("group_name") or "",
                "has_submission": bool(record.get("has_submission", False)),
                "submission_uid": record.get("submission_uid"),
                "submission_status": record.get("submission_status"),
                "has_report": bool(record.get("has_report", False)),
                "report_uid": record.get("report_uid"),
                "report_outcome": record.get("report_outcome"),
            }
            exercises.append(row)

        self.logger.info(f"Found {len(exercises)} exercises with status for PS {ps_uid}")
        return Result.ok(exercises)

    # ========================================================================
    # FILE-BASED EXERCISE LOADING
    # ========================================================================

    async def seed_default_exercise(
        self,
        instructions_path: str | None = None,
        exercise_uid: str = "jp.transcript_default",
        model: str = "gpt-4o",
    ) -> Result[Exercise]:
        """Load/update default transcript exercise from instructions file.

        Called at startup to ensure default exercises exist.
        Encapsulates file resolution, system user ownership, and idempotent create/update.
        """
        from pathlib import Path

        path = instructions_path or os.getenv(
            "SKUEL_TRANSCRIPT_INSTRUCTIONS_PATH",
            str(Path(__file__).parents[3] / "data" / "instructions - transcripts 0.md"),
        )

        return await self.load_exercise_from_file(
            file_path=path,
            user_uid=UserUID("user_system"),
            exercise_uid=exercise_uid,
            model=model,
        )

    async def load_exercise_from_file(
        self,
        file_path: str,
        user_uid: UserUID,
        exercise_uid: str | None = None,
        model: str = "gpt-4o",
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

            if exercise_uid:
                existing = await self.backend.get(exercise_uid)
                if existing.is_ok and existing.value:
                    result = await self.update_exercise(
                        uid=exercise_uid, instructions=instructions, model=model
                    )
                    self.logger.info(f"Exercise updated from file: {exercise_uid} - {file_path}")
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

        except FILE_IO_EXCEPTIONS as e:
            self.logger.error(f"Error loading exercise from file {file_path}: {e}")
            return Result.fail(
                Errors.system(
                    f"Failed to load exercise from file: {e!s}",
                    operation="load_exercise_from_file",
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Error loading exercise from file {file_path}: {e}")
            return Result.fail(
                Errors.system(
                    f"Failed to load exercise from file: {e!s}",
                    operation="load_exercise_from_file",
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
        curriculum knowledge unit — anchoring the exercise to the
        four-phase loop: Exercise → UserEntry → ExerciseReport → RevisedExercise.

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
    async def get_required_knowledge(
        self, exercise_uid: str
    ) -> Result[list[RequiredKnowledgeResult]]:
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

    @with_error_handling("get_exercises_for_path_steps", error_type="database")
    async def get_exercises_for_path_steps(
        self, ps_uids: list[str]
    ) -> Result[list[dict[str, Any]]]:
        """Get exercises associated with the given PathStep UIDs.

        Traverses PathStep -[:USES_KU|CONTAINS_KNOWLEDGE]-> Ku <-[:REQUIRES_KNOWLEDGE]- Exercise.

        Args:
            ps_uids: List of PathStep UIDs to look up exercises for

        Returns:
            Result containing list of exercise dicts (uid, title, scope, description, status)
        """
        result = await self.backend.get_exercises_for_path_steps(ps_uids)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    @with_error_handling("get_exercises_for_curriculum", error_type="database")
    async def get_exercises_for_curriculum(
        self, curriculum_uid: str
    ) -> Result[list[CurriculumExerciseResult]]:
        """
        Get all exercises that require a specific curriculum KU.

        Enables the reverse lookup: "what exercises practice this knowledge?"

        Args:
            curriculum_uid: Curriculum KU UID

        Returns:
            Result containing list of exercise summaries
        """
        result = await self.backend.get_exercises_for_curriculum(curriculum_uid)

        if result.is_error:
            return Result.fail(result)

        exercises: list[CurriculumExerciseResult] = [
            dict(record)  # type: ignore[misc]
            for record in (result.value or [])
        ]
        self.logger.info(f"Found {len(exercises)} exercises for curriculum {curriculum_uid}")
        return Result.ok(exercises)

    # ========================================================================
    # DAILY PLANNING QUERIES (service-routed replacement for the inline blocks
    # that DailyPlanningMixin formerly built from context.unsubmitted_exercises
    # and context.pending_revised_exercises). These join prerequisite mastery
    # so callers see "blocked by N unmastered KUs" without re-querying.
    # ========================================================================

    @with_error_handling("get_actionable_exercises_for_user", error_type="database")
    async def get_actionable_exercises_for_user(
        self,
        context: RichUserContext,
        limit: int = 3,
    ) -> Result[list[ContextualExercise]]:
        """Unsubmitted exercises enriched with REQUIRES_KNOWLEDGE prerequisite
        readiness. Sorted: most-ready first, then overdue, then earliest due."""
        from datetime import date as _date

        from core.models.context_types import ContextualExercise

        if not context.unsubmitted_exercises:
            return Result.ok([])

        today = _date.today()
        enriched: list[ContextualExercise] = []

        for ex_dict in context.unsubmitted_exercises:
            uid = ex_dict.get("uid")
            if not uid:
                continue

            due_date: date | None = None
            days_until_due: int | None = None
            is_overdue = False
            raw_due = ex_dict.get("due_date")
            if raw_due:
                try:
                    due_date = _date.fromisoformat(raw_due)
                    delta = (due_date - today).days
                    days_until_due = delta
                    is_overdue = delta < 0
                except ValueError:
                    self.logger.warning(f"Invalid due_date on exercise {uid}: {raw_due!r}")

            blocking_kus, readiness_score = await self._compute_prereq_readiness(uid, context)

            enriched.append(
                ContextualExercise(
                    uid=uid,
                    title=ex_dict.get("title", "Untitled Exercise"),
                    due_date=due_date,
                    is_overdue=is_overdue,
                    days_until_due=days_until_due,
                    subtype="assignment",
                    blocking_kus=blocking_kus,
                    readiness_score=readiness_score,
                    est_time_minutes=ExerciseTimeEstimate.FRESH_SUBMISSION_MINUTES,
                )
            )

        def _sort_key(ex: ContextualExercise) -> tuple[float, int, int]:
            days = ex.days_until_due if ex.days_until_due is not None else 10_000
            return (-ex.readiness_score, -int(ex.is_overdue), days)

        enriched.sort(key=_sort_key)
        return Result.ok(enriched[:limit])

    @with_error_handling("get_pending_revisions_for_user", error_type="database")
    async def get_pending_revisions_for_user(
        self,
        context: RichUserContext,
        limit: int = 3,
    ) -> Result[list[ContextualExercise]]:
        """Pending revised exercises enriched with prereq readiness. Lives on
        ExerciseService (not RevisedExerciseService) because the prereq chain
        REVISES_EXERCISE → Exercise → REQUIRES_KNOWLEDGE → Ku is anchored to
        the original Exercise, whose UID is already on each revision dict."""
        from core.models.context_types import ContextualExercise

        if not context.pending_revised_exercises:
            return Result.ok([])

        enriched: list[ContextualExercise] = []

        for rev_dict in context.pending_revised_exercises:
            rev_uid = rev_dict.get("uid")
            if not rev_uid:
                continue

            original_uid = rev_dict.get("original_exercise_uid")
            if original_uid:
                blocking_kus, readiness_score = await self._compute_prereq_readiness(
                    original_uid, context
                )
            else:
                blocking_kus = ()
                readiness_score = 1.0

            enriched.append(
                ContextualExercise(
                    uid=rev_uid,
                    title=rev_dict.get("title", "Revision"),
                    due_date=None,
                    is_overdue=False,
                    days_until_due=None,
                    subtype="revision",
                    blocking_kus=blocking_kus,
                    readiness_score=readiness_score,
                    est_time_minutes=ExerciseTimeEstimate.REVISION_MINUTES,
                )
            )

        def _revision_sort_key(ex: ContextualExercise) -> float:
            return -ex.readiness_score

        enriched.sort(key=_revision_sort_key)
        return Result.ok(enriched[:limit])

    async def _compute_prereq_readiness(
        self,
        exercise_uid: str,
        context: RichUserContext,
    ) -> tuple[tuple[str, ...], float]:
        """Join exercise REQUIRES_KNOWLEDGE prerequisites with
        context.knowledge_mastery (threshold 0.7). Lookup failures degrade to
        (empty, 1.0) so a single prereq query error never collapses the batch."""
        result = await self.get_required_knowledge(exercise_uid)
        if result.is_error:
            self.logger.warning(
                f"get_required_knowledge failed for exercise {exercise_uid}: "
                f"{result.expect_error()}"
            )
            return ((), 1.0)
        prereqs = result.value or []
        if not prereqs:
            return ((), 1.0)
        unmastered = tuple(
            ku["uid"] for ku in prereqs if context.knowledge_mastery.get(ku["uid"], 0.0) < 0.7
        )
        score = (len(prereqs) - len(unmastered)) / len(prereqs)
        return (unmastered, score)

    # ========================================================================
    # QUERY LAYER (FilteredContextProvider)
    # ========================================================================

    async def get_filtered_context(
        self,
        user_uid: UserUID,
        status_filter: str = "all",
        sort_by: str = "title",
    ) -> Result[ListContext]:
        """Get filtered and sorted exercises with pre-filter stats."""

        async def fetch_all() -> Result[list[Any]]:
            return await self.list_user_exercises(user_uid, active_only=False)

        def apply_filters(all_exercises: list[Any]) -> list[Any]:
            if status_filter == ExerciseScope.PERSONAL:
                return [
                    e for e in all_exercises if getattr(e, "scope", None) == ExerciseScope.PERSONAL
                ]
            elif status_filter == ExerciseScope.ASSIGNED:
                return [
                    e for e in all_exercises if getattr(e, "scope", None) == ExerciseScope.ASSIGNED
                ]
            elif status_filter == ExerciseScope.ASSESSMENT:
                return [
                    e
                    for e in all_exercises
                    if getattr(e, "scope", None) == ExerciseScope.ASSESSMENT
                ]
            return all_exercises

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_exercise_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_exercise_sort,
            sort_by=sort_by,
        )
