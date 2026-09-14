"""``HabitEventScheduler`` persists through the Events entity door, never a backend.

``EventsCoreService.create`` is the one create path for Events: the duration
rule, the entity-carried REINFORCES_HABIT edge, ``CalendarEventCreated`` and the
ADR-074 embedding request all happen there. A scheduler handing a DTO to
``backend.create_event`` skipped every one of them — its events landed
unchecked, un-announced, un-embedded and unlinked. Pinned here with a fake
Events facade:

- every scheduled event reaches ``events_service.create`` as an ``Event``
  carrying the habit as ``reinforces_habit_uid`` — the edge's INPUT on create —
  so the primitive writes the edge, not the scheduler;
- the streak-maintenance door does the same;
- ``auto_create=False`` persists nothing;
- a refused create is skipped, the rest still land.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.models.enums import EntityStatus, RecurrencePattern
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.habit.habit import Habit
from core.services.habit_event_scheduler import EventSchedulingConfig, HabitEventScheduler
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

HABIT_UID = "habit_read_daily"
USER = "user_sched"


class _FakeEventsFacade:
    """Records what reaches the entity door; echoes the event back as persisted."""

    def __init__(self, *, refuse_after: int | None = None) -> None:
        self.created: list[Event] = []
        self.refuse_after = refuse_after
        self._seen = 0

    async def create(self, entity: Event) -> Result[Event]:
        self._seen += 1
        if self.refuse_after is not None and self._seen > self.refuse_after:
            return Result.fail(Errors.database("create", "refused by the fixture"))
        self.created.append(entity)
        return Result.ok(entity)


class _FakeHabitsBackend:
    def __init__(self, habit: Habit) -> None:
        self._habit = habit

    async def get_habit(self, habit_uid: str) -> Result[dict[str, Any]]:
        assert habit_uid == self._habit.uid
        return Result.ok(self._habit.to_dto().to_dict())


def _habit() -> Habit:
    return Habit(
        uid=HABIT_UID,
        user_uid=USER,
        title="Read daily",
        status=EntityStatus.ACTIVE,
        duration_minutes=30,
        recurrence_pattern=RecurrencePattern.DAILY,
    )


def _scheduler(facade: _FakeEventsFacade) -> HabitEventScheduler:
    return HabitEventScheduler(
        habits_backend=_FakeHabitsBackend(_habit()),  # type: ignore[arg-type]
        events_service=facade,  # type: ignore[arg-type]
        config=EventSchedulingConfig(schedule_ahead_days=3),
    )


@pytest.mark.asyncio
async def test_every_scheduled_event_reaches_the_entity_door_linked_to_its_habit() -> None:
    facade = _FakeEventsFacade()
    result = await _scheduler(facade).schedule_events_for_habit(
        HABIT_UID, UserContext(user_uid=USER), auto_create=True
    )

    assert result.is_ok
    assert facade.created, "nothing reached the entity door"
    assert all(isinstance(e, Event) for e in facade.created)
    assert all(e.reinforces_habit_uid == HABIT_UID for e in facade.created)
    assert [dto.uid for dto in result.value] == [e.uid for e in facade.created]
    assert all(isinstance(dto, EventDTO) for dto in result.value)


@pytest.mark.asyncio
async def test_streak_maintenance_reaches_the_entity_door_linked_to_its_habit() -> None:
    facade = _FakeEventsFacade()
    # ``at_risk_habits`` is a rich-context field; the scheduler reads it through
    # ``at_risk_habits_or_empty`` (standard depth → nothing to maintain).
    context = UserContext(user_uid=USER, habit_streaks={HABIT_UID: 3}, at_risk_habits=[HABIT_UID])
    result = await _scheduler(facade).schedule_streak_maintenance(context, auto_create=True)

    assert result.is_ok
    assert facade.created, "no maintenance event reached the entity door"
    maintenance = facade.created[0]
    assert maintenance.title.startswith("MAINTAIN STREAK")
    assert maintenance.reinforces_habit_uid == HABIT_UID


@pytest.mark.asyncio
async def test_templates_only_persist_nothing() -> None:
    facade = _FakeEventsFacade()
    result = await _scheduler(facade).schedule_events_for_habit(
        HABIT_UID, UserContext(user_uid=USER), auto_create=False
    )
    assert result.is_ok and result.value
    assert facade.created == []


@pytest.mark.asyncio
async def test_a_refused_create_is_skipped_and_the_rest_land() -> None:
    facade = _FakeEventsFacade(refuse_after=1)
    result = await _scheduler(facade).schedule_events_for_habit(
        HABIT_UID, UserContext(user_uid=USER), auto_create=True
    )
    assert result.is_ok
    assert len(result.value) == 1
    assert len(facade.created) == 1
