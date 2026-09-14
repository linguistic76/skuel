"""
EntityExtractor matches a question against the rich context, in memory.

Every candidate title comes from ``RichUserContext.entities_rich`` (the six
activity domains) and ``knowledge_units_rich`` (every MASTERED | IN_PROGRESS
target, Ku or PathStep); the extractor holds no service handle and makes no
graph read per question. Each domain is scoped to the uids the standard
context marks live, and every match carries the node's ``entity_type``.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.models.type_hints import UserUID
from core.ports.query_types import RichEntityItem
from core.services.askesis.entity_extractor import EntityExtractor
from core.services.user.unified_user_context import RichUserContext


def _item(uid: str, title: str, entity_type: str, **props: Any) -> RichEntityItem:
    """A rich activity item, in the ``{"entity": …, "graph_context": …}`` shape."""
    return {
        "entity": {"uid": uid, "title": title, "entity_type": entity_type, **props},
        "graph_context": {},
    }


@pytest.fixture
def context() -> RichUserContext:
    """A learner engaged with two Kus and one PathStep, with live activities in every domain."""
    ctx = RichUserContext(user_uid=UserUID("user_test"))
    ctx.mastered_knowledge_uids = {"ku.python-basics"}
    ctx.in_progress_knowledge_uids = {"ku.machine-learning", "ps.data-pipelines"}
    ctx.knowledge_units_rich = {
        "ku.python-basics": {
            "ku": {"uid": "ku.python-basics", "title": "Python Basics", "entity_type": "ku"},
            "graph_context": {},
        },
        "ku.machine-learning": {
            "ku": {"uid": "ku.machine-learning", "title": "Machine Learning", "entity_type": "ku"},
            "graph_context": {},
        },
        "ps.data-pipelines": {
            "ku": {
                "uid": "ps.data-pipelines",
                "title": "Data Pipelines",
                "entity_type": "path_step",
            },
            "graph_context": {},
        },
    }
    ctx.active_task_uids = ["task_001", "task_002"]
    ctx.active_goal_uids = ["goal_001"]
    ctx.active_habit_uids = ["habit_001"]
    ctx.today_event_uids = ["event_today"]
    ctx.upcoming_event_uids = ["event_today", "event_next"]
    ctx.core_principle_uids = ["principle_001"]
    ctx.pending_choice_uids = ["choice_001"]
    ctx.entities_rich = {
        "tasks": [
            _item("task_001", "Complete Python project", "task"),
            _item("task_002", "Review ML code", "task"),
            # touched inside the window but completed: in the rich rows, not in active_task_uids
            _item("task_done", "Python retrospective", "task", status="completed"),
        ],
        "goals": [_item("goal_001", "Learn Machine Learning", "goal")],
        "habits": [_item("habit_001", "Daily Python kata", "habit")],
        "events": [
            _item("event_today", "Python meetup", "event"),
            _item("event_next", "Data study group", "event"),
        ],
        "principles": [_item("principle_001", "Ship in public", "principle")],
        "choices": [_item("choice_001", "Pick a capstone project", "choice")],
    }
    return ctx


def _uids(entities: dict[str, list[dict[str, str]]], key: str) -> list[str]:
    return [match["uid"] for match in entities[key]]


def test_exact_title_match_across_every_domain(context: RichUserContext) -> None:
    entities = EntityExtractor().extract_entities_from_query(
        "Before Python Basics, should I Complete Python project, join the Python meetup, "
        "keep the Daily Python kata, honour Ship in public and Pick a capstone project?",
        context,
    )

    assert _uids(entities, "knowledge") == ["ku.python-basics"]
    assert _uids(entities, "tasks") == ["task_001"]
    assert _uids(entities, "habits") == ["habit_001"]
    assert _uids(entities, "events") == ["event_today"]
    assert _uids(entities, "principles") == ["principle_001"]
    assert _uids(entities, "choices") == ["choice_001"]
    # "Learn Machine Learning" shares no significant word (>3 chars) with the question
    assert entities["goals"] == []


def test_every_match_carries_the_node_entity_type(context: RichUserContext) -> None:
    entities = EntityExtractor().extract_entities_from_query(
        "What comes after Python Basics and Data Pipelines?", context
    )

    # Ku and PathStep alike, told apart by the label-derived field, never the uid
    assert {m["uid"]: m["entity_type"] for m in entities["knowledge"]} == {
        "ku.python-basics": "ku",
        "ps.data-pipelines": "path_step",
    }
    assert entities["knowledge"][0].keys() == {"uid", "title", "entity_type"}


def test_matching_is_case_insensitive(context: RichUserContext) -> None:
    entities = EntityExtractor().extract_entities_from_query("tell me about python basics", context)

    assert "ku.python-basics" in _uids(entities, "knowledge")


def test_partial_and_acronym_strategies(context: RichUserContext) -> None:
    # "python" is a significant word of "Python Basics", "Complete Python project" and
    # "Python meetup"; "ml" is the acronym of "Machine Learning". "Review ML code" has
    # no significant word in the question and "ml" is too short to be one.
    entities = EntityExtractor().extract_entities_from_query(
        "How is my Python work and my ML progress?", context
    )

    assert set(_uids(entities, "knowledge")) == {"ku.python-basics", "ku.machine-learning"}
    assert _uids(entities, "tasks") == ["task_001"]
    assert _uids(entities, "events") == ["event_today"]


def test_a_rich_row_outside_the_live_scope_is_not_a_candidate(context: RichUserContext) -> None:
    """The window admits a completed task into the rich rows; extraction scopes to open ones."""
    entities = EntityExtractor().extract_entities_from_query(
        "How did the Python retrospective go?", context
    )

    assert "task_done" not in _uids(entities, "tasks")


def test_an_event_in_both_today_and_upcoming_matches_once(context: RichUserContext) -> None:
    entities = EntityExtractor().extract_entities_from_query("the Python meetup", context)

    assert _uids(entities, "events") == ["event_today"]


def test_no_match_yields_every_domain_empty(context: RichUserContext) -> None:
    entities = EntityExtractor().extract_entities_from_query("What is the weather like?", context)

    assert entities == {
        "knowledge": [],
        "tasks": [],
        "goals": [],
        "habits": [],
        "events": [],
        "principles": [],
        "choices": [],
    }


def test_the_extractor_reaches_no_service() -> None:
    """Zero graph reads per question: there is no handle to read through."""
    extractor = EntityExtractor()

    assert not any(name.endswith("_service") for name in vars(extractor))
    assert not any(name.endswith("_service") for name in vars(EntityExtractor))
