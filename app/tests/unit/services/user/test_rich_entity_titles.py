"""``rich_entity_titles`` — every title the rich context carries, by uid.

The Insights cards and the schedule-aware recommendations name entities by it.
It must read the activity domains' rich items, the engaged-Ku window, the
learner's knowledge units and the three path-step collections, skip anything
without a title, and leave a uid the context lacks absent (the caller's Ku batch).
"""

from __future__ import annotations

from core.services.user.rich_context import rich_entity_titles
from core.services.user.unified_user_context import RichUserContext


def test_reads_every_collection_the_context_names_titles_in() -> None:
    context = RichUserContext(user_uid="user_titles")
    context.entities_rich = {
        "tasks": [{"entity": {"uid": "task_1", "title": "Pay bills"}, "graph_context": {}}],
        "ku": [{"entity": {"uid": "ku.window", "title": "Window concept"}, "graph_context": {}}],
    }
    context.knowledge_units_rich = {"ku.known": {"ku": {"uid": "ku.known", "title": "Known"}}}
    context.active_path_steps_rich = [{"step": {"uid": "ps.active", "title": "Active step"}}]
    context.current_path_steps = [{"uid": "ps.current", "title": "Current step"}]
    context.mastered_path_steps = [
        {"uid": "ps.done", "title": "Mastered step", "entity_type": "path_step"}
    ]

    assert rich_entity_titles(context) == {
        "task_1": "Pay bills",
        "ku.window": "Window concept",
        "ku.known": "Known",
        "ps.active": "Active step",
        "ps.current": "Current step",
        "ps.done": "Mastered step",
    }


def test_an_item_without_a_title_contributes_nothing() -> None:
    context = RichUserContext(user_uid="user_titles")
    context.entities_rich = {"goals": [{"entity": {"uid": "goal_1"}, "graph_context": {}}]}
    context.knowledge_units_rich = {"ku.bare": {"ku": {"uid": "ku.bare", "title": ""}}}
    assert rich_entity_titles(context) == {}


def test_no_context_is_no_titles() -> None:
    assert rich_entity_titles(None) == {}
