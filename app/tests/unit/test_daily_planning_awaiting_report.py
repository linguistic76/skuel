"""
Unit Tests — Daily Planning: Priority 2.7, entries awaiting a report
====================================================================

The daily plan names the turn-ins that are out of the user's hands: entries
on a pipeline that ``awaits_report`` (teacher review) with no ``REPORT_FOR``
yet, read through ``ReportRelationshipService.get_pending_submissions`` with
``Pipeline.awaiting_report()`` as the filter. The slot costs no minutes, is
not capacity-checked, and is stated once in the rationale.
``UserContextService.get_next_action`` carries the list through.

The plan under test is assembled by the real ``DailyPlanningMixin`` over the
no-op domain services of ``test_daily_planning_domain_stats``.
"""

from typing import cast
from unittest.mock import AsyncMock

import pytest

from core.models.context_types import DailyWorkPlan
from core.models.enums.pipeline import Pipeline
from core.services.user.user_context_builder import UserContextBuilder
from core.services.user.user_context_service import UserContextService
from core.services.user_service import UserService
from core.utils.result_simplified import Errors, Result
from tests.unit.test_daily_planning_domain_stats import (
    MockDailyPlanningService,
    make_context,
)

AWAITING = ["ue_turn_in_newest", "ue_turn_in_older"]


def _planner(awaiting: list[str], available_minutes: int = 480) -> MockDailyPlanningService:
    service = MockDailyPlanningService(context=make_context(available_minutes=available_minutes))
    service.report.get_pending_submissions = AsyncMock(return_value=Result.ok(list(awaiting)))
    return service


class _PlanSource:
    def __init__(self, planner: MockDailyPlanningService) -> None:
        self._planner = planner

    async def get_daily_work_plan(self, user_uid: str) -> Result[DailyWorkPlan]:
        return await self._planner.get_ready_to_work_on_today()


# =============================================================================
# The pipeline rule
# =============================================================================


def test_only_a_teacher_review_entry_awaits_a_report() -> None:
    assert Pipeline.awaiting_report() == [Pipeline.TEACHER_REVIEW]
    assert Pipeline.TEACHER_REVIEW.awaits_report() is True
    # the journal pipelines: the owner asks for the response, nobody owes one
    assert Pipeline.EXTRACT_ACTIVITIES.awaits_report() is False
    assert Pipeline.TRANSCRIBE_AND_STRUCTURE.awaits_report() is False
    assert Pipeline.NONE.awaits_report() is False


# =============================================================================
# The slot
# =============================================================================


@pytest.mark.asyncio
async def test_the_plan_names_the_entries_awaiting_a_report_in_the_order_read() -> None:
    planner = _planner(AWAITING)

    result = await planner.get_ready_to_work_on_today()

    assert result.is_ok, result
    assert result.value.awaiting_report == tuple(AWAITING)
    read = cast("AsyncMock", planner.report.get_pending_submissions)
    read.assert_awaited_once_with("user_test", pipelines=[Pipeline.TEACHER_REVIEW])


@pytest.mark.asyncio
async def test_the_slot_costs_no_minutes_and_ignores_capacity() -> None:
    """A user with no minutes today still sees what is out of their hands."""
    result = await _planner(AWAITING, available_minutes=0).get_ready_to_work_on_today(
        respect_capacity=True
    )

    plan = result.value
    assert plan.awaiting_report == tuple(AWAITING)
    assert plan.estimated_time_minutes == 0
    assert plan.fits_capacity is True


@pytest.mark.asyncio
async def test_the_rationale_counts_the_entries_once() -> None:
    plan = (await _planner(AWAITING).get_ready_to_work_on_today()).value
    assert "2 entries awaiting a report" in plan.rationale.split("; ")

    plan = (await _planner(AWAITING[:1]).get_ready_to_work_on_today()).value
    assert "1 entry awaiting a report" in plan.rationale.split("; ")


@pytest.mark.asyncio
async def test_nothing_awaiting_leaves_the_slot_and_the_rationale_silent() -> None:
    plan = (await _planner([]).get_ready_to_work_on_today()).value

    assert plan.awaiting_report == ()
    assert "awaiting a report" not in plan.rationale


@pytest.mark.asyncio
async def test_a_failed_read_leaves_the_slot_empty_and_the_plan_whole() -> None:
    planner = _planner([])
    planner.report.get_pending_submissions = AsyncMock(
        return_value=Result.fail(Errors.database(operation="pending", message="graph down"))
    )

    result = await planner.get_ready_to_work_on_today()

    assert result.is_ok, result
    assert result.value.awaiting_report == ()


# =============================================================================
# get_next_action carries the slot
# =============================================================================


@pytest.mark.asyncio
async def test_next_action_carries_the_entries_awaiting_a_report() -> None:
    service = UserContextService(
        context_builder=cast("UserContextBuilder", object()),
        user_service=cast("UserService", _PlanSource(_planner(AWAITING))),
    )

    result = await service.get_next_action("user_test")

    assert result.is_ok, result
    assert result.value["awaiting_report"] == AWAITING
