"""
Unit Tests — method 3: where this knowledge is applied, read from the context's links
=====================================================================================

``get_knowledge_application_opportunities`` answers with every activity the context
links to the Ku: the active tasks applying it, the habits and events that apply it
directly, the habits supporting the goals that require it and the events reinforcing
those habits, the pending choices it informs, the active principles grounded in it. It
reads no service, so no read can fail into an empty answer. A choice already made, a
principle no longer held, an inactive habit or task, and an upcoming event that is
cancelled or already over are not opportunities.
"""

from datetime import date, datetime, time
from unittest.mock import MagicMock

import pytest
import time_machine

from core.ports.query_types import RichEntityItem
from core.services.user.intelligence import (
    UserContextIntelligence,
    UserContextIntelligenceFactory,
)
from core.services.user.unified_user_context import RichUserContext
from core.utils.zone_context import current_zone

pytestmark = pytest.mark.asyncio

DAY = date(2026, 10, 8)

KU = "ku.test.anchor"
OTHER = "ku.test.other"


def _hub(context: RichUserContext) -> UserContextIntelligence:
    """The real hub over ``context``; every service is a bare mock method 3 must not call."""
    factory = UserContextIntelligenceFactory(
        tasks=MagicMock(),
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


def _event(uid: str, status: str, end: time) -> RichEntityItem:
    return {
        "entity": {
            "uid": uid,
            "title": uid,
            "user_uid": "user_test",
            "status": status,
            "event_date": DAY.isoformat(),
            "start_time": "08:00:00",
            "end_time": end.isoformat(),
        },
        "graph_context": {},
    }


def _context() -> RichUserContext:
    context = RichUserContext(user_uid="user_test")
    context.active_task_uids = ["task.applies", "task.other"]
    context.task_knowledge_applied = {"task.applies": [KU], "task.completed": [KU]}
    context.active_goal_uids = ["goal.requires", "goal.other"]
    context.goal_knowledge_required = {"goal.requires": [KU], "goal.other": [OTHER]}
    context.active_habit_uids = ["habit.applies", "habit.supports", "habit.other"]
    context.habit_knowledge_applied = {"habit.applies": [KU], "habit.inactive": [KU]}
    context.habits_by_goal = {"goal.requires": ["habit.supports"], "goal.other": ["habit.other"]}
    context.upcoming_event_uids = [
        "event.applies",
        "event.reinforces",
        "event.other",
        "event.cancelled",
        "event.over",
    ]
    context.event_knowledge_applied = {
        "event.applies": [KU],
        "event.past": [KU],
        "event.cancelled": [KU],
        "event.over": [KU],
    }
    context.entities_rich = {
        "events": [
            _event("event.applies", "scheduled", time(18, 0)),
            _event("event.cancelled", "cancelled", time(18, 0)),
            _event("event.over", "scheduled", time(9, 0)),
        ]
    }
    context.events_by_habit = {
        "habit.supports": ["event.reinforces"],
        "habit.other": ["event.other"],
    }
    context.pending_choice_uids = ["choice.pending", "choice.other"]
    context.choice_knowledge_informed = {"choice.pending": [KU], "choice.made": [KU]}
    context.core_principle_uids = ["principle.held", "principle.other"]
    context.principle_knowledge_grounded = {"principle.held": [KU], "principle.archived": [KU]}
    return context


def _at_noon() -> time_machine.travel:
    instant = datetime.combine(DAY, time(12, 0), tzinfo=current_zone())
    return time_machine.travel(instant.timestamp(), tick=False)


async def test_every_kind_is_answered_from_the_context_links() -> None:
    with _at_noon():
        result = await _hub(_context()).get_knowledge_application_opportunities(KU)

    assert result.is_ok, result
    assert result.value == {
        "tasks": ["task.applies"],
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


async def test_no_service_is_asked() -> None:
    hub = _hub(_context())

    with _at_noon():
        await hub.get_knowledge_application_opportunities(KU)

    assert hub.tasks.mock_calls == []
