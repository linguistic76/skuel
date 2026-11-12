"""The goal page offers the control its measurement type and status allow.

A goal's measurement type names the one writer of its figure, so the page shows the
progress form only where the learner is that writer, and says where a derived figure
comes from otherwise. A goal its owner set aside shows what it holds and no control.
"""

from __future__ import annotations

import pytest
from fasthtml.common import to_xml

from core.models.enums import EntityStatus
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.milestone import Milestone
from ui.activities.goals_views import GoalDetailView

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
