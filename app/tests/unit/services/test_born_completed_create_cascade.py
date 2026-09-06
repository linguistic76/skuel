"""A born-completed entity cascades at the CREATE door, not only at the update one.

An entity can arrive already ``COMPLETED``: a vault ``- [x] … ✅ 2026-03-04`` line
becomes a ``TaskCreateRequest(status=COMPLETED, completion_date=✅date)``, and the
entity door persists whatever status it is handed. That entity never passes through
``update_task`` / ``update_goal`` / ``update_event``, which is where the transition
events are published — so every completion subscriber (goal progress, PS engagement
auto-complete, duration calibration, productivity analytics, context invalidation)
was silently skipped for it. The create door announced ``TaskCreated`` /
``GoalCreated`` / ``CalendarEventCreated`` and nothing else.

A create has NO prior status, so a created-completed entity is unambiguously a
transition INTO completed: ``is_repeat`` is False and no prior-status machinery is
needed. The gate is the entity's own status, which is why a non-completed create must
stay silent — that is the half a "does it publish?" assertion cannot see.

``occurred_at`` carries the entity's OWN completion stamp (CLAUDE.md's sanctioned
carry-forward), so a backfilled historical completion reports the day it happened.
That is what makes ``ProductivityAnalytics.last_completion_at`` order-sensitive for
the first time, and the monotone-max half of the fix is pinned in
``tests/integration/test_productivity_stamp_monotone.py`` — a Python-side assertion
here could not see it, because the ordering lives in the Cypher.

Habit and Choice are deliberately absent: neither has an entity-completion event
(``HabitCompleted`` is a logged daily OCCURRENCE, ``ChoiceMade`` is the DRAFT→ACTIVE
decide moment), and inventing one with no subscribers would be staged bloat.

No Neo4j: the backend is stubbed, so what is under test is the service wiring —
which is exactly where the gap lived.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.events.base import BaseEvent
from core.events.calendar_event_events import CalendarEventCompleted, CalendarEventCreated
from core.events.goal_events import GoalAchieved, GoalCreated
from core.events.task_events import TaskCompleted, TaskCreated
from core.models.enums import EntityStatus
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.task.task import Task
from core.services.events.events_core_service import EventsCoreService
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.tasks.tasks_core_service import TasksCoreService
from core.utils.result_simplified import Errors, Result

USER = "user_born_completed"


class _RecordingBus:
    """Captures published events; ``publish_async`` is the whole contract."""

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


class _RoundTripBackend:
    """Round-trips ``create`` the way ``UniversalNeo4jBackend._create_node`` does.

    The serialization must be the real one: the announcers read ``status`` and the
    completion stamp off the entity the backend RETURNS, and returning the input
    unchanged would hide a field the mapper drops on the way in.

    ``__getattr__`` fails CLOSED — a backend call this stub does not model is an
    assertion failure, never a silent mock.
    """

    def __init__(self, model: type) -> None:
        self._model = model

    async def create(self, entity: Any) -> Result[Any]:
        return Result.ok(from_neo4j_node(to_neo4j_node(entity), self._model))

    async def get(self, uid: str) -> Result[Any]:
        return Result.fail(Errors.not_found(self._model.__name__, uid))

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"Unmodelled backend call: {name}")


def _tasks() -> tuple[TasksCoreService, _RecordingBus]:
    bus = _RecordingBus()
    return TasksCoreService(backend=_RoundTripBackend(Task), event_bus=bus), bus


def _goals() -> tuple[GoalsCoreService, _RecordingBus]:
    bus = _RecordingBus()
    return GoalsCoreService(backend=_RoundTripBackend(Goal), event_bus=bus), bus


def _events() -> tuple[EventsCoreService, _RecordingBus]:
    bus = _RecordingBus()
    return EventsCoreService(backend=_RoundTripBackend(Event), event_bus=bus), bus


# ---------------------------------------------------------------------------
# 1. Task — the door carrying the live traffic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTaskCreatedCompleted:
    async def test_a_dsl_checked_line_cascades_task_completed(self) -> None:
        """The `- [x]` path end to end: parse → convert → create."""
        from core.services.dsl.activity_domain_converters import activity_to_task_request
        from core.services.dsl.obsidian_tasks_adapter import obsidian_task_line_to_parsed

        parsed = obsidian_task_line_to_parsed("- [x] Review the notes ✅ 2026-03-04")
        assert parsed is not None and parsed.is_checked
        request = activity_to_task_request(parsed).value

        service, bus = _tasks()
        result = await service.create_task(request, USER)

        assert result.is_ok
        completed = bus.of(TaskCompleted)
        assert len(completed) == 1
        assert completed[0].task_uid == result.value.uid
        assert completed[0].user_uid == USER
        assert completed[0].is_repeat is False

    async def test_the_authored_done_date_becomes_occurred_at(self) -> None:
        from core.services.dsl.activity_domain_converters import activity_to_task_request
        from core.services.dsl.obsidian_tasks_adapter import obsidian_task_line_to_parsed

        parsed = obsidian_task_line_to_parsed("- [x] Review the notes ✅ 2026-03-04")
        assert parsed is not None
        service, bus = _tasks()

        await service.create_task(activity_to_task_request(parsed).value, USER)

        assert bus.of(TaskCompleted)[0].occurred_at == datetime(2026, 3, 4, 0, 0)

    async def test_the_created_event_is_announced_first(self) -> None:
        """``TaskCreated`` is what invalidates the user context — it must not be
        preceded by the completion event."""
        service, bus = _tasks()
        task = Task(
            uid="task_born",
            user_uid=USER,
            title="done on arrival",
            status=EntityStatus.COMPLETED,
            completion_date=date(2026, 3, 4),
        )

        await service.create(task)

        order = [type(event) for event in bus.events]
        assert order.index(TaskCreated) < order.index(TaskCompleted)

    async def test_an_uncompleted_create_publishes_no_completion_event(self) -> None:
        service, bus = _tasks()

        await service.create(Task(uid="task_open", user_uid=USER, title="still open"))

        assert bus.of(TaskCreated)
        assert bus.of(TaskCompleted) == []

    async def test_a_historical_task_completed_on_time_is_not_reported_overdue(self) -> None:
        """``was_overdue`` is measured against the COMPLETION moment, not today.

        Measured against ``date.today()`` — the reference the update chokepoint uses,
        where the two are the same day — every backfilled task with a past due date
        would be announced overdue, and the overdue branch APPENDS a PersistedInsight.
        """
        service, bus = _tasks()
        task = Task(
            uid="task_history",
            user_uid=USER,
            title="delivered early",
            status=EntityStatus.COMPLETED,
            completion_date=date(2026, 3, 4),
            due_date=date(2026, 3, 10),
        )

        await service.create(task)

        assert bus.of(TaskCompleted)[0].was_overdue is False

    async def test_a_task_completed_after_its_due_date_still_reports_overdue(self) -> None:
        service, bus = _tasks()
        task = Task(
            uid="task_late",
            user_uid=USER,
            title="delivered late",
            status=EntityStatus.COMPLETED,
            completion_date=date(2026, 3, 10),
            due_date=date(2026, 3, 4),
        )

        await service.create(task)

        assert bus.of(TaskCompleted)[0].was_overdue is True

    async def test_a_dateless_completed_create_falls_back_to_now(self) -> None:
        service, bus = _tasks()
        before = datetime.now()

        await service.create(
            Task(uid="task_nodate", user_uid=USER, title="no stamp", status=EntityStatus.COMPLETED)
        )

        assert before <= bus.of(TaskCompleted)[0].occurred_at <= datetime.now()


# ---------------------------------------------------------------------------
# 2. Goal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGoalCreatedCompleted:
    async def test_a_born_achieved_goal_cascades_goal_achieved(self) -> None:
        service, bus = _goals()
        goal = Goal(
            uid="goal_born",
            user_uid=USER,
            title="shipped",
            status=EntityStatus.COMPLETED,
            achieved_date=date(2026, 3, 4),
        )

        result = await service.create(goal)

        assert result.is_ok
        achieved = bus.of(GoalAchieved)
        assert len(achieved) == 1
        assert achieved[0].goal_uid == "goal_born"
        assert achieved[0].occurred_at == datetime(2026, 3, 4, 0, 0)

    async def test_the_created_event_is_announced_first(self) -> None:
        service, bus = _goals()
        goal = Goal(
            uid="goal_order",
            user_uid=USER,
            title="shipped",
            status=EntityStatus.COMPLETED,
            achieved_date=date(2026, 3, 4),
        )

        await service.create(goal)

        order = [type(event) for event in bus.events]
        assert order.index(GoalCreated) < order.index(GoalAchieved)

    async def test_an_active_goal_publishes_no_achievement(self) -> None:
        service, bus = _goals()

        await service.create(Goal(uid="goal_open", user_uid=USER, title="in flight"))

        assert bus.of(GoalCreated)
        assert bus.of(GoalAchieved) == []


# ---------------------------------------------------------------------------
# 3. Event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCalendarEventCreatedCompleted:
    async def test_a_born_completed_event_cascades_completion(self) -> None:
        service, bus = _events()
        event = Event(
            uid="event_born",
            user_uid=USER,
            title="the workshop",
            status=EntityStatus.COMPLETED,
            event_date=date(2026, 3, 4),
            completed_at=datetime(2026, 3, 4, 17, 30),
        )

        result = await service.create(event)

        assert result.is_ok
        completed = bus.of(CalendarEventCompleted)
        assert len(completed) == 1
        assert completed[0].event_uid == "event_born"
        assert completed[0].completion_date == date(2026, 3, 4)
        assert completed[0].quality_score is None
        assert completed[0].occurred_at == datetime(2026, 3, 4, 17, 30)

    async def test_the_created_event_is_announced_first(self) -> None:
        service, bus = _events()
        event = Event(
            uid="event_order",
            user_uid=USER,
            title="the workshop",
            status=EntityStatus.COMPLETED,
            event_date=date(2026, 3, 4),
            completed_at=datetime(2026, 3, 4, 17, 30),
        )

        await service.create(event)

        order = [type(published) for published in bus.events]
        assert order.index(CalendarEventCreated) < order.index(CalendarEventCompleted)

    async def test_a_scheduled_event_publishes_no_completion(self) -> None:
        service, bus = _events()

        await service.create(
            Event(uid="event_open", user_uid=USER, title="upcoming", event_date=date(2026, 3, 4))
        )

        assert bus.of(CalendarEventCreated)
        assert bus.of(CalendarEventCompleted) == []
