"""The goal page offers the control its measurement type and status allow.

A goal's measurement type names the one writer of its figure, so the page shows the
progress form only where the learner is that writer, and says where a derived figure
comes from otherwise. A goal its owner set aside shows what it holds and no control.
"""

from __future__ import annotations

import re
from datetime import date

import pytest
from fasthtml.common import to_xml

from core.models.enums import EntityStatus
from core.models.enums.goal_enums import HabitEssentiality, MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.goal_habit_link import GoalHabitLink
from core.models.goal.milestone import Milestone
from core.ports.query_types import EntityConnection
from ui.activities.goals_views import GoalDetailView, GoalHabitsSection

_MILESTONES = (
    Milestone(uid="m_open", title="Open one"),
    Milestone(uid="m_done", title="Done one", is_completed=True),
)


def _page(
    measurement: MeasurementType,
    status: EntityStatus = EntityStatus.ACTIVE,
    *,
    milestones: tuple[Milestone, ...] = _MILESTONES,
    target_value: float | None = None,
    current_value: float = 0.0,
    unit: str | None = None,
) -> str:
    goal = Goal(
        uid="goal_page",
        user_uid="user_page",
        title="A goal",
        status=status,
        measurement_type=measurement,
        milestones=milestones,
        target_value=target_value,
        current_value=current_value,
        unit_of_measurement=unit,
    )
    return to_xml(GoalDetailView(goal, []))


@pytest.mark.parametrize("measurement", list(MeasurementType))
def test_the_progress_form_shows_exactly_where_the_learner_enters_the_figure(
    measurement: MeasurementType,
) -> None:
    html = _page(measurement, target_value=50.0)

    assert ("data-goal-progress" in html) == measurement.takes_entered_figure()
    assert ("Measured from" in html) == (not measurement.takes_entered_figure())


def test_a_numeric_goal_is_asked_for_its_unit_and_a_percentage_goal_for_a_percentage() -> None:
    numeric = _page(MeasurementType.NUMERIC, target_value=50.0, current_value=12.5, unit="km")
    percentage = _page(MeasurementType.PERCENTAGE)

    assert "Progress so far (of 50 km)" in numeric
    assert 'value="12.5"' in numeric
    assert ' max="100"' not in numeric
    assert "Progress so far (%)" in percentage
    assert ' max="100"' in percentage
    assert "12.5/50 km" in numeric, "the measurement pair renders without a float's trailing .0"


def test_a_numeric_goal_with_no_target_is_told_to_set_one() -> None:
    html = _page(MeasurementType.NUMERIC)

    assert "data-goal-progress" not in html
    assert "Set a target value" in html


def test_an_open_milestone_carries_complete_and_a_reached_one_reopen() -> None:
    html = _page(MeasurementType.MILESTONE)

    assert 'data-goal-milestone-complete="m_open"' in html
    assert 'data-goal-milestone-complete="m_done"' not in html
    assert 'data-goal-milestone-reopen="m_done"' in html
    assert 'data-goal-milestone-reopen="m_open"' not in html
    assert 'hx-post="/api/goals/goal_page/milestones/reopen"' in html
    assert "data-goal-add-milestone" in html


def test_a_goal_with_no_milestones_still_offers_the_add_form() -> None:
    html = _page(MeasurementType.PERCENTAGE, milestones=())

    assert "data-goal-add-milestone" in html
    assert "data-goal-milestone-complete" not in html


@pytest.mark.parametrize(
    "status", [EntityStatus.CANCELLED, EntityStatus.ARCHIVED, EntityStatus.FAILED]
)
def test_a_goal_set_aside_shows_its_milestones_and_no_control(status: EntityStatus) -> None:
    html = _page(MeasurementType.PERCENTAGE, status)

    assert "Open one" in html
    for control in (
        "data-goal-progress",
        "data-goal-add-milestone",
        "data-goal-milestone-complete",
        "data-goal-milestone-reopen",
    ):
        assert control not in html
    assert " · On Track" not in html
    assert " · Behind" not in html
    assert f" · {status.value.title()}" in html


def test_a_completed_goal_keeps_its_controls() -> None:
    """Lowering the figure or adding a milestone is how a finished goal is taken up again."""
    html = _page(MeasurementType.PERCENTAGE, EntityStatus.COMPLETED)

    assert "data-goal-progress" in html
    assert "data-goal-add-milestone" in html


def test_a_reopened_milestone_shows_its_target_not_the_day_it_was_first_reached() -> None:
    reopened = Milestone(
        uid="m_back",
        title="Back open",
        target_date=date(2026, 12, 1),
        achieved_date=date(2026, 9, 2),
    )
    html = _page(MeasurementType.MILESTONE, milestones=(reopened,))

    assert "By 2026-12-01" in html
    assert "Achieved 2026-09-02" not in html
    assert 'data-goal-milestone-complete="m_back"' in html


# ---------------------------------------------------------------------------
# The habit section (``GoalHabitsSection``, loaded by ``/goals/habits``)
# ---------------------------------------------------------------------------

_LINKS = (
    GoalHabitLink(habit_uid="habit_run", title="Run", essentiality=HabitEssentiality.ESSENTIAL),
    GoalHabitLink(habit_uid="habit_read", title="Read", essentiality=HabitEssentiality.OPTIONAL),
)


def _habits(
    status: EntityStatus = EntityStatus.ACTIVE, links: tuple[GoalHabitLink, ...] = _LINKS
) -> str:
    goal = Goal(uid="goal_page", user_uid="user_page", title="A goal", status=status)
    return to_xml(GoalHabitsSection(goal, links))


def _selected_tier(html: str, habit_uid: str) -> str:
    """The option chosen in a habit row's tier select."""
    select = re.search(
        rf"<select[^>]*data-goal-habit-tier-select=\"{habit_uid}\"[^>]*>(.*?)</select>",
        html,
        re.DOTALL,
    )
    assert select is not None, f"no tier select for {habit_uid}"
    chosen = re.findall(r"<option[^>]*value=\"(\w+)\"[^>]*selected", select.group(1))
    assert len(chosen) == 1
    return chosen[0]


def test_each_linked_habit_shows_its_tier_in_its_own_select() -> None:
    html = _habits()

    assert _selected_tier(html, "habit_run") == "essential"
    assert _selected_tier(html, "habit_read") == "optional"
    assert re.search(r"hx-post=[\"']/api/goals/goal_page/habits/essentiality[\"']", html), (
        "the select posts the tier door"
    )
    assert re.search(r"hx-vals=['\"]\{(&quot;|\")habit_uid(&quot;|\"): (&quot;|\")habit_run", html)


def test_each_linked_habit_carries_unlink_and_the_section_a_link_form() -> None:
    html = _habits()

    assert 'data-goal-habit-unlink="habit_run"' in html
    assert 'data-goal-habit-unlink="habit_read"' in html
    assert "data-goal-link-habit" in html
    assert re.search(r"hx-post=[\"']/api/goals/goal_page/habits[\"']", html)
    assert 'name="habit_uid"' in html, "the picker's hidden field is what the form posts"


def test_a_goal_with_no_habits_says_so_and_offers_the_link_form() -> None:
    html = _habits(links=())

    assert "No habits support this goal yet." in html
    assert "data-goal-link-habit" in html


@pytest.mark.parametrize(
    "status", [EntityStatus.CANCELLED, EntityStatus.ARCHIVED, EntityStatus.FAILED]
)
def test_a_goal_set_aside_shows_its_habits_and_tiers_and_no_control(status: EntityStatus) -> None:
    html = _habits(status)

    assert "Run" in html and "Read" in html
    assert 'data-goal-habit-tier="essential"' in html
    assert 'data-goal-habit-tier="optional"' in html
    assert "<select" not in html
    assert "data-goal-habit-unlink" not in html
    assert "data-goal-link-habit" not in html


def test_the_detail_page_loads_the_section_and_lists_habits_there_alone() -> None:
    goal = Goal(uid="goal_page", user_uid="user_page", title="A goal")
    habit_link: EntityConnection = {
        "heading": "Habits that support this goal",
        "rel_type": "SUPPORTS_GOAL",
        "connected_uid": "habit_run",
        "title": "Run",
        "connected_type": "habit",
        "inferred": False,
        "confidence": None,
    }
    principle_link: EntityConnection = {
        **habit_link,
        "heading": "Principles that support this goal",
        "connected_uid": "principle_honesty",
        "title": "Honesty",
        "connected_type": "principle",
    }

    html = to_xml(GoalDetailView(goal, [habit_link, principle_link]))

    assert re.search(r"hx-get=[\"']/goals/habits\?uid=goal_page[\"']", html)
    assert 'id="goal-habits-goal_page"' in html
    assert "Principles that support this goal" in html
    assert "Honesty" in html
    assert ">Run<" not in html, "a supporting habit is listed by the habit section, not twice"
