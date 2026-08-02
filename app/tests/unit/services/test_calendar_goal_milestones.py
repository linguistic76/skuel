"""Unit tests for goals as calendar Milestones (act-from arc C5).

Truthful legend: every legend entry has a producer. Goals with a target date
surface as all-day purple Milestone chips (``_fetch_goals`` →
``_goal_to_calendar_item``), and ``get_item`` resolves the ``goal-`` wire
prefix owner-scoped — non-owner and unknown ids surface as not-found, a
failed read propagates instead of masquerading as missing.

The goal paths touch only the injected goals service, so we build the
CalendarService with mocks and drive it directly.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.event.calendar_models import CalendarItemType, CalendarView
from core.models.goal.goal import Goal
from core.services.calendar_service import CalendarService
from core.utils.result_simplified import ErrorCategory, Errors, Result


def _goal(
    *,
    uid: str = "goal_1",
    user_uid: str = "user_test",
    target: date | None = date(2026, 8, 21),
) -> Goal:
    created = datetime(2026, 7, 1, 8, 0)
    return Goal(
        uid=uid,
        user_uid=user_uid,
        title="Focus on Van",
        entity_type=EntityType.GOAL,
        status=EntityStatus.ACTIVE,
        created_at=created,
        updated_at=created,
        target_date=target,
    )


def _service(goal: Goal | None = None) -> tuple[CalendarService, Mock]:
    goals_service = Mock()
    if goal is not None:
        goals_service.get = AsyncMock(return_value=Result.ok(goal))
        goals_service.get_user_items_in_range = AsyncMock(return_value=Result.ok([goal]))
    service = CalendarService(
        tasks_service=Mock(),
        events_service=Mock(),
        habits_service=Mock(),
        goals_service=goals_service,
    )
    return service, goals_service


# ---------------------------------------------------------------------------
# _goal_to_calendar_item — the one MILESTONE producer
# ---------------------------------------------------------------------------


def test_goal_converts_to_all_day_milestone_on_target_date() -> None:
    service, _ = _service()

    item = service._goal_to_calendar_item(_goal())

    assert item.item_type == CalendarItemType.MILESTONE
    assert item.uid == "goal-goal_1"
    assert item.source_uid == "goal_1"
    assert item.all_day is True
    assert item.start_time.date() == date(2026, 8, 21)
    assert item.end_time.date() == date(2026, 8, 21)
    assert item.color == "#9333ea"  # the legend's Milestone swatch
    assert item.icon == "🎯"


def test_dateless_goal_still_converts_without_raising() -> None:
    """A hand-crafted get_item for a goal with no target date must not crash
    the modal — the converter falls back like the task converter does."""
    service, _ = _service()

    item = service._goal_to_calendar_item(_goal(target=None))

    assert item.item_type == CalendarItemType.MILESTONE
    assert item.uid == "goal-goal_1"


# ---------------------------------------------------------------------------
# _fetch_goals — in the view pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_goals_uses_the_plain_range_fetch() -> None:
    """Goals DomainConfig already places by target_date — no date_field
    override (the calendar-only OR-of-fields trick is a Tasks concern)."""
    goal = _goal()
    service, goals_service = _service(goal)

    items = await service._fetch_goals(
        "user_test", date(2026, 8, 1), date(2026, 8, 31), include_completed=False
    )

    goals_service.get_user_items_in_range.assert_awaited_once_with(
        user_uid="user_test",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        include_completed=False,
    )
    assert len(items) == 1
    assert items[0].item_type == CalendarItemType.MILESTONE


@pytest.mark.asyncio
async def test_get_calendar_view_includes_milestones() -> None:
    """End-to-end through get_calendar_view: the goal fetch feeds the same
    item list as tasks and events."""
    goal = _goal()
    service, _ = _service(goal)
    service.tasks_service.get_user_items_in_range = AsyncMock(return_value=Result.ok([]))
    service.events_service.get_user_items_in_range = AsyncMock(return_value=Result.ok([]))
    service.habits_service.get_active = AsyncMock(return_value=Result.ok([]))

    result = await service.get_calendar_view(
        "user_test", date(2026, 8, 1), date(2026, 8, 31), CalendarView.MONTH
    )

    assert result.is_ok
    milestones = [i for i in result.value.items if i.item_type == CalendarItemType.MILESTONE]
    assert [m.uid for m in milestones] == ["goal-goal_1"]


# ---------------------------------------------------------------------------
# get_item — owner-scoped 'goal-' resolution (the #911 Codex gotcha)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_item_resolves_owned_goal() -> None:
    service, _ = _service(_goal())

    result = await service.get_item("user_test", "goal-goal_1")

    assert result.is_ok
    assert result.value is not None
    assert result.value.item_type == CalendarItemType.MILESTONE
    assert result.value.title == "Focus on Van"


@pytest.mark.asyncio
async def test_get_item_non_owner_goal_is_not_found() -> None:
    """Same pattern as task/event/habit: another user's goal reads as
    missing — no UID oracle."""
    service, _ = _service(_goal(user_uid="user_other"))

    result = await service.get_item("user_test", "goal-goal_1")

    assert result.is_ok
    assert result.value is None


@pytest.mark.asyncio
async def test_get_item_unknown_prefix_is_not_found() -> None:
    service, _ = _service()

    result = await service.get_item("user_test", "milestone-goal_1")

    assert result.is_ok
    assert result.value is None


@pytest.mark.asyncio
async def test_get_item_propagates_failed_goal_read() -> None:
    """A transient read failure is not a missing item — the caller must see
    a retryable failure, never the 'not found' modal state."""
    service, goals_service = _service()
    goals_service.get = AsyncMock(return_value=Result.fail(Errors.database("goals.get", "boom")))

    result = await service.get_item("user_test", "goal-goal_1")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.DATABASE
