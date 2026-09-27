"""Goal events measure elapsed days between two aware instants.

``GoalAchieved.actual_duration_days`` and ``GoalAbandoned.days_active`` are
``now - goal.created_at``. A goal's ``created_at`` is aware whenever its stored
value carries an offset — an authored ``…Z`` stamp (``goal.self-reflection-beginner``)
or any native — and ``naive datetime.now() - aware`` raises ``TypeError`` after the
write, so the completion or the delete landed and its event never did. Both sides
now go through ``as_utc``: the three publishers are pinned here with an aware
``created_at``, and with a naive one under a zone west of UTC, where the naive stamp
must still be read as local time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.events.base import BaseEvent
from core.events.goal_events import GoalAbandoned, GoalAchieved
from core.models.enums import EntityStatus
from core.models.goal.goal import Goal
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.services.goals.goals_core_service import GoalsCoreService
from core.utils.result_simplified import Result
from tests.helpers.forced_zone import forced_zone
from tests.helpers.status_guarded_backend import guarded_backend

USER = "user_goal_durations"
GOAL = "goal_durations"
DAYS_AGO = 12


class _RecordingBus:
    """Captures published events; ``publish_async`` is the whole contract."""

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


def _goal(created_at: datetime, status: EntityStatus = EntityStatus.ACTIVE) -> Goal:
    return Goal(
        uid=GOAL, user_uid=USER, title="Finish the course", status=status, created_at=created_at
    )


def _aware_created_at() -> datetime:
    """An authored-shape stamp: an offset string read back through the real mapper."""
    stored = to_neo4j_node(_goal(datetime.now(UTC) - timedelta(days=DAYS_AGO)))
    created_at = from_neo4j_node(stored, Goal).created_at
    assert created_at is not None and created_at.tzinfo is not None  # the premise
    return created_at


def _completing_service(created_at: datetime) -> tuple[GoalsCoreService, _RecordingBus]:
    backend, _recorder = guarded_backend(
        _goal(created_at), _goal(created_at, status=EntityStatus.COMPLETED)
    )
    bus = _RecordingBus()
    return GoalsCoreService(backend=backend, event_bus=bus), bus


def _deleting_service(created_at: datetime) -> tuple[GoalsCoreService, _RecordingBus]:
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(_goal(created_at)))
    backend.delete = AsyncMock(return_value=Result.ok(True))
    bus = _RecordingBus()
    return GoalsCoreService(backend=backend, event_bus=bus), bus


class _RoundTripBackend:
    """``create`` round-trips through the real mapper, as ``_create_node`` does."""

    async def create(self, entity: Goal) -> Result[Any]:
        return Result.ok(from_neo4j_node(to_neo4j_node(entity), Goal))

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"Unmodelled backend call: {name}")


@pytest.mark.asyncio
class TestGoalAchievedDuration:
    async def test_completing_a_goal_with_an_aware_created_at_announces_it(self) -> None:
        service, bus = _completing_service(_aware_created_at())

        result = await service.update_goal(
            GOAL, GoalUpdateIntent(status=EntityStatus.COMPLETED.value)
        )

        assert result.is_ok, result
        achieved = bus.of(GoalAchieved)
        assert len(achieved) == 1
        assert achieved[0].actual_duration_days == DAYS_AGO

    async def test_a_naive_created_at_is_read_in_the_process_zone(self) -> None:
        with forced_zone("America/Vancouver"):
            service, bus = _completing_service(datetime.now() - timedelta(days=DAYS_AGO))
            result = await service.update_goal(
                GOAL, GoalUpdateIntent(status=EntityStatus.COMPLETED.value)
            )

        assert result.is_ok, result
        assert bus.of(GoalAchieved)[0].actual_duration_days == DAYS_AGO

    async def test_a_goal_born_achieved_with_an_aware_created_at_announces_it(self) -> None:
        bus = _RecordingBus()
        service = GoalsCoreService(backend=_RoundTripBackend(), event_bus=bus)
        goal = Goal(
            uid=GOAL,
            user_uid=USER,
            title="Shipped",
            status=EntityStatus.COMPLETED,
            achieved_date=date(2026, 3, 4),
            created_at=_aware_created_at(),
        )

        result = await service.create(goal)

        assert result.is_ok, result
        achieved = bus.of(GoalAchieved)
        assert len(achieved) == 1
        assert achieved[0].actual_duration_days == DAYS_AGO


@pytest.mark.asyncio
class TestGoalAbandonedDaysActive:
    async def test_deleting_a_goal_with_an_aware_created_at_announces_it(self) -> None:
        service, bus = _deleting_service(_aware_created_at())

        result = await service.delete(GOAL)

        assert result.is_ok, result
        abandoned = bus.of(GoalAbandoned)
        assert len(abandoned) == 1
        assert abandoned[0].days_active == DAYS_AGO

    async def test_a_naive_created_at_is_read_in_the_process_zone(self) -> None:
        with forced_zone("America/Vancouver"):
            service, bus = _deleting_service(datetime.now() - timedelta(days=DAYS_AGO))
            result = await service.delete(GOAL)

        assert result.is_ok, result
        assert bus.of(GoalAbandoned)[0].days_active == DAYS_AGO
