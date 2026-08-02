"""Unit tests for the calendar's due-OR-scheduled task fetch (act-from arc C2).

Defect: tasks were fetched with the DomainConfig ``due_date`` field only, yet
``_task_to_calendar_item`` renders ``scheduled_date``-first as a TASK_WORK chip
— so a scheduled-only task (no due_date) could never be fetched, and therefore
never render. The fix threads an OR-of-date-fields override through the range
seam; the calendar asks Tasks for ``["due_date", "scheduled_date"]``.

``_fetch_tasks`` touches only the injected tasks service, so we build the
CalendarService with mocks and drive it directly.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.event.calendar_models import CalendarItemType
from core.models.task.task import Task
from core.services.calendar_service import CalendarService
from core.utils.result_simplified import Result


def _task(
    *,
    uid: str,
    due: date | None = None,
    scheduled: date | None = None,
) -> Task:
    created = datetime(2026, 7, 1, 8, 0)
    return Task(
        uid=uid,
        user_uid="user_test",
        title=f"Task {uid}",
        entity_type=EntityType.TASK,
        status=EntityStatus.ACTIVE,
        created_at=created,
        updated_at=created,
        due_date=due,
        scheduled_date=scheduled,
    )


def _calendar_with_tasks(tasks: list[Task]) -> tuple[CalendarService, Mock]:
    tasks_service = Mock()
    tasks_service.get_user_items_in_range = AsyncMock(return_value=Result.ok(tasks))
    service = CalendarService(
        tasks_service=tasks_service,
        events_service=Mock(),
        habits_service=Mock(),
    )
    return service, tasks_service


@pytest.mark.asyncio
async def test_fetch_tasks_requests_due_or_scheduled() -> None:
    """The calendar fetch overrides the Tasks date field with BOTH date fields."""
    service, tasks_service = _calendar_with_tasks([])

    await service._fetch_tasks(
        "user_test", date(2026, 8, 1), date(2026, 8, 31), include_completed=False
    )

    tasks_service.get_user_items_in_range.assert_awaited_once_with(
        user_uid="user_test",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        include_completed=False,
        date_field=["due_date", "scheduled_date"],
    )


@pytest.mark.asyncio
async def test_scheduled_only_task_renders_as_work_chip() -> None:
    """A scheduled-only task (no due_date) surfaces as a 9am TASK_WORK chip."""
    scheduled_only = _task(uid="task_sched", scheduled=date(2026, 8, 12))
    service, _ = _calendar_with_tasks([scheduled_only])

    items = await service._fetch_tasks(
        "user_test", date(2026, 8, 1), date(2026, 8, 31), include_completed=False
    )

    assert len(items) == 1
    item = items[0]
    assert item.item_type == CalendarItemType.TASK_WORK
    assert item.all_day is False
    assert item.start_time == datetime(2026, 8, 12, 9, 0)


@pytest.mark.asyncio
async def test_due_only_task_still_renders_as_deadline_chip() -> None:
    """A due-only task keeps its all-day TASK_DEADLINE placement (unchanged by C2)."""
    due_only = _task(uid="task_due", due=date(2026, 8, 20))
    service, _ = _calendar_with_tasks([due_only])

    items = await service._fetch_tasks(
        "user_test", date(2026, 8, 1), date(2026, 8, 31), include_completed=False
    )

    assert len(items) == 1
    item = items[0]
    assert item.item_type == CalendarItemType.TASK_DEADLINE
    assert item.all_day is True
    assert item.start_time.date() == date(2026, 8, 20)
