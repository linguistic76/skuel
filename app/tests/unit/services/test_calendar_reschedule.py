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
from core.models.event.calendar_models import CalendarItemType, parse_calendar_item_uid
from core.models.event.event import Event
from core.models.sentinels import UNSET
from core.models.task.task import Task
from core.services.calendar_service import CalendarService
from core.utils.result_simplified import ErrorCategory, Errors, Result


def _task(
    *,
    uid: str = "task_1",
    user_uid: str = "user_test",
    due: date | None = None,
    scheduled: date | None = None,
    recurrence_end: date | None = None,
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
        recurrence_end_date=recurrence_end,
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

    result = await service.reschedule_item("user_test", "task-task_1", datetime(2026, 8, 14, 0, 0))

    assert result.is_ok
    intent = tasks_service.update_task.await_args.args[1]
    assert intent.scheduled_date == date(2026, 8, 14)
    assert intent.due_date is UNSET


@pytest.mark.asyncio
async def test_work_date_may_land_exactly_on_the_deadline() -> None:
    """due_date == scheduled_date is legal (creation forbids only due < scheduled)."""
    task = _task(due=date(2026, 8, 15), scheduled=date(2026, 8, 10))
    service, tasks_service, _ = _service(task=task)

    result = await service.reschedule_item("user_test", "task-task_1", datetime(2026, 8, 15, 0, 0))

    assert result.is_ok
    assert tasks_service.update_task.await_args.args[1].scheduled_date == date(2026, 8, 15)


@pytest.mark.asyncio
async def test_work_date_past_the_deadline_is_refused() -> None:
    """Creation forbids due_date < scheduled_date and the update path doesn't
    recheck — the calendar must not persist work scheduled after its own
    deadline."""
    task = _task(due=date(2026, 8, 15), scheduled=date(2026, 8, 10))
    service, tasks_service, _ = _service(task=task)

    result = await service.reschedule_item("user_test", "task-task_1", datetime(2026, 8, 20, 0, 0))

    assert result.is_error
    error = result.expect_error()
    assert error.category == ErrorCategory.VALIDATION
    assert "2026-08-15" in error.message  # names the deadline so the form shows it
    tasks_service.update_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_recurring_deadline_move_onto_or_past_recurrence_end_is_refused() -> None:
    """Task twin of the event recurrence guard: creation forbids due_date
    on/after recurrence_end_date — a deadline move must not persist a
    recurrence window that ends before it starts."""
    task = _task(due=date(2026, 8, 10), recurrence_end=date(2026, 8, 20))
    service, tasks_service, _ = _service(task=task)

    result = await service.reschedule_item("user_test", "task-task_1", datetime(2026, 8, 20, 0, 0))

    assert result.is_error
    error = result.expect_error()
    assert error.category == ErrorCategory.VALIDATION
    assert "2026-08-20" in error.message  # names the recurrence end
    tasks_service.update_task.assert_not_awaited()

    # Strictly before the recurrence end stays legal.
    result = await service.reschedule_item("user_test", "task-task_1", datetime(2026, 8, 19, 0, 0))
    assert result.is_ok
    assert tasks_service.update_task.await_args.args[1].due_date == date(2026, 8, 19)


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
async def test_event_move_onto_or_past_recurrence_end_is_refused() -> None:
    """Creation forbids event_date on/after recurrence_end_date — the move
    must not persist a recurrence window that ends before it starts."""
    event = Event(
        uid="event_1",
        user_uid="user_test",
        title="Weekly sync",
        entity_type=EntityType.EVENT,
        status=EntityStatus.SCHEDULED,
        created_at=datetime(2026, 7, 1, 8, 0),
        updated_at=datetime(2026, 7, 1, 8, 0),
        event_date=date(2026, 8, 11),
        start_time=time(10, 0),
        end_time=time(11, 0),
        recurrence_end_date=date(2026, 8, 20),
    )
    service, _, events_service = _service(event=event)

    result = await service.reschedule_item(
        "user_test", "event-event_1", datetime(2026, 8, 20, 10, 0)
    )

    assert result.is_error
    error = result.expect_error()
    assert error.category == ErrorCategory.VALIDATION
    assert "2026-08-20" in error.message  # names the recurrence end
    events_service.update_event.assert_not_awaited()

    # Strictly before the recurrence end stays legal.
    result = await service.reschedule_item(
        "user_test", "event-event_1", datetime(2026, 8, 19, 10, 0)
    )
    assert result.is_ok
    assert events_service.update_event.await_args.args[1].event_date == date(2026, 8, 19)


@pytest.mark.asyncio
async def test_event_move_crossing_midnight_is_refused() -> None:
    """The Event model is single-day: an end past midnight would persist
    end_time BEFORE start_time. Such moves are refused, not truncated."""
    event = _event(start=time(10, 0), end=time(11, 30))  # 90 minutes
    service, _, events_service = _service(event=event)

    result = await service.reschedule_item(
        "user_test", "event-event_1", datetime(2026, 8, 12, 23, 30)
    )

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.VALIDATION
    events_service.update_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_task_read_propagates_not_404() -> None:
    """A transient read failure is not a missing item — the caller must see
    a retryable failure, never a false 'not found'."""
    service, tasks_service, _ = _service()
    tasks_service.get = AsyncMock(return_value=Result.fail(Errors.database("tasks.get", "boom")))
    tasks_service.update_task = AsyncMock()

    result = await service.reschedule_item("user_test", "task-task_1", datetime(2026, 8, 20, 0, 0))

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.DATABASE
    tasks_service.update_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_event_read_propagates_not_404() -> None:
    service, _, events_service = _service()
    events_service.get = AsyncMock(return_value=Result.fail(Errors.database("events.get", "boom")))
    events_service.update_event = AsyncMock()

    result = await service.reschedule_item(
        "user_test", "event-event_1", datetime(2026, 8, 12, 14, 15)
    )

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.DATABASE
    events_service.update_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_item_propagates_failed_read() -> None:
    """Same class in the read path: get_item must not render a DB failure as
    the 'not found' modal state (Result.ok(None))."""
    service, tasks_service, _ = _service()
    tasks_service.get = AsyncMock(return_value=Result.fail(Errors.database("tasks.get", "boom")))

    result = await service.get_item("user_test", "task-task_1")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.DATABASE


def test_parse_calendar_item_uid_wire_format() -> None:
    """One parse of the '{kind}-{source_uid}' wire format for service + route."""
    assert parse_calendar_item_uid("task-task_1") == (EntityType.TASK, "task_1")
    assert parse_calendar_item_uid("event-event:abc") == (EntityType.EVENT, "event:abc")
    assert parse_calendar_item_uid("habit-habit_1") == (EntityType.HABIT, "habit_1")
    assert parse_calendar_item_uid("goal-goal_1") is None  # milestones land in PR 5
    assert parse_calendar_item_uid("garbage") is None


@pytest.mark.asyncio
async def test_habit_item_id_is_not_found() -> None:
    service, _, _ = _service()

    result = await service.reschedule_item(
        "user_test", "habit-habit_1", datetime(2026, 8, 20, 0, 0)
    )

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.NOT_FOUND
