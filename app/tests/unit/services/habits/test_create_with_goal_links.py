"""A habit created with goal links says which link was refused.

``create_with_goal_links`` creates the habit, then links it to each goal named.
The link door answers a ``Result``; a refused link is logged with the goal it
named, the other links are still attempted, and the created habit is returned.
"""

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from core.models.enums.goal_enums import HabitEssentiality
from core.models.type_hints import UserUID
from core.services.habits._orchestration_mixin import _OrchestrationMixin
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.habit.habit_request import HabitCreateRequest
    from core.services.goals_service import GoalsService

HABIT_UID = "habit_0123456789abcdef"
OWN_GOAL = "goal_aaaaaaaaaaaaaaaa"
FOREIGN_GOAL = "goal_bbbbbbbbbbbbbbbb"
# The fake core ignores the request, so an empty stand-in is enough.
_REQUEST = cast("HabitCreateRequest", SimpleNamespace())


class _Core:
    async def create_habit(self, _request: object, _user_uid: UserUID) -> Result[SimpleNamespace]:
        return Result.ok(SimpleNamespace(uid=HABIT_UID))


class _Goals:
    """Stands in for the goals facade's link door: refuses one goal, links the rest."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str, HabitEssentiality]] = []

    async def link_goal_to_habit(
        self, goal_uid: str, habit_uid: str, essentiality: HabitEssentiality
    ) -> Result[bool]:
        self.asked.append((goal_uid, habit_uid, essentiality))
        if goal_uid == FOREIGN_GOAL:
            return Result.fail(Errors.not_found("Habit", habit_uid))
        return Result.ok(True)


def _host(goals: _Goals) -> _OrchestrationMixin:
    host = _OrchestrationMixin()
    host.core = _Core()
    host.goals_service = cast("GoalsService", goals)
    host.logger = logging.getLogger("test.habits.create_with_goal_links")
    return host


@pytest.mark.asyncio
async def test_a_refused_link_is_logged_and_the_rest_are_still_attempted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    goals = _Goals()
    with caplog.at_level(logging.WARNING, logger="test.habits.create_with_goal_links"):
        result = await _host(goals).create_with_goal_links(
            _REQUEST,
            UserUID("user_0123456789abcdef"),
            {
                FOREIGN_GOAL: HabitEssentiality.ESSENTIAL,
                OWN_GOAL: HabitEssentiality.SUPPORTING,
            },
        )

    assert result.is_ok
    assert result.value.uid == HABIT_UID
    assert [goal for goal, _habit, _tier in goals.asked] == [FOREIGN_GOAL, OWN_GOAL]
    refused = [record.getMessage() for record in caplog.records]
    assert len(refused) == 1
    assert FOREIGN_GOAL in refused[0]
    assert OWN_GOAL not in refused[0]


@pytest.mark.asyncio
async def test_links_that_land_log_nothing(caplog: pytest.LogCaptureFixture) -> None:
    goals = _Goals()
    with caplog.at_level(logging.WARNING, logger="test.habits.create_with_goal_links"):
        result = await _host(goals).create_with_goal_links(
            _REQUEST,
            UserUID("user_0123456789abcdef"),
            {OWN_GOAL: HabitEssentiality.SUPPORTING},
        )

    assert result.is_ok
    assert caplog.records == []
