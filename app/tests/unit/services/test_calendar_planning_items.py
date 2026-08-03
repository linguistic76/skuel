"""Unit tests for CalendarService.get_planning_items (periodic-notes arc S3).

The weekly-note read panel's producer: tasks + events + goal Milestones for a
range, composed from the SAME internal fetches the calendar grid uses — so the
due-OR-scheduled task semantics (act-from arc C2) can never drift between the
two surfaces. Habits are deliberately excluded (v1 ruling: daily recurrence is
calendar texture, not weekly planning matter) and results are chronological.
"""

from __future__ import annotations

from datetime import date, datetime, time
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.event.calendar_models import CalendarItemType
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.task.task import Task
from core.services.calendar_service import CalendarService
from core.utils.result_simplified import Result

_WEEK_START = date(2026, 8, 3)
_WEEK_END = date(2026, 8, 9)
_CREATED = datetime(2026, 7, 1, 8, 0)


def _task(uid: str, *, due: date | None = None, scheduled: date | None = None) -> Task:
    return Task(
        uid=uid,
        user_uid="user_test",
        title=f"Task {uid}",
        entity_type=EntityType.TASK,
        status=EntityStatus.ACTIVE,
        created_at=_CREATED,
        updated_at=_CREATED,
        due_date=due,
        scheduled_date=scheduled,
    )


def _event(uid: str, *, on: date) -> Event:
    return Event(
        uid=uid,
        user_uid="user_test",
        title=f"Event {uid}",
        entity_type=EntityType.EVENT,
        status=EntityStatus.SCHEDULED,
        created_at=_CREATED,
        updated_at=_CREATED,
        event_date=on,
        start_time=time(10, 0),
        end_time=time(11, 0),
    )


def _goal(uid: str, *, target: date) -> Goal:
    return Goal(
        uid=uid,
        user_uid="user_test",
        title=f"Goal {uid}",
        entity_type=EntityType.GOAL,
        status=EntityStatus.ACTIVE,
        created_at=_CREATED,
        updated_at=_CREATED,
        target_date=target,
    )


def _service(
    tasks: list[Task] | None = None,
    events: list[Event] | None = None,
    goals: list[Goal] | None = None,
) -> tuple[CalendarService, Mock, Mock, Mock, Mock]:
    tasks_service = Mock()
    tasks_service.get_user_items_in_range = AsyncMock(return_value=Result.ok(tasks or []))
    events_service = Mock()
    events_service.get_user_items_in_range = AsyncMock(return_value=Result.ok(events or []))
    goals_service = Mock()
    goals_service.get_user_items_in_range = AsyncMock(return_value=Result.ok(goals or []))
    habits_service = Mock()
    service = CalendarService(
        tasks_service=tasks_service,
        events_service=events_service,
        habits_service=habits_service,
        goals_service=goals_service,
    )
    return service, tasks_service, events_service, goals_service, habits_service


@pytest.mark.asyncio
async def test_planning_items_compose_tasks_events_and_milestones() -> None:
    """All three producers feed the panel; the item kinds are the calendar's."""
    service, *_ = _service(
        tasks=[_task("task_a", scheduled=_WEEK_START)],
        events=[_event("event_a", on=date(2026, 8, 5))],
        goals=[_goal("goal_a", target=_WEEK_END)],
    )

    result = await service.get_planning_items("user_test", _WEEK_START, _WEEK_END)

    assert result.is_ok
    kinds = {i.item_type for i in result.value}
    assert kinds == {CalendarItemType.TASK, CalendarItemType.EVENT, CalendarItemType.MILESTONE}


@pytest.mark.asyncio
async def test_planning_items_use_due_or_scheduled_task_fetch() -> None:
    """C2 semantics ride along: the task fetch asks for BOTH date fields."""
    service, tasks_service, *_ = _service()

    await service.get_planning_items("user_test", _WEEK_START, _WEEK_END)

    tasks_service.get_user_items_in_range.assert_awaited_once_with(
        user_uid="user_test",
        start_date=_WEEK_START,
        end_date=_WEEK_END,
        include_completed=False,
        date_field=["due_date", "scheduled_date"],
    )


@pytest.mark.asyncio
async def test_planning_items_never_touch_habits() -> None:
    """Habits are deliberately excluded from the weekly panel (v1 ruling)."""
    service, _t, _e, _g, habits_service = _service()

    result = await service.get_planning_items("user_test", _WEEK_START, _WEEK_END)

    assert result.is_ok
    habits_service.get_active.assert_not_called()
    habits_service.get_user_habits.assert_not_called()


@pytest.mark.asyncio
async def test_planning_items_are_chronological() -> None:
    """Items sort by start_time across kinds, not by producer order."""
    service, *_ = _service(
        tasks=[_task("task_late", scheduled=date(2026, 8, 8))],
        events=[_event("event_mid", on=date(2026, 8, 5))],
        goals=[_goal("goal_early", target=date(2026, 8, 3))],
    )

    result = await service.get_planning_items("user_test", _WEEK_START, _WEEK_END)

    assert result.is_ok
    assert [i.uid for i in result.value] == ["goal-goal_early", "event-event_mid", "task-task_late"]


@pytest.mark.asyncio
async def test_dual_date_task_placed_outside_the_range_is_filtered() -> None:
    """A task scheduled BEFORE the week but due within it matches the OR fetch,
    yet its placement day (scheduled-first, ``_task_to_calendar_item``) falls
    outside the range — the week grid never renders that chip, so the panel
    must not list it either (it shows on its scheduled day's week). Codex #923."""
    dual = _task("task_dual", due=date(2026, 8, 5), scheduled=date(2026, 7, 30))
    in_week = _task("task_in", scheduled=date(2026, 8, 4))
    service, *_ = _service(tasks=[dual, in_week])

    result = await service.get_planning_items("user_test", _WEEK_START, _WEEK_END)

    assert result.is_ok
    assert [i.uid for i in result.value] == ["task-task_in"]


@pytest.mark.asyncio
async def test_due_only_task_carries_the_due_state() -> None:
    """A due-but-unscheduled task is a Task WITH is_due=True (E1: state, not kind)."""
    service, *_ = _service(tasks=[_task("task_due", due=date(2026, 8, 7))])

    result = await service.get_planning_items("user_test", _WEEK_START, _WEEK_END)

    assert result.is_ok
    (item,) = result.value
    assert item.item_type == CalendarItemType.TASK
    assert item.is_due is True
