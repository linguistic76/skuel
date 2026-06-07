"""Unit Tests — Overview UI: Goal Learning-Requirements Section
==============================================================

Tests for ``_goal_focus_section`` / ``_goal_learning_requirements_line`` in
``ui/profile/overview.py`` — the daily-plan card subsection that surfaces each
advancing goal's mastery-aware learning requirements (the production rendering of
the consolidated learning-requirements lens).

Covers:
1. No contextual goals → section returns None
2. Goal with an open knowledge gap → renders "mastered (n%) · gaps · ~h to learn"
3. Goal with all knowledge mastered → renders "ready to start"
4. Goal with no required knowledge → no requirements line (no clutter)
"""

from __future__ import annotations

from fasthtml.common import to_xml

from core.models.context_types import ContextualGoal, DailyWorkPlan
from core.services.user.unified_user_context import UserContext
from ui.profile.overview import _goal_focus_section

REQUIRED = ["ku_a", "ku_b"]


def _ctx(mastery: dict[str, float]) -> UserContext:
    return UserContext(
        user_uid="user_test",
        active_goal_uids={"goal_test"},
        knowledge_mastery=mastery,
    )


def _goal(mastery: dict[str, float], required: list[str] = REQUIRED) -> ContextualGoal:
    return ContextualGoal.from_entity_and_context(
        uid="goal_test",
        title="Learn Rust",
        context=_ctx(mastery),
        required_knowledge_uids=required,
    )


def test_no_goals_returns_none():
    assert _goal_focus_section(DailyWorkPlan()) is None


def test_open_gap_renders_mastery_summary():
    plan = DailyWorkPlan(contextual_goals=(_goal({"ku_a": 0.9}),))  # ku_b is a gap
    xml = to_xml(_goal_focus_section(plan))
    assert "Learn Rust" in xml
    assert "1/2 mastered" in xml
    assert "1 gap" in xml
    assert "to learn" in xml
    assert "ready to start" not in xml


def test_all_mastered_renders_ready():
    plan = DailyWorkPlan(contextual_goals=(_goal({"ku_a": 0.9, "ku_b": 0.9}),))
    xml = to_xml(_goal_focus_section(plan))
    assert "ready to start" in xml
    assert "mastered" not in xml


def test_no_required_knowledge_renders_no_line():
    plan = DailyWorkPlan(contextual_goals=(_goal({}, required=[]),))
    xml = to_xml(_goal_focus_section(plan))
    assert "Learn Rust" in xml  # goal still listed
    assert "mastered" not in xml
    assert "ready to start" not in xml
