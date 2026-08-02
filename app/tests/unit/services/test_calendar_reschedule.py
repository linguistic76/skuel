"""Unit tests for CalendarService.reschedule_item (act-from arc C4).

The reschedule moves the date that PLACES the item on the calendar:

- a scheduled task moves ``scheduled_date`` (an existing due_date is a
  separate fact and stays put);
- a due-only task renders as a deadline chip, so moving it moves
  ``due_date`` itself — writing ``scheduled_date`` would silently convert
  the deadline into a work chip while the real due date stayed behind
  (Codex P1 on PR #916);
- an event moves its date/start and keeps its duration;
- non-owner and habit/unknown item ids surface as not-found.

``reschedule_item`` touches only the injected domain services, so we build
the CalendarService with mocks and drive it directly.
"""

from __future__ import annotations

from datetime import date, datetime, time
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.event.calendar_models import CalendarItemType
from core.models.event.event import Event
from core.models.sentinels import UNSET
from core.models.task.task import Task
from core.services.calendar_service import CalendarService
from core.utils.result_simplified import ErrorCategory, Result


def _task(
    *,
    uid: str = "task_1",
    user_uid: str = "user_test",
    due: date | None = None,
    scheduled: date | None = None,
) -> Task:
    created = datetime(2026, 7, 1, 8, 0)
    return Task(
        uid=uid,
        user_uid=user_uid,
        title=f"Task {uid}",
        entity_type=EntityType.TASK,
        status=EntityStatus.ACTIVE,
        created_at=created,
        updated_at=created,
        due_date=due,
        scheduled_date=scheduled,
    )


def _event(
    *,
    uid: str = "event_1",
    user_uid: str = "user_test",
    event_date: date = date(2026, 8, 11),
    start: time = time(10, 0),
    end: time = time(11, 30),
) -> Event:
    created = datetime(2026, 7, 1, 8, 0)
    return Event(
        uid=uid,
        user_uid=user_uid,
        title=f"Event {uid}",
        entity_type=EntityType.EVENT,
        status=EntityStatus.SCHEDULED,
        created_at=created,
        updated_at=created,
        event_date=event_date,
        start_time=start,
        end_time=end,
    )


def _service(
    *, task: Task | None = None, event: Event | None = None
) -> tuple[CalendarService, Mock, Mock]:
    tasks_service = Mock()
    events_service = Mock()
    if task is not None:
        tasks_service.get = AsyncMock(return_value=Result.ok(task))
        tasks_service.update_task = AsyncMock(return_value=Result.ok(task))
    if event is not None:
        events_service.get = AsyncMock(return_value=Result.ok(event))
        events_service.update_event = AsyncMock(return_value=Result.ok(event))
    service = CalendarService(
        tasks_service=tasks_service,
        events_service=events_service,
        habits_service=Mock(),
    )
    return service, tasks_service, events_service


@pytest.mark.asyncio
async def test_scheduled_task_moves_scheduled_date() -> None:
    task = _task(scheduled=date(2026, 8, 10))
    service, tasks_service, _ = _service(task=task)

    result = await service.reschedule_item("user_test", "task-task_1", datetime(2026, 8, 20, 0, 0))

    assert result.is_ok
    intent = tasks_service.update_task.await_args.args[1]
    assert intent.scheduled_date == date(2026, 8, 20)
    assert intent.due_date is UNSET


@pytest.mark.asyncio
async def test_due_only_task_moves_due_date_and_stays_a_deadline() -> None:
    """Moving a deadline chip moves the deadline itself — the task must NOT
    gain a scheduled_date (which would re-render it as a work chip while the
    real due date stayed behind)."""
    task = _task(due=date(2026, 8, 10))
    moved = _task(due=date(2026, 8, 20))
    service, tasks_service, _ = _service(task=task)
    tasks_service.update_task = AsyncMock(return_value=Result.ok(moved))

    result = await service.reschedule_item("user_test", "task-task_1", datetime(2026, 8, 20, 0, 0))

    assert result.is_ok
    intent = tasks_service.update_task.await_args.args[1]
    assert intent.due_date == date(2026, 8, 20)
    assert intent.scheduled_date is UNSET
    assert result.value.item_type == CalendarItemType.TASK_DEADLINE


@pytest.mark.asyncio
async def test_task_with_both_dates_moves_scheduled_only() -> None:
    """A scheduled task's due_date is a separate fact — it stays put."""
    task = _task(due=date(2026, 8, 15), scheduled=date(2026, 8, 10))
    service, tasks_service, _ = _service(task=task)

    result = await service.reschedule_item("user_test", "task-task_1", datetime(2026, 8, 20, 0, 0))

    assert result.is_ok
    intent = tasks_service.update_task.await_args.args[1]
    assert intent.scheduled_date == date(2026, 8, 20)
    assert intent.due_date is UNSET


@pytest.mark.asyncio
async def test_non_owner_task_gets_not_found_without_mutation() -> None:
    task = _task(user_uid="user_other", scheduled=date(2026, 8, 10))
    service, tasks_service, _ = _service(task=task)

    result = await service.reschedule_item("user_test", "task-task_1", datetime(2026, 8, 20, 0, 0))

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.NOT_FOUND
    tasks_service.update_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_reschedule_preserves_duration() -> None:
    event = _event(start=time(10, 0), end=time(11, 30))  # 90 minutes
    service, _, events_service = _service(event=event)

    result = await service.reschedule_item(
        "user_test", "event-event_1", datetime(2026, 8, 12, 14, 15)
    )

    assert result.is_ok
    intent = events_service.update_event.await_args.args[1]
    assert intent.event_date == date(2026, 8, 12)
    assert intent.start_time == time(14, 15)
    assert intent.end_time == time(15, 45)  # 90 minutes preserved


@pytest.mark.asyncio
async def test_habit_item_id_is_not_found() -> None:
    service, _, _ = _service()

    result = await service.reschedule_item(
        "user_test", "habit-habit_1", datetime(2026, 8, 20, 0, 0)
    )

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.NOT_FOUND
