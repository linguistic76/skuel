"""
Exercise Service
=================

Reads Exercises — the instruction templates of the core educational loop.

An Exercise is curriculum: authored only in the content vault, owned by no user,
and naming in its file the teacher who reviews work on it (ADR-091 S2-S4). Its
instructions are always shown to the learner (no black box). This service reads
exercises for learners and teachers and joins them to the learner's submissions;
it writes none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from core.constants import ExerciseTimeEstimate
from core.models.enums.neo_labels import NeoLabel
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
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

logger = get_logger(__name__)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from core.models.context_types import ContextualExercise
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
        "has_submission": bool(record.get("has_submission", False)),
        "submission_uid": record.get("submission_uid"),
        "submission_status": record.get("submission_status"),
        "has_report": bool(record.get("has_report", False)),
        "report_uid": record.get("report_uid"),
        "report_outcome": record.get("report_outcome"),
        "has_in_progress": bool(record.get("has_in_progress", False)),
        "in_progress_uid": record.get("in_progress_uid"),
    }


class ExerciseService(BaseService[ExerciseBackendOperations, Exercise]):
    """
    Read service for Exercises (instruction templates).

    Exercises are stored as :Entity:Exercise nodes with entity_type=EntityType.EXERCISE,
    written only by the content-vault sync (ADR-091 S4).
    """

    _config = DomainConfig(
        dto_class=ExerciseDTO,
        model_class=Exercise,
        entity_label="Entity",
        search_fields=("title", "instructions"),
        search_order_by="created_at",
        # Curriculum: no user owns an exercise (ADR-091 S2), so its visibility
        # derives to PUBLIC — every exercise is shared content, and a draft is
        # unlisted by the publication gate.
        user_ownership_relationship=None,
    )

    # Graph enrichment for graph_aware_faceted_search (SearchRouter integration)
    _graph_enrichment_patterns: ClassVar[
        tuple[tuple[str, str, str] | tuple[str, str, str, str], ...]
    ] = (
        (RelationshipName.REQUIRES_KNOWLEDGE.value, NeoLabel.ENTITY.value, "required_knowledge"),
        (
            RelationshipName.FULFILLS_EXERCISE.value,
            NeoLabel.ENTITY.value,
            "submissions",
            "incoming",
        ),
    )

    def __init__(self, backend: ExerciseBackendOperations) -> None:
        """
        Initialize with backend.

        Args:
            backend: Exercise backend port - REQUIRED (ExerciseBackend satisfies it)
        """
        super().__init__(backend, "exercises")
        self.backend = backend
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger
        logger.info("ExerciseService initialized")

    # ========================================================================
    # READ
    # ========================================================================

    @with_error_handling("get_exercise", error_type="database")
    async def get_exercise(self, uid: str) -> Result[Exercise]:
        """Get a specific Exercise by UID, unscoped.

        For service composition resolving the exercise a submission fulfils,
        after that submission has itself been checked. Any surface serving a
        user-supplied UID wants get_exercise_for_user(), which applies the
        domain's declared audience.
        """
        result = await self.backend.get(uid)
        if result.is_error:
            # Result.fail, not `return result`: the backend hands back
            # Result[Exercise | None] and this method promises Result[Exercise].
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found(resource="Exercise", identifier=uid))
        return Result.ok(result.value)

    @with_error_handling("get_exercise_for_user", error_type="database")
    async def get_exercise_for_user(self, uid: str, user_uid: UserUID) -> Result[Exercise]:
        """Get an Exercise by UID through the domain's declared read audience.

        Every exercise is curriculum, so the declaration is PUBLIC and a by-UID
        read admits any signed-in user, as a PathStep's does; the publication
        gate belongs to discovery (search and listings), not to a named read.
        Reading through the declaration keeps a direct read and a search of the
        domain in agreement by construction. A uid that names no exercise is
        not-found.

        Backend: UniversalNeo4jBackend.get_visible_to_user
        """
        result = await self.backend.get_visible_to_user(
            uid, user_uid, self._config.get_read_visibility()
        )
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found(resource="Exercise", identifier=uid))
        return Result.ok(result.value)

    # ========================================================================
    # LEARNER QUERIES
    # ========================================================================

    @with_error_handling("get_student_exercises_with_status", error_type="database")
    async def get_student_exercises_with_status(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[ExerciseStatusRow]]:
        """Get exercises with submission + report status for the library exercises tab.

        The exercises hanging from the PathSteps the learner is in progress on
        (``IN_PROGRESS`` → ``HAS_EXERCISE``), each enriched with has_submission,
        submission_uid, submission_status, has_report, report_uid, report_outcome,
        and the vault living channel's has_in_progress / in_progress_uid
        (declared-intent entry, no turn-in edge — "exercise in progress").
        ``None`` for ``limit`` returns all of them.

        Backend: ExerciseBackend.get_enrolled_ps_exercises_with_status
        """
        result = await self.backend.get_enrolled_ps_exercises_with_status(user_uid, limit=limit)
        if result.is_error:
            return Result.fail(result)
        exercises = [_to_status_row(record) for record in result.value or []]
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
    # CURRICULUM LINKS
    # ========================================================================

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

    @with_error_handling("get_required_knowledge_for_user", error_type="database")
    async def get_required_knowledge_for_user(
        self, exercise_uid: str, user_uid: UserUID
    ) -> Result[list[RequiredKnowledgeResult]]:
        """The Kus an exercise requires, read by a caller in the exercise's audience.

        The audience is the one ``get_exercise_for_user`` applies, so a uid that
        names no exercise is not-found and an exercise with no requirements an
        empty list. The unscoped ``get_required_knowledge`` serves reads that
        start from the user's own context (the daily plan).

        Backend: ExerciseBackend.get_required_knowledge_for_user
        """
        result = await self.backend.get_required_knowledge_for_user(exercise_uid, user_uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found(resource="Exercise", identifier=exercise_uid))
        return Result.ok(result.value)

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
        self, curriculum_uid: str, user_uid: UserUID
    ) -> Result[list[CurriculumExerciseResult]]:
        """
        The exercises requiring a curriculum KU that this user may read.

        Enables the reverse lookup: "what exercises practice this knowledge?" — a
        discovery listing, so a draft exercise is unlisted.

        Args:
            curriculum_uid: Curriculum KU UID
            user_uid: The requesting user

        Returns:
            Result containing list of exercise summaries

        Backend: ExerciseBackend.get_exercises_for_curriculum
        """
        result = await self.backend.get_exercises_for_curriculum(curriculum_uid, user_uid)

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

        today = today_in(current_zone())
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
