"""The per-view membership (``VIEW_SPECS``) — what each calendar view renders.

A view declares the kinds it admits and, per kind, the minimum priority
(calendar-priority-lens arc C1). ``CalendarService.get_calendar_view`` fetches
only the admitted kinds and filters the rest server-side; within the declared
membership, the legend's client-side filters are the only hiding mechanism.
An entity stating no priority reads as MEDIUM — the request-model default —
so an unstated habit is shown, not hidden.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums.activity_enums import Priority
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.scheduling_enums import RecurrencePattern
from core.models.event.calendar_models import (
    VIEW_SPECS,
    CalendarItemType,
    CalendarView,
    ViewSpec,
)
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.task.task import Task
from core.services.calendar_service import CalendarService
from core.utils.result_simplified import Result

_CREATED = datetime(2026, 7, 1, 8, 0)
_WEEK_START = date(2026, 8, 17)
_WEEK_END = date(2026, 8, 23)


def _task(uid: str, priority: str | None) -> Task:
    return Task(
        uid=uid,
        user_uid="user_test",
        title=f"Task {uid}",
        entity_type=EntityType.TASK,
        status=EntityStatus.ACTIVE,
        priority=priority,
        created_at=_CREATED,
        updated_at=_CREATED,
        due_date=date(2026, 8, 19),
    )


def _event(uid: str, priority: str | None) -> Event:
    return Event(
        uid=uid,
        user_uid="user_test",
        title=f"Event {uid}",
        entity_type=EntityType.EVENT,
        status=EntityStatus.SCHEDULED,
        priority=priority,
        created_at=_CREATED,
        updated_at=_CREATED,
        event_date=date(2026, 8, 19),
        start_time=time(10, 0),
        end_time=time(11, 0),
    )


def _goal(uid: str, priority: str | None) -> Goal:
    return Goal(
        uid=uid,
        user_uid="user_test",
        title=f"Goal {uid}",
        entity_type=EntityType.GOAL,
        status=EntityStatus.ACTIVE,
        priority=priority,
        created_at=_CREATED,
        updated_at=_CREATED,
        target_date=date(2026, 8, 21),
    )


def _habit(uid: str, priority: str | None) -> Habit:
    return Habit(
        uid=uid,
        user_uid="user_test",
        title=f"Habit {uid}",
        entity_type=EntityType.HABIT,
        status=EntityStatus.ACTIVE,
        priority=priority,
        recurrence_pattern=RecurrencePattern.DAILY,
        created_at=_CREATED,
        updated_at=_CREATED,
    )


def _service(
    *,
    tasks: Sequence[Task] = (),
    events: Sequence[Event] = (),
    goals: Sequence[Goal] = (),
    habits: Sequence[Habit] = (),
) -> tuple[CalendarService, SimpleNamespace]:
    """The service over mocked facades, plus the reads as ``AsyncMock`` handles
    (kept as locals — mypy types the facade attributes as the protocol's
    methods, which carry no ``assert_*`` API)."""
    reads = SimpleNamespace(
        tasks=AsyncMock(return_value=Result.ok(list(tasks))),
        events=AsyncMock(return_value=Result.ok(list(events))),
        goals=AsyncMock(return_value=Result.ok(list(goals))),
        habits=AsyncMock(return_value=Result.ok(list(habits))),
        completions=AsyncMock(return_value=Result.ok([])),
    )
    tasks_service, events_service, goals_service, habits_service = Mock(), Mock(), Mock(), Mock()
    tasks_service.get_user_items_in_range = reads.tasks
    events_service.get_user_items_in_range = reads.events
    goals_service.get_user_items_in_range = reads.goals
    habits_service.get_active = reads.habits
    habits_service.completions.get_completions_for_habit = reads.completions
    service = CalendarService(
        tasks_service=tasks_service,
        events_service=events_service,
        habits_service=habits_service,
        goals_service=goals_service,
    )
    return service, reads


async def _uids(service: CalendarService, view: CalendarView) -> list[str]:
    start, end = (
        (_WEEK_START, _WEEK_END)
        if view is CalendarView.WEEK
        else (
            date(2026, 8, 1),
            date(2026, 8, 31),
        )
    )
    result = await service.get_calendar_view("user_test", start, end, view)
    assert result.is_ok
    return sorted(item.uid for item in result.value.items)


# ---------------------------------------------------------------------------
# ViewSpec — the membership rule itself
# ---------------------------------------------------------------------------


def test_declared_membership_is_the_contract() -> None:
    """The two views' declarations, pinned: the month is events-only at
    medium+; the week is events/habits/milestones at medium+ and tasks at
    high. Changing a floor is a contract change, not a tweak."""
    assert dict(VIEW_SPECS[CalendarView.MONTH].members) == {
        CalendarItemType.EVENT: Priority.MEDIUM,
    }
    assert dict(VIEW_SPECS[CalendarView.WEEK].members) == {
        CalendarItemType.EVENT: Priority.MEDIUM,
        CalendarItemType.HABIT: Priority.MEDIUM,
        CalendarItemType.TASK: Priority.HIGH,
        CalendarItemType.MILESTONE: Priority.MEDIUM,
    }
    assert set(VIEW_SPECS) == set(CalendarView)


def test_admits_compares_against_the_kind_floor() -> None:
    spec = ViewSpec({CalendarItemType.TASK: Priority.HIGH, CalendarItemType.EVENT: Priority.MEDIUM})
    assert spec.admits(CalendarItemType.TASK, Priority.HIGH)
    assert not spec.admits(CalendarItemType.TASK, Priority.MEDIUM)
    assert not spec.admits(CalendarItemType.TASK, Priority.LOW)
    assert spec.admits(CalendarItemType.EVENT, Priority.HIGH)
    assert spec.admits(CalendarItemType.EVENT, Priority.MEDIUM)
    assert not spec.admits(CalendarItemType.EVENT, Priority.LOW)


def test_unstated_priority_reads_as_medium() -> None:
    """None is the request-model default, not "lowest": it clears a MEDIUM
    floor and fails a HIGH one."""
    spec = ViewSpec({CalendarItemType.TASK: Priority.HIGH, CalendarItemType.HABIT: Priority.MEDIUM})
    assert spec.admits(CalendarItemType.HABIT, None)
    assert not spec.admits(CalendarItemType.TASK, None)


def test_a_kind_outside_the_membership_is_never_admitted() -> None:
    spec = ViewSpec({CalendarItemType.EVENT: Priority.MEDIUM})
    assert not spec.admits_kind(CalendarItemType.HABIT)
    assert not spec.admits(CalendarItemType.HABIT, Priority.HIGH)


# ---------------------------------------------------------------------------
# get_calendar_view — the service renders the declaration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_month_fetches_events_only() -> None:
    """Non-member kinds are not fetched at all — the month issues no task,
    goal or habit read."""
    service, reads = _service(
        tasks=[_task("task_hi", "high")],
        events=[_event("event_mid", "medium")],
        goals=[_goal("goal_hi", "high")],
        habits=[_habit("habit_hi", "high")],
    )

    assert await _uids(service, CalendarView.MONTH) == ["event-event_mid"]
    reads.tasks.assert_not_awaited()
    reads.goals.assert_not_awaited()
    reads.habits.assert_not_awaited()


@pytest.mark.asyncio
async def test_month_drops_low_priority_events() -> None:
    service, _ = _service(
        events=[
            _event("event_low", "low"),
            _event("event_mid", "medium"),
            _event("event_hi", "high"),
        ]
    )
    assert await _uids(service, CalendarView.MONTH) == ["event-event_hi", "event-event_mid"]


@pytest.mark.asyncio
async def test_week_keeps_high_tasks_and_medium_plus_events_milestones_habits() -> None:
    service, _ = _service(
        tasks=[_task("task_hi", "high"), _task("task_mid", "medium"), _task("task_low", "low")],
        events=[_event("event_mid", "medium"), _event("event_low", "low")],
        goals=[_goal("goal_hi", "high"), _goal("goal_low", "low")],
        habits=[_habit("habit_mid", "medium"), _habit("habit_low", "low")],
    )

    assert await _uids(service, CalendarView.WEEK) == [
        "event-event_mid",
        "goal-goal_hi",
        "habit-habit_mid",
        "task-task_hi",
    ]


@pytest.mark.asyncio
async def test_week_reads_unstated_priority_as_medium() -> None:
    """A habit or event with no stated priority is shown; a task with none is
    below the HIGH floor and is not."""
    service, _ = _service(
        tasks=[_task("task_none", None)],
        events=[_event("event_none", None)],
        habits=[_habit("habit_none", None)],
    )

    assert await _uids(service, CalendarView.WEEK) == ["event-event_none", "habit-habit_none"]


@pytest.mark.asyncio
async def test_week_expands_occurrences_only_for_admitted_habits() -> None:
    """A habit below the floor is filtered before its occurrences are read —
    no completions query and no occurrence rows for it."""
    service, reads = _service(habits=[_habit("habit_mid", "medium"), _habit("habit_low", "low")])

    result = await service.get_calendar_view("user_test", _WEEK_START, _WEEK_END, CalendarView.WEEK)

    assert result.is_ok
    assert set(result.value.occurrences) == {"habit_mid"}
    assert reads.completions.await_count == 1
