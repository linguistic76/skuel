"""Value pins for the goal bar emitted by ``VisualizationService.format_goal_gantt``.

``format_goal_gantt`` read ``getattr(goal, "progress", 0) or 0`` — and ``Goal`` has no
``progress`` field. The default therefore won on every call, so **every** goal bar on
``GET /api/visualizations/gantt/goal/{goal_uid}`` rendered 0%. The normalisation beside it,
``int(goal_progress * 100) if goal_progress <= 1 else int(goal_progress)``, then took its
``<= 1`` arm every time (``0 <= 1``) and faithfully scaled the wrong number; the arm that
no input could reach was the ``else int(goal_progress)``.

Why the bug survived: nothing asserted the *value*. No test in the repo's history ever
referenced ``format_goal_gantt``; the one path that reached it,
``tests/integration/test_gantt_aggregation_roundtrip.py``, builds a real ``Goal`` through
Neo4j and asserts only which UIDs appear. ``test_visualization_wire_shape.py`` pins the key
set and passes either way. Shape was covered from both ends and value from neither, which
is the gap this file fills.

The goals below are real :class:`~core.models.goal.goal.Goal` objects rather than
duck-typed stand-ins for a forward-looking reason, not a historical one: a stand-in
carrying a ``progress`` attribute would make the buggy code pass and silently re-admit the
regression.

Two tests here also pin the *choice of reader*. ``Goal`` exposes both
``progress_percentage`` (0-100) and ``calculate_progress()`` (nominally 0.0-1.0), and the
latter is wrong for this bar — see ``TestGoalBarReaderChoice``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.services.visualization_service import VisualizationService


@pytest.fixture
def service() -> VisualizationService:
    return VisualizationService()


def _goal(**overrides: object) -> Goal:
    """A real Goal. ``uid`` and ``title`` are read by the formatter, ``user_uid`` is a
    required constructor argument it never touches, and ``measurement_type`` is here
    because the reader-choice tests below turn on it."""
    fields: dict[str, object] = {
        "uid": "goal_1",
        "user_uid": "user_1",
        "title": "Ship the feature",
        "measurement_type": MeasurementType.PERCENTAGE,
        "start_date": date(2026, 3, 1),
        "target_date": date(2026, 6, 1),
    }
    fields.update(overrides)
    return Goal(**fields)  # type: ignore[arg-type]


def _goal_bar(service: VisualizationService, goal: Goal) -> dict:
    """The first Gantt task is the goal's own bar (custom_class ``goal-bar``)."""
    result = service.format_goal_gantt(goal, [])
    assert result.is_ok, f"format_goal_gantt failed: {result}"
    bar = result.value["tasks"][0]
    assert bar["custom_class"] == "goal-bar"
    return bar


class TestGoalBarProgress:
    def test_partial_progress_is_not_zero(self, service: VisualizationService) -> None:
        """The regression itself: a 40%-complete goal must not render as an empty bar."""
        bar = _goal_bar(service, _goal(progress_percentage=40.0))

        assert bar["progress"] == 40

    def test_zero_progress_stays_zero(self, service: VisualizationService) -> None:
        bar = _goal_bar(service, _goal(progress_percentage=0.0))

        assert bar["progress"] == 0

    def test_complete_goal_reads_one_hundred(self, service: VisualizationService) -> None:
        """Pins the scale at the top of the range: 100 in, 100 out — catching a stray
        ``/ 100``, which would emit 1. Note this test cannot catch the opposite slip: a
        doubly-scaled 10000 clips back to exactly 100 through the clamp, so
        ``test_partial_progress_is_not_zero`` is what covers that direction."""
        bar = _goal_bar(service, _goal(progress_percentage=100.0))

        assert bar["progress"] == 100

    def test_sub_one_percent_is_not_inflated_to_half(self, service: VisualizationService) -> None:
        """The case that keeps the deleted ``<= 1`` normalisation deleted.

        Against a 0-100 reader, ``int(value * 100) if value <= 1`` turns 0.5% into 50% —
        a barely-started goal rendered as half done.
        """
        bar = _goal_bar(service, _goal(progress_percentage=0.5))

        assert bar["progress"] == 0

    def test_repeating_percentage_rounds_rather_than_truncates(
        self, service: VisualizationService
    ) -> None:
        """``complete_milestone`` stores ``(completed / total) * 100``, so 2 of 3
        milestones is 66.666… — which ``int()`` would render as 66."""
        bar = _goal_bar(service, _goal(progress_percentage=200.0 / 3.0))

        assert bar["progress"] == 67

    def test_above_range_progress_is_clamped_to_one_hundred(
        self, service: VisualizationService
    ) -> None:
        """Vault ingestion copies goal frontmatter into node properties unchecked, so
        ``progress_percentage: 150`` reaches the formatter. Frappe Gantt takes 0-100."""
        bar = _goal_bar(service, _goal(progress_percentage=150.0))

        assert bar["progress"] == 100

    def test_below_range_progress_is_clamped_to_zero(self, service: VisualizationService) -> None:
        """Same unvalidated door as above, other end: ``progress_percentage: -40``."""
        bar = _goal_bar(service, _goal(progress_percentage=-40.0))

        assert bar["progress"] == 0


class TestGoalBarReaderChoice:
    """``Goal`` offers two progress readers and only one of them is right here.

    ``Goal.calculate_progress()`` prefers a ``current_value / target_value`` branch, but
    every live writer stores a *percent* in ``current_value`` while ``target_value`` holds
    domain units (5 tasks, a 30-day streak, 10 books). Both tests below would fail if this
    formatter were switched to ``calculate_progress()``; they exist so that switch cannot
    be made silently.
    """

    def test_completed_value_measured_goal_reads_full(self, service: VisualizationService) -> None:
        """``goals_core_service.complete_goal`` writes ``progress_percentage=100.0`` and
        never touches ``current_value``, so ``calculate_progress()`` returns
        ``min(1.0, 0.0 / 10.0)`` = 0.0 — a finished goal with an empty bar, which is the
        exact symptom this module exists to prevent."""
        bar = _goal_bar(
            service,
            _goal(
                measurement_type=MeasurementType.NUMERIC,
                target_value=10.0,
                current_value=0.0,
                progress_percentage=100.0,
            ),
        )

        assert bar["progress"] == 100

    def test_task_based_goal_one_fifth_in_does_not_read_complete(
        self, service: VisualizationService
    ) -> None:
        """``goals_progress_service`` writes ``current_value = new_progress`` (a percent)
        alongside ``progress_percentage``, so for a 5-task goal one task in,
        ``calculate_progress()`` computes ``min(1.0, 20.0 / 5.0)`` = 1.0."""
        bar = _goal_bar(
            service,
            _goal(
                measurement_type=MeasurementType.TASK_BASED,
                target_value=5.0,
                current_value=20.0,
                progress_percentage=20.0,
            ),
        )

        assert bar["progress"] == 20


class TestGoalBarDates:
    """``start_date`` / ``target_date`` were read through ``getattr`` defaults too. Both
    are real ``Goal`` fields, so those reads worked — these pin the fallbacks that the
    ``or`` half of those expressions provided, which the direct reads must keep."""

    def test_declared_dates_are_used(self, service: VisualizationService) -> None:
        bar = _goal_bar(service, _goal(progress_percentage=10.0))

        assert bar["start"] == "2026-03-01"
        assert bar["end"] == "2026-06-01"

    def test_missing_dates_fall_back_to_today_plus_ninety_days(
        self, service: VisualizationService
    ) -> None:
        bar = _goal_bar(service, _goal(start_date=None, target_date=None))

        assert bar["start"] == date.today().isoformat()
        assert bar["end"] == (date.today() + timedelta(days=90)).isoformat()
