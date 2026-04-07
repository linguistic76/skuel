"""Library UI Orchestrator
=========================

Application orchestrator for the Library Hub. Consolidates Exercises,
Resources, KU, PathStep, Submissions, and UserRelationship services
into a single unified facade for UI rendering.
"""

from typing import Any

from core.utils.errors import Errors
from core.utils.result import Result


class LibraryOrchestrator:
    """Facade for the Library Hub UI layer."""

    def __init__(
        self,
        exercises_service: Any | None = None,
        resource_service: Any | None = None,
        ku_service: Any | None = None,
        ps_service: Any | None = None,
        submissions_service: Any | None = None,
        user_relationship_service: Any | None = None,
    ):
        self._exercises = exercises_service
        self._resource = resource_service
        self._ku = ku_service
        self._ps = ps_service
        self._submissions = submissions_service
        self._user_relationships = user_relationship_service

    # ------------------------------------------------------------------
    # Exercises
    # ------------------------------------------------------------------

    async def get_student_exercises_with_status(
        self, user_uid: str
    ) -> Result[list[Any]]:
        """Get exercises assigned to the student with submission/feedback status."""
        if not self._exercises:
            return Result.fail(Errors.system("Exercise service not initialized"))
        return await self._exercises.get_student_exercises_with_status(user_uid)

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    async def list_resources(self) -> Result[list[Any]]:
        """List all admin-curated resources."""
        if not self._resource:
            return Result.fail(Errors.system("Resource service not initialized"))
        return await self._resource.list_all()

    # ------------------------------------------------------------------
    # Submissions
    # ------------------------------------------------------------------

    async def list_exercise_submissions(
        self, user_uid: str, limit: int = 50
    ) -> Result[list[Any]]:
        """List user's exercise submissions."""
        if not self._submissions:
            return Result.fail(Errors.system("Submissions service not initialized"))
        from core.models.enums.entity_enums import EntityType

        return await self._submissions.list_submissions(
            user_uid, entity_type=EntityType.EXERCISE_SUBMISSION, limit=limit
        )

    # ------------------------------------------------------------------
    # Bookmarked KU
    # ------------------------------------------------------------------

    async def get_pinned_entities(self, user_uid: str) -> Result[Any]:
        """Get UIDs of entities pinned by the user."""
        if not self._user_relationships:
            return Result.ok([])
        return await self._user_relationships.get_pinned_entities(user_uid)

    async def get_bookmarked_kus(self, user_uid: str) -> Result[list[Any]]:
        """Get the KU entities that the user has pinned/bookmarked."""
        if not self._ku or not self._user_relationships:
            return Result.fail(
                Errors.system("KU or relationship service not initialized")
            )

        pins_result = await self._user_relationships.get_pinned_entities(user_uid)
        if pins_result.is_error:
            return pins_result

        pinned_uids = list(pins_result.value or [])
        if not pinned_uids:
            return Result.ok([])

        result = await self._ku.core.backend.get_many(pinned_uids)
        if result.is_error:
            return result

        kus = [ku for ku in (result.value or []) if ku is not None]
        return Result.ok(kus)

    async def get_bookmarked_kus_preview(
        self, user_uid: str, limit: int = 3
    ) -> Result[list[Any]]:
        """Get a limited preview of bookmarked KUs for hub cards."""
        if not self._ku or not self._user_relationships:
            return Result.ok([])

        pins_result = await self._user_relationships.get_pinned_entities(user_uid)
        if pins_result.is_error:
            return Result.ok([])

        pinned_uids = list(pins_result.value or [])
        if not pinned_uids:
            return Result.ok([])

        result = await self._ku.core.backend.get_many(pinned_uids[:limit])
        if result.is_error:
            return Result.ok([])

        kus = [ku for ku in (result.value or []) if ku is not None]
        return Result.ok(kus)

    # ------------------------------------------------------------------
    # Enrolled PathSteps
    # ------------------------------------------------------------------

    async def get_enrolled_path_steps(self, user_uid: str) -> Result[list[Any]]:
        """Get PathStep entities the user is currently enrolled in (IN_PROGRESS)."""
        if not self._ps:
            return Result.fail(Errors.system("PS service not initialized"))

        uids_result = await self._ps.mastery.get_in_progress_step_uids(user_uid)
        if uids_result.is_error:
            return uids_result

        enrolled_uids = list(uids_result.value or [])
        if not enrolled_uids:
            return Result.ok([])

        result = await self._ps.core.backend.get_many(enrolled_uids)
        if result.is_error:
            return result

        steps = [s for s in (result.value or []) if s is not None]
        return Result.ok(steps)

    async def get_enrolled_path_steps_preview(
        self, user_uid: str, limit: int = 3
    ) -> Result[list[Any]]:
        """Get a limited preview of enrolled PathSteps for hub cards."""
        if not self._ps:
            return Result.ok([])

        uids_result = await self._ps.mastery.get_in_progress_step_uids(user_uid)
        if uids_result.is_error:
            return Result.ok([])

        enrolled_uids = list(uids_result.value or [])
        if not enrolled_uids:
            return Result.ok([])

        result = await self._ps.core.backend.get_many(enrolled_uids[:limit])
        if result.is_error:
            return Result.ok([])

        steps = [s for s in (result.value or []) if s is not None]
        return Result.ok(steps)
