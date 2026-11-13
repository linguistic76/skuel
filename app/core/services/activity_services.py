"""The six Activity Domain facades as one typed set.

The composition root builds every Activity facade in one call and hands the set
to the wiring steps that follow. Each key names its facade's class, so a read of
``activity_services["goals"]`` is a ``GoalsService`` to the type checker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.principles_service import PrinciplesService
    from core.services.tasks_service import TasksService


class ActivityServices(TypedDict):
    """One facade per Activity Domain, keyed by the domain's plural name."""

    tasks: TasksService
    events: EventsService
    habits: HabitsService
    goals: GoalsService
    choices: ChoicesService
    principles: PrinciplesService
