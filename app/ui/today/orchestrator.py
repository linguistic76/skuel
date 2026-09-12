"""Today Orchestrator.

Produces the ``TodayPageContext`` consumed by ``ui/today/page.py``: the day's
dated Activity across every domain, as per-domain lists of domain models. One
method, one shape. Lives in ``ui/today/`` — alongside its sole consumer and
the ``TodayPageContext`` TypedDict in ``ui/page_contexts.py`` — because the
output is a view shape, not a service-layer contract.

The orchestrator selects and sorts; it never re-shapes. Task membership comes
from ``ui/today/membership.py`` — the same predicates the defer guard
validates by, so render and guard cannot drift (act-from arc C7).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import TYPE_CHECKING

from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.neo4j_temporal import convert_neo4j_datetime
from core.utils.result_simplified import Result
from ui.page_contexts import TodayPageContext
from ui.today.membership import is_ribbon_member, is_triage_member

if TYPE_CHECKING:
    from core.models.choice.choice import Choice
    from core.models.event.calendar_models import CalendarItem
    from core.models.event.event import Event
    from core.models.goal.goal import Goal
    from core.models.task.task import Task
    from core.ports.service_protocols import CalendarServiceOperations
    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.tasks_service import TasksService

logger = get_logger("skuel.orchestrators.today")


def _date_label(day: date) -> str:
    """E.g. ``"Saturday · March 22"``."""
    return day.strftime("%A · %B ") + str(day.day)


def _heading_label(view_date: date, today: date) -> str:
    """The big H1 for the day lens: relative words near today, else a date.

    ``Today`` / ``Yesterday`` / ``Tomorrow`` for the three days the user reaches
    most; anything further out falls back to ``"Jul 19"`` (month + day), which
    the uppercase eyebrow (``_date_label``) disambiguates with the weekday.
    """
    delta = (view_date - today).days
    if delta == 0:
        return "Today"
    if delta == -1:
        return "Yesterday"
    if delta == 1:
        return "Tomorrow"
    return view_date.strftime("%b ") + str(view_date.day)


def moment_is_on_day(value: object, day: date) -> bool:
    """Whether a stored datetime (native or Neo4j temporal) falls on ``day``."""
    moment = convert_neo4j_datetime(value)
    return moment is not None and moment.date() == day


def choice_is_on_day(choice: Choice, day: date) -> bool:
    """A choice belongs to the day it is due to be decided or was decided on.

    Choices are the one other dated domain (Principles are dateless and have
    no day-view section): ``decision_deadline`` is the day's ask, ``decided_at``
    the day's answer — a choice decided on its deadline day renders once.
    """
    return moment_is_on_day(choice.decision_deadline, day) or moment_is_on_day(
        choice.decided_at, day
    )


def _task_order(task: Task) -> tuple[str, str]:
    return (task.due_date.isoformat() if task.due_date else "9999-12-31", task.title or "")


def _event_order(event: Event) -> tuple[str, str]:
    return (str(event.start_time or ""), event.title or "")


def _goal_order(goal: Goal) -> str:
    return goal.title or ""


def _choice_order(choice: Choice) -> tuple[str, str]:
    moment = convert_neo4j_datetime(choice.decision_deadline)
    return (moment.isoformat() if moment else "9999", choice.title or "")


def _or_empty[T](result: Result[list[T]], section: str) -> list[T]:
    """A failed section read renders as an empty section, logged — the day
    stays useful without it."""
    if result.is_error:
        logger.warning("today.%s read failed: %s", section, result.expect_error().message)
        return []
    return result.value


class TodayOrchestrator:
    """Facade for the day view.

    Composes the day's tasks, events, habits, goal milestones and choices into
    a flat ``TodayPageContext``. The orchestrator does NOT mutate — all writes
    happen through the individual domain services (the cards' status toggles
    post to the domains' status doors; quick-add and defer post to
    ``adapters/inbound/today_routes.py``).

    Reads are issued concurrently and degrade per section: a failed events
    read leaves Events empty while the rest of the day still renders. Tasks
    are the exception — the day's spine — so a failed task read fails the page.
    """

    def __init__(
        self,
        tasks_service: TasksService,
        events_service: EventsService,
        habits_service: HabitsService,
        goals_service: GoalsService,
        choices_service: ChoicesService,
        calendar_service: CalendarServiceOperations,
    ) -> None:
        self._tasks = tasks_service
        self._events = events_service
        self._habits = habits_service
        self._goals = goals_service
        self._choices = choices_service
        self._calendar = calendar_service

    async def build_context(
        self, user_uid: UserUID, view_date: date | None = None
    ) -> Result[TodayPageContext]:
        """Assemble the day view's context for this user and day (``None`` → today).

        Membership keys off ``view_date``; the relative heading and the
        overdue gate key off the real ``today`` — overdue is a present-tense
        surface and renders only on the live day.
        """
        today = datetime.now().date()
        view_date = view_date or today
        is_today = view_date == today

        tasks_r, events_r, habits_r, goals_r, choices_r = await asyncio.gather(
            self._tasks.get_user_tasks(user_uid),
            # The lens shows the day's truth: a completed event or an achieved
            # goal whose day this is still belongs to the day.
            self._events.get_user_items_in_range(
                user_uid, view_date, view_date, include_completed=True
            ),
            self._calendar.habit_items_for_day(user_uid, view_date),
            self._goals.get_user_items_in_range(
                user_uid, view_date, view_date, include_completed=True
            ),
            # Dated read, not "all choices then filter": the plain list is capped
            # at the backend's default limit, and a day's choice could sit past it.
            # The range query matches either date field (OR semantics); the
            # in-memory predicate below is the same rule stated once.
            self._choices.get_user_items_in_range(
                user_uid,
                view_date,
                view_date,
                include_completed=True,
                date_field=["decision_deadline", "decided_at"],
            ),
        )
        if tasks_r.is_error:
            return Result.fail(tasks_r)

        all_tasks = tasks_r.value
        overdue = (
            sorted((t for t in all_tasks if is_triage_member(t, today)), key=_task_order)
            if is_today
            else []
        )
        overdue_uids = {t.uid for t in overdue}
        tasks = sorted(
            (t for t in all_tasks if is_ribbon_member(t, view_date) and t.uid not in overdue_uids),
            key=_task_order,
        )
        events: list[Event] = sorted(_or_empty(events_r, "events"), key=_event_order)
        habits: list[CalendarItem] = _or_empty(habits_r, "habits")
        milestones: list[Goal] = sorted(_or_empty(goals_r, "goals"), key=_goal_order)
        choices: list[Choice] = sorted(
            (c for c in _or_empty(choices_r, "choices") if choice_is_on_day(c, view_date)),
            key=_choice_order,
        )

        return Result.ok(
            TodayPageContext(
                today_iso=view_date.isoformat(),
                date_label=_date_label(view_date),
                heading=_heading_label(view_date, today),
                is_today=is_today,
                # Quick-add is offered on today and future days only — you plan
                # work forward, not into a day already gone (act-from arc C6).
                # The POST backstops this too.
                can_quick_add=view_date >= today,
                overdue=overdue,
                tasks=tasks,
                events=events,
                habits=habits,
                milestones=milestones,
                choices=choices,
            )
        )
