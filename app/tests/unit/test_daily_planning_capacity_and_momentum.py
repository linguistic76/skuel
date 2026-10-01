"""
Unit Tests — Daily Planning: capacity verdict and the habit-consistency signal
==============================================================================

Two statements the daily plan makes about a user, each held to what was measured:

- ``DailyWorkPlan.fits_capacity`` compares the plan's estimated minutes with the
  user's available minutes. Habits and events are planned whatever the capacity,
  so a plan can exceed it; ``workload_utilization`` is the ratio held to 0.0-1.0.
  ``UserContextService.get_next_action`` reports an over-capacity plan as one
  ``capacity_warning`` alert and leaves the plan's warnings their own type.
- ``habit_consistency`` in the momentum signals is the mean of the rates the
  habit items carry, and ``None`` when no item carries one. The low-consistency
  warning needs a value.

The plan under test is assembled by the real ``DailyPlanningMixin`` over the
no-op domain services of ``test_daily_planning_domain_stats``.
"""

from typing import cast
from unittest.mock import AsyncMock

import pytest

from core.models.context_types import ContextualHabit, DailyWorkPlan
from core.models.enums.entity_enums import EntityStatus
from core.ports.query_types import RichEntityItem
from core.services.user.user_context_builder import UserContextBuilder
from core.services.user.user_context_service import UserContextService
from core.services.user_service import UserService
from core.utils.result_simplified import Result
from tests.unit.test_daily_planning_domain_stats import (
    MockDailyPlanningService,
    make_context,
)

LOW_CONSISTENCY = "Habit consistency is low — rebuilding streaks is today's priority"


def _at_risk_habits(count: int) -> list[ContextualHabit]:
    return [ContextualHabit(uid=f"habit_{n}", title=f"Habit {n}") for n in range(count)]


def _planner(available_minutes: int, at_risk_habits: int = 0) -> MockDailyPlanningService:
    """A planner whose only planned work is ``at_risk_habits`` habits (15 minutes each)."""
    service = MockDailyPlanningService(context=make_context(available_minutes=available_minutes))
    service.habits.get_at_risk_habits_for_user = AsyncMock(
        return_value=Result.ok(_at_risk_habits(at_risk_habits))
    )
    return service


class _PlanSource:
    """Stands in for ``UserService``: answers ``get_daily_work_plan`` from a planner."""

    def __init__(self, planner: MockDailyPlanningService) -> None:
        self._planner = planner

    async def get_daily_work_plan(self, user_uid: str) -> Result[DailyWorkPlan]:
        return await self._planner.get_ready_to_work_on_today()


def _context_service(planner: MockDailyPlanningService) -> UserContextService:
    return UserContextService(
        context_builder=cast("UserContextBuilder", object()),
        user_service=cast("UserService", _PlanSource(planner)),
    )


def _habit_item(completion_rate: float | None) -> RichEntityItem:
    entity: dict[str, object] = {"uid": "habit_x", "status": EntityStatus.ACTIVE.value}
    if completion_rate is not None:
        entity["completion_rate"] = completion_rate
    return {"entity": entity, "graph_context": {}}


def _momentum_planner(habits: list[RichEntityItem]) -> MockDailyPlanningService:
    """A planner whose window holds one task and the given habit items."""
    context = make_context()
    context.entities_rich = {
        "tasks": [{"entity": {"uid": "task_x", "status": EntityStatus.ACTIVE.value}}],
        "habits": habits,
    }
    return MockDailyPlanningService(context=context)


# =============================================================================
# fits_capacity / workload_utilization
# =============================================================================


@pytest.mark.asyncio
async def test_plan_needing_more_minutes_than_available_does_not_fit() -> None:
    """45 planned minutes against 10 available: the plan does not fit."""
    result = await _planner(available_minutes=10, at_risk_habits=3).get_ready_to_work_on_today()

    assert result.is_ok
    plan = result.value
    assert plan.estimated_time_minutes == 45
    assert plan.fits_capacity is False
    assert plan.workload_utilization == 1.0


@pytest.mark.asyncio
async def test_plan_within_available_minutes_fits() -> None:
    result = await _planner(available_minutes=480, at_risk_habits=3).get_ready_to_work_on_today()

    plan = result.value
    assert plan.estimated_time_minutes == 45
    assert plan.fits_capacity is True
    assert plan.workload_utilization == pytest.approx(45 / 480)


@pytest.mark.asyncio
async def test_plan_using_exactly_the_available_minutes_fits() -> None:
    result = await _planner(available_minutes=45, at_risk_habits=3).get_ready_to_work_on_today()

    plan = result.value
    assert plan.fits_capacity is True
    assert plan.workload_utilization == 1.0


@pytest.mark.asyncio
async def test_empty_plan_fits_a_user_with_no_available_minutes() -> None:
    result = await _planner(available_minutes=0).get_ready_to_work_on_today()

    plan = result.value
    assert plan.estimated_time_minutes == 0
    assert plan.fits_capacity is True
    assert plan.workload_utilization == 0.0


@pytest.mark.asyncio
async def test_any_planned_minute_exceeds_zero_available_minutes() -> None:
    result = await _planner(available_minutes=0, at_risk_habits=1).get_ready_to_work_on_today()

    plan = result.value
    assert plan.fits_capacity is False
    assert plan.workload_utilization == 1.0


# =============================================================================
# get_next_action — the capacity alert
# =============================================================================


@pytest.mark.asyncio
async def test_next_action_reports_an_over_capacity_plan_as_one_high_alert() -> None:
    service = _context_service(_planner(available_minutes=10, at_risk_habits=3))

    result = await service.get_next_action("user_test")

    assert result.is_ok
    alerts = result.value["alerts"]
    capacity_alerts = [a for a in alerts if a["type"] == "capacity_warning"]
    assert capacity_alerts == [
        {
            "type": "capacity_warning",
            "severity": "high",
            "message": "Today's plan needs 45 minutes — more than the time available",
            "item_count": 0,
        }
    ]
    assert alerts[0] == capacity_alerts[0]
    assert result.value["insights"]["capacity_utilization"] == 1.0


@pytest.mark.asyncio
async def test_next_action_keeps_plan_warnings_their_own_type_when_over_capacity() -> None:
    """A warning about something other than capacity is not relabelled by it."""
    service = _context_service(_planner(available_minutes=10, at_risk_habits=3))

    result = await service.get_next_action("user_test")

    plan_alerts = [a for a in result.value["alerts"] if a["type"] != "capacity_warning"]
    assert plan_alerts, "the over-capacity plan carries its 'very full schedule' warning"
    assert {(a["type"], a["severity"]) for a in plan_alerts} == {("plan_warning", "medium")}
    assert "Very full schedule - consider reducing if feeling overwhelmed" in [
        a["message"] for a in plan_alerts
    ]


@pytest.mark.asyncio
async def test_next_action_for_a_plan_that_fits_has_no_capacity_alert() -> None:
    planner = _planner(available_minutes=46, at_risk_habits=3)
    service = _context_service(planner)

    result = await service.get_next_action("user_test")

    alerts = result.value["alerts"]
    assert alerts, "a plan at 45 of 46 minutes carries its 'very full schedule' warning"
    assert {(a["type"], a["severity"]) for a in alerts} == {("plan_warning", "medium")}
    assert result.value["insights"]["capacity_utilization"] == pytest.approx(45 / 46)


# =============================================================================
# habit_consistency — None is "nothing measured", not "zero"
# =============================================================================


def test_no_habits_in_the_window_is_no_consistency_signal() -> None:
    planner = _momentum_planner(habits=[])

    signals = planner.compute_momentum_signals()

    assert signals["habit_consistency"] is None
    assert "habits" in signals["neglected"]
    assert LOW_CONSISTENCY not in planner._momentum_warnings(signals)


def test_unpopulated_window_is_no_consistency_signal() -> None:
    planner = MockDailyPlanningService(context=make_context())

    signals = planner.compute_momentum_signals()

    assert signals == {
        "velocities": {},
        "neglected": [],
        "habit_consistency": None,
        "phase": "unknown",
    }
    assert planner._momentum_warnings(signals) == []


def test_habits_carrying_no_rate_are_no_consistency_signal() -> None:
    planner = _momentum_planner(habits=[_habit_item(None), _habit_item(None)])

    signals = planner.compute_momentum_signals()

    assert signals["habit_consistency"] is None
    assert LOW_CONSISTENCY not in planner._momentum_warnings(signals)


def test_low_mean_rate_warns() -> None:
    planner = _momentum_planner(habits=[_habit_item(0.1), _habit_item(0.3)])

    signals = planner.compute_momentum_signals()

    assert signals["habit_consistency"] == pytest.approx(0.2)
    assert LOW_CONSISTENCY in planner._momentum_warnings(signals)


def test_a_measured_zero_rate_warns() -> None:
    planner = _momentum_planner(habits=[_habit_item(0.0)])

    signals = planner.compute_momentum_signals()

    assert signals["habit_consistency"] == 0.0
    assert LOW_CONSISTENCY in planner._momentum_warnings(signals)


def test_mean_rate_skips_the_habits_that_carry_none() -> None:
    planner = _momentum_planner(habits=[_habit_item(0.2), _habit_item(None)])

    assert planner.compute_momentum_signals()["habit_consistency"] == pytest.approx(0.2)


@pytest.mark.parametrize("rates", [(0.4,), (0.4, 0.9), (1.0,)])
def test_mean_rate_at_or_above_the_threshold_does_not_warn(rates: tuple[float, ...]) -> None:
    planner = _momentum_planner(habits=[_habit_item(rate) for rate in rates])

    signals = planner.compute_momentum_signals()

    assert LOW_CONSISTENCY not in planner._momentum_warnings(signals)


@pytest.mark.asyncio
async def test_daily_plan_for_a_user_with_no_habits_has_no_consistency_warning() -> None:
    result = await _momentum_planner(habits=[]).get_ready_to_work_on_today()

    assert result.is_ok
    assert LOW_CONSISTENCY not in result.value.warnings


@pytest.mark.asyncio
async def test_daily_plan_for_an_unpopulated_window_has_no_consistency_warning() -> None:
    planner = MockDailyPlanningService(context=make_context())

    result = await planner.get_ready_to_work_on_today()

    assert result.is_ok
    assert LOW_CONSISTENCY not in result.value.warnings


@pytest.mark.asyncio
async def test_daily_plan_carries_the_consistency_warning_for_low_rates() -> None:
    result = await _momentum_planner(habits=[_habit_item(0.2)]).get_ready_to_work_on_today()

    assert result.is_ok
    assert LOW_CONSISTENCY in result.value.warnings
