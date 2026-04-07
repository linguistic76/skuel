"""Profile Orchestrator Facade.

Acts as a dedicated Read-Model Orchestrator for the User Profile Hub.
Aggregates logic for domain previews, recent reports, shared content, and
intelligence data — keeping the routing layer clean of orchestration
dependencies.
"""

from typing import TYPE_CHECKING, Any

from core.models.enums import Priority
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.orchestrator.submissions_orchestrator import SubmissionsOrchestrator  # noqa: F401
    from core.ports import (
        ExerciseReportOperations,
        SharingOperations,
    )
    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.exercises.exercise_service import ExerciseService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.principles_service import PrinciplesService
    from core.services.ps_service import PsService
    from core.services.report.activity_report_service import ActivityReportService
    from core.services.tasks_service import TasksService
    from core.services.user.intelligence.factory import UserContextIntelligenceFactory
    from core.services.user.unified_user_context import UserContext


logger = get_logger("skuel.orchestrators.profile")


_PREVIEW_PRIORITY_ORDER = {
    Priority.CRITICAL: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}

# Valid Activity Domain slugs
_PREVIEW_VALID_SLUGS = frozenset({"tasks", "goals", "habits", "events", "choices", "principles"})
_TERMINAL_STRINGS = frozenset(["completed", "failed", "cancelled", "archived"])


def _preview_priority_sort_key(item: Any) -> int:
    """Sort key for domain preview items by priority (CRITICAL first).

    Coerces string priority values to Priority enum before lookup so that
    service backends returning plain strings sort correctly.
    """
    raw = getattr(item, "priority", Priority.LOW)
    if not isinstance(raw, Priority):
        try:
            raw = Priority(str(raw).lower())
        except ValueError:
            raw = Priority.LOW
    return _PREVIEW_PRIORITY_ORDER.get(raw, 4)


class ProfileOrchestrator:
    """Facade for the User Profile Hub UI.

    Abstracts cross-domain reads so the UI routing layer depends only on this
    orchestrator. All service dependencies are required — bootstrap raises if
    any are missing (Fail-Fast Dependency Philosophy).

    ``context_intelligence`` is the one legitimate optional: it is ``None``
    when ``INTELLIGENCE_TIER=core``, and the orchestrator degrades to basic
    mode transparently.
    """

    def __init__(
        self,
        tasks_service: "TasksService",
        goals_service: "GoalsService",
        habits_service: "HabitsService",
        events_service: "EventsService",
        choices_service: "ChoicesService",
        principles_service: "PrinciplesService",
        exercise_report_service: "ExerciseReportOperations",
        activity_report_service: "ActivityReportService",
        sharing_service: "SharingOperations",
        ps_service: "PsService",
        exercises_service: "ExerciseService",
        context_intelligence: "UserContextIntelligenceFactory | None",
    ):
        self._tasks_service = tasks_service
        self._goals_service = goals_service
        self._habits_service = habits_service
        self._events_service = events_service
        self._choices_service = choices_service
        self._principles_service = principles_service
        self._exercise_report_service = exercise_report_service
        self._activity_report_service = activity_report_service
        self._sharing_service = sharing_service
        self._ps_service = ps_service
        self._exercises_service = exercises_service
        self._context_intelligence = context_intelligence

    async def get_assigned_exercises(self, user_uid: UserUID) -> Result[list[Any]]:
        """Get exercises assigned to this student."""
        return await self._exercises_service.get_student_exercises(user_uid)

    async def get_domain_preview_items(self, user_uid: UserUID, slug: str) -> Result[list[Any]]:
        """Get the top 3 active items for a domain, sorted by priority."""
        if slug not in _PREVIEW_VALID_SLUGS:
            return Result.fail(Errors.validation(f"Unknown domain slug: {slug}"))

        if slug == "tasks":
            result = await self._tasks_service.get_user_tasks(user_uid)
        elif slug == "goals":
            result = await self._goals_service.get_user_goals(user_uid)
        elif slug == "habits":
            result = await self._habits_service.get_user_habits(user_uid)
        elif slug == "events":
            result = await self._events_service.get_user_events(user_uid)
        elif slug == "choices":
            result = await self._choices_service.get_user_choices(user_uid)
        elif slug == "principles":
            result = await self._principles_service.get_user_principles(user_uid)
        else:
            return Result.fail(Errors.system(f"Unsupported slug: {slug}"))

        if result.is_error:
            return result

        active_items = [
            item
            for item in result.value
            if str(getattr(item, "status", "active")).lower() not in _TERMINAL_STRINGS
        ]
        sorted_items = sorted(active_items, key=_preview_priority_sort_key)
        return Result.ok(sorted_items[:3])

    async def get_recent_exercise_reports(self, user_uid: UserUID, limit: int = 5) -> Result[list[Any]]:
        """Get recent exercise reports for the user."""
        return await self._exercise_report_service.get_assessments_for_student(user_uid, limit=limit)

    async def get_recent_activity_reports(self, user_uid: UserUID, limit: int = 5) -> Result[list[Any]]:
        """Get recent activity reports for the user."""
        return await self._activity_report_service.get_history(user_uid, limit=limit)

    async def get_shared_with_me_items(self, user_uid: UserUID, limit: int = 50) -> Result[list[Any]]:
        """Get content shared with the user."""
        return await self._sharing_service.get_shared_with_me(user_uid=user_uid, limit=limit)

    async def get_knowledge_status(self, user_uid: UserUID) -> Result[list[Any]]:
        """Get user's knowledge unit relationship statuses."""
        return await self._ps_service.get_all_user_knowledge_status(user_uid)

    async def get_intelligence_data(
        self, context: "UserContext"
    ) -> "Result[dict[str, Any] | None]":
        """Gather cross-domain intelligence for the Profile Hub.

        Calls UserContextIntelligence methods independently so a failure in one
        does not block the others. Partial failures are collected in
        ``partial_errors`` so the UI can show a warning banner while still
        rendering the sections that succeeded.

        Returns:
            - ``Result.ok(dict)`` — intelligence data (some values may be ``None``
              on partial failure)
            - ``Result.ok(None)`` — intelligence not available (CORE tier or
              factory not configured); UI renders in basic mode
            - ``Result.fail()`` — all intelligence calls failed
        """
        if not self._context_intelligence:
            logger.info("Intelligence factory not configured — using basic mode")
            return Result.ok(None)

        try:
            intelligence = self._context_intelligence.create(context)
        except (AttributeError, TypeError, KeyError) as e:
            logger.warning(
                "Intelligence services not properly configured — using basic mode",
                extra={"error_type": type(e).__name__, "error_message": str(e)},
            )
            return Result.ok(None)

        daily_plan = alignment = synergies = path_steps = None
        partial_errors: list[str] = []

        try:
            plan_result = await intelligence.get_ready_to_work_on_today()
            if plan_result.is_error:
                partial_errors.append("Daily plan unavailable")
            else:
                daily_plan = plan_result.value
        except Exception as e:  # safety-net: individual intelligence call
            logger.warning(f"Daily plan call failed: {e}")
            partial_errors.append("Daily plan unavailable")

        try:
            alignment_result = await intelligence.calculate_life_path_alignment()
            if alignment_result.is_error:
                partial_errors.append("Life path alignment unavailable")
            else:
                alignment = alignment_result.value
        except Exception as e:  # safety-net: individual intelligence call
            logger.warning(f"Alignment call failed: {e}")
            partial_errors.append("Life path alignment unavailable")

        try:
            synergies_result = await intelligence.get_cross_domain_synergies()
            if synergies_result.is_error:
                partial_errors.append("Cross-domain synergies unavailable")
            else:
                synergies = synergies_result.value
        except Exception as e:  # safety-net: individual intelligence call
            logger.warning(f"Synergies call failed: {e}")
            partial_errors.append("Cross-domain synergies unavailable")

        try:
            steps_result = await intelligence.get_optimal_next_path_steps()
            if steps_result.is_error:
                partial_errors.append("Learning step recommendations unavailable")
            else:
                path_steps = steps_result.value
        except Exception as e:  # safety-net: individual intelligence call
            logger.warning(f"Learning steps call failed: {e}")
            partial_errors.append("Learning step recommendations unavailable")

        if all(v is None for v in [daily_plan, alignment, synergies, path_steps]):
            return Result.fail(Errors.system("All intelligence calls failed"))

        return Result.ok(
            {
                "daily_plan": daily_plan,
                "alignment": alignment,
                "synergies": synergies,
                "path_steps": path_steps,
                "partial_errors": partial_errors,
            }
        )
