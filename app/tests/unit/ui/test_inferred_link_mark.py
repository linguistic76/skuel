"""Where a link the grounding pass inferred is marked, and where it is not.

Grounding writes ``APPLIES_KNOWLEDGE {inferred: true}`` from tasks (and entries, whose
pages have their own chips). The page reader hands every Activity surface a row's
``inferred`` flag; only the task's detail page reads it, marking the link with its
confidence and offering its owner a remove that posts to the task's removal door.
Every other detail page and every list card renders an inferred row exactly as it
renders a row someone made.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from fasthtml.common import to_xml

from core.models.choice.choice import Choice
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.task.task import Task
from ui.activities.choices_views import ChoiceCard, ChoiceDetailView
from ui.activities.events_views import EventCard, EventDetailView
from ui.activities.goals_views import GoalCard, GoalDetailView
from ui.activities.habits_views import HabitCard, HabitDetailView
from ui.activities.principles_views import PrincipleCard, PrincipleDetailView
from ui.activities.tasks_views import TaskCard, TaskDetailView

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.ports.query_types import EntityConnection

HEADING = "Knowledge applied"
KU = "ku.mark.breath"
TITLE = "Breath awareness"
DOOR = "/api/tasks/grounding/remove"

type View = Callable[..., FT]  # each view takes its own domain model

DOMAINS: list[tuple[str, type, View, View]] = [
    ("tasks", Task, TaskDetailView, TaskCard),
    ("goals", Goal, GoalDetailView, GoalCard),
    ("habits", Habit, HabitDetailView, HabitCard),
    ("events", Event, EventDetailView, EventCard),
    ("choices", Choice, ChoiceDetailView, ChoiceCard),
    ("principles", Principle, PrincipleDetailView, PrincipleCard),
]
OTHER_FIVE = [d for d in DOMAINS if d[0] != "tasks"]


def _link(*, inferred: bool, uid: str = KU, title: str = TITLE) -> EntityConnection:
    return {
        "heading": HEADING,
        "rel_type": "APPLIES_KNOWLEDGE",
        "connected_uid": uid,
        "title": title,
        "connected_type": "ku",
        "inferred": inferred,
        "confidence": 0.82 if inferred else None,
    }


# EntityPicker mints a random id per render (``picker-{name}-{8 hex}``).
_PICKER_ID = re.compile(r"(picker-[a-z_]+)-[0-9a-f]{8}")


def _render(component: FT) -> str:
    return _PICKER_ID.sub(r"\1-ID", to_xml(component))


def _entity(model: type, domain: str) -> object:
    return model(uid=f"{domain}_mark_1", title=f"A {domain} entity", user_uid="user_mark")


@pytest.mark.parametrize(
    ("domain", "model", "detail", "_card"), OTHER_FIVE, ids=[d[0] for d in OTHER_FIVE]
)
def test_the_other_five_detail_pages_show_nothing_new(
    domain: str, model: type, detail: View, _card: View
) -> None:
    entity = _entity(model, domain)
    owned = _render(detail(entity, [_link(inferred=False)]))
    inferred = _render(detail(entity, [_link(inferred=True)]))

    assert TITLE in owned
    assert inferred == owned


@pytest.mark.parametrize(
    ("domain", "model", "_detail", "card"), DOMAINS, ids=[d[0] for d in DOMAINS]
)
def test_no_list_card_marks_an_inferred_link(
    domain: str, model: type, _detail: View, card: View
) -> None:
    entity = _entity(model, domain)
    owned = _render(card(entity, [_link(inferred=False)]))
    inferred = _render(card(entity, [_link(inferred=True)]))

    assert TITLE in owned
    assert inferred == owned


def test_the_task_page_marks_only_the_inferred_link_and_offers_its_remove() -> None:
    task = Task(uid="task_mark_1", title="Notice the breath", user_uid="user_mark")
    owned = _link(inferred=False, uid="ku.mark.named", title="Named by the owner")
    html = to_xml(TaskDetailView(task, [owned, _link(inferred=True)]))

    section = html[html.index('id="connections-task_mark_1"') :]
    owned_row = section[section.index("Named by the owner") :].split("</li>", 1)[0]
    inferred_row = section[section.index(f">{TITLE}<") :].split("</li>", 1)[0]
    assert "inferred" not in owned_row
    assert "<button" not in owned_row
    assert "inferred · 82%" in inferred_row
    assert f'hx-post="{DOOR}?uid=task_mark_1&amp;ku_uid={KU}"' in inferred_row
    assert 'hx-target="#connections-task_mark_1"' in inferred_row
    assert 'hx-swap="outerHTML"' in inferred_row
    assert html.count("data-inferred-link-remove") == 1


def test_the_task_section_keeps_its_id_when_its_last_link_is_gone() -> None:
    task = Task(uid="task_mark_1", title="Notice the breath", user_uid="user_mark")
    assert 'id="connections-task_mark_1"' in to_xml(TaskDetailView(task, []))
