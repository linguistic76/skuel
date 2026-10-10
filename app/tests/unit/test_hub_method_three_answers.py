"""
Unit Tests — method 3: where this knowledge is applied, read from the context's links
=====================================================================================

``get_knowledge_application_opportunities`` answers with every activity the context
links to the Ku: the habits and events that apply it directly, the habits supporting
the goals that require it and the events reinforcing those habits, the pending choices
it informs, the active principles grounded in it. A choice already made, a principle
no longer held, a past event and an inactive habit are not opportunities.
"""

from unittest.mock import MagicMock, create_autospec

import pytest

from core.services.tasks_service import TasksService
from core.services.user.intelligence import (
    UserContextIntelligence,
    UserContextIntelligenceFactory,
)
from core.services.user.unified_user_context import RichUserContext
from core.utils.result_simplified import Errors, Result

pytestmark = pytest.mark.asyncio

KU = "ku.test.anchor"
OTHER = "ku.test.other"


def _hub(context: RichUserContext, tasks: Result[list] | None = None) -> UserContextIntelligence:
    """The real hub over ``context``; the one service read method 3 makes answers as given."""
    tasks_service = create_autospec(TasksService, instance=True)
    tasks_service.get_learning_tasks_for_user.return_value = tasks or Result.ok([])
    factory = UserContextIntelligenceFactory(
        tasks=tasks_service,
        goals=MagicMock(),
        habits=MagicMock(),
        events=MagicMock(),
        choices=MagicMock(),
        principles=MagicMock(),
        ps=MagicMock(),
        lp=MagicMock(),
        exercises=MagicMock(),
        report=MagicMock(),
        calendar=MagicMock(),
        vector_search_service=None,
        zpd_service=None,
    )
    return factory.create(context)


def _context() -> RichUserContext:
    context = RichUserContext(user_uid="user_test")
    context.active_goal_uids = ["goal.requires", "goal.other"]
    context.goal_knowledge_required = {"goal.requires": [KU], "goal.other": [OTHER]}
    context.active_habit_uids = ["habit.applies", "habit.supports", "habit.other"]
    context.habit_knowledge_applied = {"habit.applies": [KU], "habit.inactive": [KU]}
    context.habits_by_goal = {"goal.requires": ["habit.supports"], "goal.other": ["habit.other"]}
    context.upcoming_event_uids = ["event.applies", "event.reinforces", "event.other"]
    context.event_knowledge_applied = {"event.applies": [KU], "event.past": [KU]}
    context.events_by_habit = {
        "habit.supports": ["event.reinforces"],
        "habit.other": ["event.other"],
    }
    context.pending_choice_uids = ["choice.pending", "choice.other"]
    context.choice_knowledge_informed = {"choice.pending": [KU], "choice.made": [KU]}
    context.core_principle_uids = ["principle.held", "principle.other"]
    context.principle_knowledge_grounded = {"principle.held": [KU], "principle.archived": [KU]}
    return context


async def test_every_kind_is_answered_from_the_context_links() -> None:
    result = await _hub(_context()).get_knowledge_application_opportunities(KU)

    assert result.is_ok, result
    assert result.value == {
        "tasks": [],
        "goals": ["goal.requires"],
        "habits": ["habit.applies", "habit.supports"],
        "events": ["event.applies", "event.reinforces"],
        "choices": ["choice.pending"],
        "principles": ["principle.held"],
    }


async def test_a_ku_nothing_links_to_answers_empty() -> None:
    result = await _hub(_context()).get_knowledge_application_opportunities("ku.test.unlinked")

    assert result.is_ok, result
    assert all(uids == [] for uids in result.value.values())


async def test_a_failed_tasks_read_fails_the_answer() -> None:
    refused: Result[list] = Result.fail(Errors.database("read", "the graph is down"))

    result = await _hub(_context(), tasks=refused).get_knowledge_application_opportunities(KU)

    assert result.is_error
