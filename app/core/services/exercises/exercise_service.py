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

from typing import TYPE_CHECKING, Any, ClassVar, cast

from core.constants import ExerciseTimeEstimate
from core.models.enums import Domain, SearchVisibility
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.user_entry_enums import ExerciseScope
from core.models.exercises.exercise import Exercise
from core.models.exercises.exercise_dto import ExerciseDTO
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.ports.curriculum_protocols import ExerciseBackendOperations
from core.ports.query_types import (
    CurriculumExerciseResult,
    ExerciseStatusRow,
    RequiredKnowledgeResult,
)
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.filtered_context import build_filtered_context
from core.utils.decorators import with_error_handling
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.list_helpers import SortConfig, apply_entity_sort
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_created_at_attr, get_title_lower
from core.utils.uid_generator import UIDGenerator

logger = get_logger(__name__)

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping
    from datetime import date

    from core.models.context_types import ContextualExercise
    from core.models.update_contracts import RawChanges
    from core.ports.query_types import ListContext
    from core.services.user.unified_user_context import RichUserContext


# boundary: neo4j-record — a raw driver row, genuinely heterogeneous: an
# ``exercise`` Node under one key plus flat scalar status columns under the
# rest. No narrower type describes both halves, and coercing here would change
# what the three callers have always emitted.
def _to_status_row(record: Mapping[str, Any]) -> ExerciseStatusRow:
    """Flatten one backend status record into an ``ExerciseStatusRow``.

    The three ``*_with_status`` backend queries all return the same shape — an
    ``exercise`` node plus flat status columns — so one reader serves them all.
    Backend: ExerciseBackend's shared ``_exercise_status_tail``.
    """
    props = dict(record["exercise"])
    return {
        "uid": props.get("uid", ""),
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
        "has_in_progress": bool(record.get("has_in_progress", False)),
        "in_progress_uid": record.get("in_progress_uid"),
    }


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


class ExerciseService(BaseService[ExerciseBackendOperations, Exercise]):
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
        # Exercises are instance-scoped, not type-scoped: CURRICULUM has no
        # owner and is visible to everyone; PERSONAL/ASSIGNED/ASSESSMENT are
        # visible via OWNS / SHARES_WITH / group membership (ADR-038/040).
        # Without this, OWNS-derived scoping hides all curriculum exercises.
        search_visibility=SearchVisibility.SCOPE_AWARE,
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

    def __init__(
        self,
        backend: ExerciseBackendOperations,
        sharing_service: Any = None,
        event_bus: Any = None,
    ) -> None:
        """
        Initialize with backend.

        Args:
            backend: Exercise backend port - REQUIRED (ExerciseBackend satisfies it)
            sharing_service: UnifiedSharingService — wired after bootstrap
                to avoid a circular construction order between Exercise and
                sharing services. Required before any ASSIGNED exercise is
                created.
            event_bus: Event bus for ExerciseEmbeddingRequested publishes on
                create/update (ADR-074 post-persist embedding step).
        """
        super().__init__(backend, "exercises")
        self.backend = backend
        self.sharing_service = sharing_service
        self.event_bus = event_bus
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger
        logger.info("ExerciseService initialized")

    # ========================================================================
    # CREATE
    # ========================================================================

    async def create(self, entity: Exercise) -> Result[Exercise]:
        """
        Create an Exercise with all required side effects.

        Scope-specific relationship writes:
        - All scopes: (User)-[:OWNS]->(Exercise) via entity.owner_uid
        - PERSONAL + path_step_uid set: (PathStep)-[:HAS_EXERCISE]->(Exercise) dual-write.
          The anchor is optional, but when path_step_uid is set the edge write must
          succeed — a set field without its mirror edge is silent inconsistency.
        - ASSIGNED + group_uid set: (Exercise)-[:SHARED_WITH_GROUP]->(Group) sharing

        Scope-field validation lives at the API boundary (ExerciseCreateRequest
        model_validator), not here.

        Called by the CRUD route factory (via ConversionServiceV2 registry) and by
        create_exercise() (the convenience builder that also generates UIDs).
        """
        uid = entity.uid

        result = await self.backend.create(entity)
        if result.is_error:
            self.logger.error(f"Failed to create exercise: {result.error}")
            return result

        # Create OWNS relationship (owner → exercise). Return failure when the
        # edge write fails: the node is already persisted, so a warning here
        # left an owner holding a create that reported success while the edge
        # was missing — the property-only shape ADR-086 grades as door 4's soft
        # spot, invisible to every :OWNS-traversing read. Reporting the failure
        # is what lets the caller retry or surface it (ADR-086 hardening).
        if entity.owner_uid:
            owns_result = await self.backend.create_owns_relationship(
                UserUID(entity.owner_uid), uid
            )
            if owns_result.is_error:
                self.logger.error(
                    f"OWNS edge failed for {uid} -> owner {entity.owner_uid}: "
                    f"{owns_result.expect_error()} (node was persisted)"
                )
                return Result.fail(owns_result)

        # Dual-write: HAS_EXERCISE edge mirrors Exercise.path_step_uid for PERSONAL scope.
        # Return failure when edge creation fails — a PERSONAL exercise without the edge
        # is invisible from PathStep views and broken for its intended purpose.
        if entity.scope == ExerciseScope.PERSONAL and entity.path_step_uid:
            ps_result = await self.backend.link_to_path_step(uid, entity.path_step_uid)
            if ps_result.is_error:
                self.logger.error(
                    f"HAS_EXERCISE edge failed for {uid} -> {entity.path_step_uid}: "
                    f"{ps_result.expect_error()} (node was persisted)"
                )
                return Result.fail(ps_result)

        # Share assigned exercises with the target group via the unified
        # SHARED_WITH_GROUP mechanism (ADR-053). FOR_GROUP has been retired.
        if entity.scope == ExerciseScope.ASSIGNED and entity.group_uid:
            if self.sharing_service is None:
                self.logger.error(
                    "ExerciseService.sharing_service not wired; ASSIGNED exercise "
                    f"{uid} was not shared with group {entity.group_uid}"
                )
            else:
                share_result = await self.sharing_service.share_with_group(
                    entity_uid=uid,
                    owner_uid=entity.owner_uid or "",
                    group_uid=entity.group_uid,
                    share_version="original",
                )
                if share_result.is_error:
                    self.logger.warning(
                        f"Failed to share exercise {uid} with group {entity.group_uid}: "
                        f"{share_result.expect_error()}"
                    )
                else:
                    self.logger.info(f"SHARED_WITH_GROUP created: {uid} -> {entity.group_uid}")

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        from core.events.embedding_publisher import publish_embedding_requested

        await publish_embedding_requested(self.event_bus, EntityType.EXERCISE, entity, self.logger)

        self.logger.info(f"Exercise created: {uid} - {entity.title} (scope={entity.scope.value})")
        return Result.ok(entity)

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
        group_uid: str | None = None,
        form_schema: list[dict[str, Any]] | None = None,
        scoring_rubric: list[dict[str, Any]] | None = None,
        pass_threshold: float | None = None,
        path_step_uid: str | None = None,
    ) -> Result[Exercise]:
        """
        Convenience builder: constructs an Exercise from named fields and delegates
        to create() for persistence and side effects.

        For PERSONAL scope: path_step_uid optional (when set, HAS_EXERCISE is dual-written).
        For ASSIGNED scope: group_uid required.
        For ASSESSMENT scope: scoring_rubric required.
        """
        # Default pass_threshold to 0.7 for assessments
        if scope == ExerciseScope.ASSESSMENT and pass_threshold is None:
            pass_threshold = 0.7

        uid = UIDGenerator.generate_uid("ex", name)

        exercise = Exercise(
            uid=uid,
            entity_type=EntityType.EXERCISE,
            title=name,
            instructions=instructions,
            model=model,
            context_notes=tuple(context_notes) if context_notes else (),
            domain=domain if domain is not None else Domain.KNOWLEDGE,
            scope=scope,
            due_date=due_date,
            group_uid=group_uid,
            enrichment_mode=None,
            form_schema=tuple(form_schema) if form_schema else None,
            scoring_rubric=tuple(scoring_rubric) if scoring_rubric else None,
            pass_threshold=pass_threshold,
            path_step_uid=path_step_uid,
            owner_uid=user_uid,
        )

        return await self.create(exercise)

    # ========================================================================
    # READ
    # ========================================================================

    @with_error_handling("get_exercise", error_type="database")
    async def get_exercise(self, uid: str) -> Result[Exercise]:
        """Get a specific Exercise by UID, unscoped.

        Reads every scope, including another user's PERSONAL exercise, so it is
        only for callers that have already established the audience by other
        means — service composition resolving the exercise a submission
        fulfils, after that submission has itself been checked.

        A role gate is not such a check: it decides who may act, never on whose
        content (ADR-042 §3). Any surface serving a user-supplied UID wants
        get_exercise_for_user(), or verify_ownership() when the surface belongs
        to the exercise's author.
        """
        result = await self.backend.get(uid)
        if result.is_error:
            # Result.fail, not `return result`: the backend hands back
            # Result[Exercise | None] and this method promises Result[Exercise].
            # `self.backend` is Any, so MyPy cannot catch the mismatch (SKUEL028).
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found(resource="Exercise", identifier=uid))
        return Result.ok(result.value)

    @with_error_handling("get_exercise_for_user", error_type="database")
    async def get_exercise_for_user(self, uid: str, user_uid: UserUID) -> Result[Exercise]:
        """Get an Exercise by UID only if this user is in its audience.

        Applies the SCOPE_AWARE policy this service already declares for
        search (see ``_config.search_visibility``) to a single-entity read:
        CURRICULUM is everyone's; PERSONAL/ASSIGNED/ASSESSMENT need OWNS,
        SHARES_WITH, or group membership. Without this, a direct read by UID
        answered questions the same entity's search surface refuses.

        Out-of-audience is reported as not-found, never forbidden, so the
        response cannot confirm that a UID exists (OWNERSHIP_VERIFICATION.md).

        Backend: UniversalNeo4jBackend.get_visible_to_user
        """
        result = await self.backend.get_visible_to_user(
            uid, user_uid, self._config.search_visibility
        )
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found(resource="Exercise", identifier=uid))
        return Result.ok(result.value)

    async def list_all(self, limit: int = 500) -> Result[list[Exercise]]:
        """List all Exercise entities (admin/shared curriculum view)."""
        # backend.list() returns a (page, total_count) tuple; this facade
        # promises just the page, so unwrap it.
        result = await self.backend.list(limit=limit, sort_by="title")
        if result.is_error:
            return Result.fail(result)
        exercises, _total = result.value
        return Result.ok(exercises)

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
            # boundary: neo4j-projection — `RETURN e` is a node map whose values
            # (enums, tuples, datetimes) exceed Neo4jValue's scalar union
            props = cast("dict[str, Any]", record["e"])
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

    async def _publish_update_embedding(
        self, exercise: Exercise, changed_fields: Collection[str]
    ) -> None:
        """Post-persist embedding refresh (ADR-074) shared by both update paths."""
        from core.events.embedding_publisher import publish_embedding_requested

        await publish_embedding_requested(
            self.event_bus,
            EntityType.EXERCISE,
            exercise,
            self.logger,
            changed_fields=changed_fields,
        )

    async def update(self, uid: str, updates: RawChanges) -> Result[Exercise]:
        """Update an Exercise, then publish the post-persist embedding refresh (ADR-074).

        Overrides the generic CRUD update to add the embedding event — text-field
        changes (title/instructions) must re-embed via the background worker.
        """
        changes = updates.to_changes()
        result = await super().update(uid, updates)
        if result.is_error or result.value is None:
            return result

        await self._publish_update_embedding(result.value, changes.keys())
        self.logger.info(f"Exercise updated: {uid}")
        return result

    async def update_for_user(
        self, uid: str, updates: RawChanges, user_uid: UserUID
    ) -> Result[Exercise]:
        """Ownership-verified update + embedding refresh (ADR-074).

        This is the path the CRUD route factory takes for exercises
        (ContentScope.USER_OWNED ⇒ verify_ownership=True) — the base mixin
        writes straight to the backend without going through update(), so the
        embedding publish must be mirrored here.
        """
        changes = updates.to_changes()
        result = await super().update_for_user(uid, updates, user_uid)
        if result.is_error or result.value is None:
            return result

        await self._publish_update_embedding(result.value, changes.keys())
        self.logger.info(f"Exercise updated: {uid} (owner {user_uid})")
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
        Get all exercises available to a student, from both sources:

        - Assigned (MEMBER_OF -> Group <- SHARED_WITH_GROUP -> Exercise)
        - Enrolled-PS curriculum (IN_PROGRESS -> PathStep -[:HAS_EXERCISE]-> Exercise)

        The union is what "my exercises" means for every consumer (submit-form
        dropdown, profile) — a solo learner with no group still sees the
        exercises of the PathSteps they enrolled in (systems review, 2026-07-03).

        Backend: ExerciseBackend.get_student_exercises +
        ExerciseBackend.get_enrolled_ps_exercises_with_status.
        """
        assigned_result = await self.backend.get_student_exercises(user_uid)
        if assigned_result.is_error:
            return Result.fail(assigned_result)

        enrolled_result = await self.backend.get_enrolled_ps_exercises_with_status(user_uid)
        if enrolled_result.is_error:
            return Result.fail(enrolled_result)

        exercises: list[Exercise] = []
        seen_uids: set[str] = set()
        for record in (assigned_result.value or []) + (enrolled_result.value or []):
            # boundary: neo4j-projection — `RETURN exercise` is a node map whose
            # values (enums, tuples, datetimes) exceed Neo4jValue's scalar union
            props = dict(cast("dict[str, Any]", record["exercise"]))
            if props.get("uid") in seen_uids:
                continue
            try:
                exercise = Exercise(**props)
            except DATA_CONVERSION_EXCEPTIONS as e:
                self.logger.warning(f"Failed to deserialize exercise: {e}")
                continue
            seen_uids.add(exercise.uid)
            exercises.append(exercise)

        self.logger.info(f"Found {len(exercises)} exercises for student {user_uid}")
        return Result.ok(exercises)

    @with_error_handling("get_student_exercises_with_status", error_type="database")
    async def get_student_exercises_with_status(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[ExerciseStatusRow]]:
        """Get exercises with submission + report status for the library exercises tab.

        Combines two sources:
        - Assigned exercises (scope=assigned, via SHARED_WITH_GROUP → group membership)
        - PathStep-linked exercises (scope=personal, via HAS_EXERCISE from enrolled PathSteps)

        Returns exercise properties enriched with has_submission, submission_uid,
        submission_status, has_report, report_uid, report_outcome, group_name,
        and the vault living channel's has_in_progress / in_progress_uid
        (declared-intent entry, no turn-in edge — "exercise in progress").

        ``limit`` is pushed down to both backend queries and re-applied after the
        assigned-first merge/dedupe, which keeps the result identical to a full
        fetch sliced to ``limit`` (assigned rows have no internal duplicates, so
        the first ``limit`` merged rows never depend on rows beyond each query's
        own top ``limit``). ``None`` returns all exercises.
        """
        assigned_result = await self.backend.get_student_exercises_with_status(
            user_uid, limit=limit
        )
        if assigned_result.is_error:
            return Result.fail(assigned_result)

        ps_result = await self.backend.get_enrolled_ps_exercises_with_status(user_uid, limit=limit)
        if ps_result.is_error:
            return Result.fail(ps_result)

        seen_uids: set[str] = set()
        exercises: list[ExerciseStatusRow] = []

        for record in (assigned_result.value or []) + (ps_result.value or []):
            row = _to_status_row(record)
            if row["uid"] in seen_uids:
                continue
            seen_uids.add(row["uid"])
            exercises.append(row)

        if limit is not None:
            exercises = exercises[:limit]

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
            exercises.append(_to_status_row(record))

        self.logger.info(f"Found {len(exercises)} exercises with status for PS {ps_uid}")
        return Result.ok(exercises)

    # ========================================================================
    # DELETE
    # ========================================================================

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
        four-phase loop: Exercise → UserEntry → EntryReport → RevisedExercise.

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

        Traverses PathStep -[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]-> Ku <-[:REQUIRES_KNOWLEDGE]- Exercise.

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
            try:
                scope = ExerciseScope(status_filter)
            except ValueError:
                return all_exercises
            return [e for e in all_exercises if getattr(e, "scope", None) == scope]

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_exercise_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_exercise_sort,
            sort_by=sort_by,
        )
