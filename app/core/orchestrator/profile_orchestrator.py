"""Profile Orchestrator Facade.

Acts as a dedicated Read-Model Orchestrator for the User Profile Hub.
Aggregates logic for domain previews and shared content — keeping the
routing layer clean of orchestration dependencies.
"""

from typing import TYPE_CHECKING, Any

from core.models.enums import Priority
from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import SharingOperations
    from core.ports.query_types import SharedWithMeItem
    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.principles_service import PrinciplesService
    from core.services.tasks_service import TasksService


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
    """

    def __init__(
        self,
        tasks_service: "TasksService",
        goals_service: "GoalsService",
        habits_service: "HabitsService",
        events_service: "EventsService",
        choices_service: "ChoicesService",
        principles_service: "PrinciplesService",
        sharing_service: "SharingOperations",
    ) -> None:
        self._tasks_service = tasks_service
        self._goals_service = goals_service
        self._habits_service = habits_service
        self._events_service = events_service
        self._choices_service = choices_service
        self._principles_service = principles_service
        self._sharing_service = sharing_service

    async def get_domain_preview_items(self, user_uid: UserUID, slug: str) -> Result[list[Any]]:
        """Get the top 3 active items for a domain, sorted by priority."""
        if slug not in _PREVIEW_VALID_SLUGS:
            return Result.fail(Errors.validation(f"Unknown domain slug: {slug}"))

        result: Result[list[Any]]
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

    async def get_shared_with_me_items(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[SharedWithMeItem]]:
        """Get content shared with the user (entity DTO + share-edge metadata
        + resolved subject context)."""
        return await self._sharing_service.get_shared_with_me(user_uid=user_uid, limit=limit)
