"""Library UI Orchestrator
=========================

Application orchestrator for the Library Hub. Consolidates Exercises,
Resources, KU, PathStep, UserEntry, and UserRelationship services
into a single unified facade for UI rendering.

All service dependencies are required — bootstrap raises if any are missing
(Fail-Fast Dependency Philosophy).
"""

from typing import TYPE_CHECKING, Any

from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.ku.ku import Ku
    from core.models.pathways.path_step import PathStep
    from core.ports.relationship_backend_protocols import UserRelationshipOperations
    from core.services.exercises.exercise_service import ExerciseService
    from core.services.ku_service import KuService
    from core.services.ps_service import PsService
    from core.services.resource_service import ResourceService
    from core.services.user_entry.user_entry_service import UserEntryService


class LibraryOrchestrator:
    """Facade for the Library Hub UI layer.

    Abstracts cross-domain reads so the UI routing layer depends only on this
    orchestrator. All service dependencies are required — bootstrap raises if
    any are missing (Fail-Fast Dependency Philosophy).
    """

    def __init__(
        self,
        exercises_service: "ExerciseService",
        resource_service: "ResourceService",
        ku_service: "KuService",
        ps_service: "PsService",
        user_entry_service: "UserEntryService",
        user_relationship_service: "UserRelationshipOperations",
    ) -> None:
        self._exercises = exercises_service
        self._resource = resource_service
        self._ku = ku_service
        self._ps = ps_service
        self._user_entry = user_entry_service
        self._user_relationships = user_relationship_service

    # ------------------------------------------------------------------
    # Exercises
    # ------------------------------------------------------------------

    async def get_student_exercises_with_status(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[Any]]:
        """Get exercises assigned to the student with submission/feedback status.

        Args:
            user_uid: The student to look up exercises for.
            limit: Cap the returned list (pushed down to the backend queries).
                ``None`` returns all exercises.
        """
        return await self._exercises.get_student_exercises_with_status(user_uid, limit=limit)

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    async def list_resources(self, limit: int = 500) -> Result[list[Any]]:
        """List admin-curated resources sorted by title.

        Args:
            limit: Cap the returned list (pushed down to the backend query).
        """
        return await self._resource.list_all(limit=limit)

    async def get_resource(self, uid: str) -> Result[Any]:
        """Fetch one curated Resource by UID for the detail page.

        Returns ``Result.ok(None)`` when the UID has no match — the route
        applies the ``require_found`` guard.
        """
        return await self._resource.get(uid)

    async def get_citing_entities(self, uid: str) -> Result[list[Neo4jProperties]]:
        """Fetch the Kus / PathSteps that cite this Resource ("Cited by" section).

        Reverse CITES_RESOURCE traversal for the detail page's citation
        provenance — each row carries the citer's uid, title, entity_type, and
        the citation locator.
        """
        return await self._resource.get_citing_entities(uid)

    # ------------------------------------------------------------------
    # UserEntry — teacher-review pipeline (ADR-054)
    # ------------------------------------------------------------------

    async def list_exercise_submissions(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[Any]]:
        """List the user's exercise submissions (pipeline=TEACHER_REVIEW entries)."""
        from core.models.enums.pipeline import Pipeline

        result = await self._user_entry.list_for_user(
            user_uid=user_uid,
            pipeline=Pipeline.TEACHER_REVIEW,
            limit=limit,
        )
        if result.is_error:
            return result
        return Result.ok(list(result.value or []))

    # ------------------------------------------------------------------
    # Bookmarked KU
    # ------------------------------------------------------------------

    async def get_bookmarked_kus(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[Ku]]:
        """Get the KU entities that the user has pinned/bookmarked.

        Args:
            user_uid: The user to look up pins for.
            limit: Cap the returned list. ``None`` returns all pinned KUs.
        """
        pins_result = await self._user_relationships.get_pinned_entities(user_uid)
        if pins_result.is_error:
            return Result.fail(pins_result)

        pinned_uids = list(pins_result.value or [])
        if not pinned_uids:
            return Result.ok([])

        fetch_uids = pinned_uids[:limit] if limit is not None else pinned_uids
        result = await self._ku.get_kus_batch(fetch_uids)
        if result.is_error:
            return Result.fail(result)

        kus = [ku for ku in (result.value or []) if ku is not None]
        return Result.ok(kus)

    # ------------------------------------------------------------------
    # Enrolled PathSteps
    # ------------------------------------------------------------------

    async def get_enrolled_path_steps(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[PathStep]]:
        """Get PathStep entities the user is currently enrolled in (IN_PROGRESS).

        Args:
            user_uid: The user to look up enrollment for.
            limit: Cap the returned list. ``None`` returns all enrolled steps.
        """
        uids_result = await self._ps.mastery.get_in_progress_step_uids(user_uid)
        if uids_result.is_error:
            return Result.fail(uids_result)

        enrolled_uids = list(uids_result.value or [])
        if not enrolled_uids:
            return Result.ok([])

        fetch_uids = enrolled_uids[:limit] if limit is not None else enrolled_uids
        result = await self._ps.get_steps_batch(fetch_uids)
        if result.is_error:
            return Result.fail(result)

        steps = [s for s in (result.value or []) if s is not None]
        return Result.ok(steps)

    # ------------------------------------------------------------------
    # Pinned entity UIDs (pass-through for sidebar / other consumers)
    # ------------------------------------------------------------------

    async def get_pinned_entities(self, user_uid: UserUID) -> Result[Any]:
        """Get UIDs of entities pinned by the user."""
        return await self._user_relationships.get_pinned_entities(user_uid)
