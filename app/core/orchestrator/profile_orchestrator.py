"""Profile Orchestrator Facade.

Acts as a dedicated Read-Model Orchestrator for the User Profile Hub.
Aggregates logic for domain previews, recent reports, and shared content,
keeping the routing layer clean of orchestration dependencies.
"""

from typing import TYPE_CHECKING, Any

from core.models.enums import Priority
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import (
        ExerciseReportOperations,
        SharingOperations,
    )
    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.principles_service import PrinciplesService
    from core.services.ps_service import PsService
    from core.services.report.activity_report_service import ActivityReportService
    from core.services.tasks_service import TasksService


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
    """Sort key for domain card preview items by priority (CRITICAL first)."""
    raw = getattr(item, "priority", Priority.LOW)
    if not isinstance(raw, Priority):
        try:
            raw = Priority(str(raw).lower())
        except ValueError:
            raw = Priority.LOW
    return _PREVIEW_PRIORITY_ORDER.get(raw, 4)


class ProfileOrchestrator:
    """Facade for the User Profile Hub UI.
    
    Abstracts cross-domain reads so the UI routing layer depends only on this orchestrator.
    """

    def __init__(
        self,
        tasks_service: "TasksService | None",
        goals_service: "GoalsService | None",
        habits_service: "HabitsService | None",
        events_service: "EventsService | None",
        choices_service: "ChoicesService | None",
        principles_service: "PrinciplesService | None",
        exercise_report_service: "ExerciseReportOperations | None",
        activity_report_service: "ActivityReportService | None",
        sharing_service: "SharingOperations | None",
        ps_service: "PsService | None",
        exercises_service: "Any | None" = None,
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

    async def get_assigned_exercises(self, user_uid: UserUID) -> Result[list[Any]]:
        """Get exercises assigned to this student."""
        if not self._exercises_service:
            return Result.fail(Errors.system("Exercises service not initialized"))
        return await self._exercises_service.get_student_exercises(user_uid)

    async def get_domain_preview_items(self, user_uid: UserUID, slug: str) -> Result[list[Any]]:
        """Get the top 3 active items for a domain, sorted by priority."""
        if slug not in _PREVIEW_VALID_SLUGS:
            return Result.fail(Errors.validation(f"Unknown domain slug: {slug}"))

        if slug == "tasks":
            if not self._tasks_service:
                return Result.fail(Errors.system("Tasks service not initialized"))
            result = await self._tasks_service.get_user_tasks(user_uid)
        elif slug == "goals":
            if not self._goals_service:
                return Result.fail(Errors.system("Goals service not initialized"))
            result = await self._goals_service.get_user_goals(user_uid)
        elif slug == "habits":
            if not self._habits_service:
                return Result.fail(Errors.system("Habits service not initialized"))
            result = await self._habits_service.get_user_habits(user_uid)
        elif slug == "events":
            if not self._events_service:
                return Result.fail(Errors.system("Events service not initialized"))
            result = await self._events_service.get_user_events(user_uid)
        elif slug == "choices":
            if not self._choices_service:
                return Result.fail(Errors.system("Choices service not initialized"))
            result = await self._choices_service.get_user_choices(user_uid)
        elif slug == "principles":
            if not self._principles_service:
                return Result.fail(Errors.system("Principles service not initialized"))
            result = await self._principles_service.get_user_principles(user_uid)
        else:
            return Result.fail(Errors.system(f"Unsupported slug: {slug}"))

        if result.is_error:
            return result

        # Filter out terminal states and sort
        active_items = [
            item
            for item in result.value
            if str(getattr(item, "status", "active")).lower() not in _TERMINAL_STRINGS
        ]
        
        sorted_items = sorted(active_items, key=_preview_priority_sort_key)
        
        # Return top 3
        return Result.ok(sorted_items[:3])

    async def get_recent_exercise_reports(self, user_uid: UserUID, limit: int = 5) -> Result[list[Any]]:
        """Get recent exercise reports for the user."""
        if not self._exercise_report_service:
            return Result.fail(Errors.system("Exercise report service not initialized"))
        return await self._exercise_report_service.get_assessments_for_student(user_uid, limit=limit)

    async def get_recent_activity_reports(self, user_uid: UserUID, limit: int = 5) -> Result[list[Any]]:
        """Get recent activity reports for the user."""
        if not self._activity_report_service:
            return Result.fail(Errors.system("Activity report service not initialized"))
        return await self._activity_report_service.get_history(user_uid, limit=limit)

    async def get_shared_with_me_items(self, user_uid: UserUID, limit: int = 50) -> Result[list[Any]]:
        """Get content shared with the user."""
        if not self._sharing_service:
            return Result.fail(Errors.system("Sharing service not initialized"))
        return await self._sharing_service.get_shared_with_me(user_uid=user_uid, limit=limit)

    async def get_knowledge_status(self, user_uid: UserUID) -> Result[list[Any]]:
        """Get user's knowledge unit relationship statuses."""
        if not self._ps_service:
            return Result.fail(Errors.system("Path Steps (knowledge) service not initialized"))
        return await self._ps_service.get_all_user_knowledge_status(user_uid)
