"""Tests for Goal.calculate_progress() — the current_value unit contract.

``current_value``/``target_value`` are DOMAIN UNITS (25 of 100 miles, a 30-day
streak) named by ``unit_of_measurement``; ``progress_percentage`` is the 0-100
percent. Reading the ratio when a writer had stored a percent in ``current_value``
is what produced the bugs pinned below, so each case names the writer it came from.
"""

from __future__ import annotations

import pytest

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal


def _goal(**kwargs: object) -> Goal:
    return Goal(uid="goal.progress", user_uid="user.test", title="t", **kwargs)  # type: ignore[arg-type]


class TestProgressPercentageIsCanonical:
    """progress_percentage wins whenever it is set — it is what every writer maintains."""

    def test_task_based_percent_does_not_read_as_domain_units(self):
        """GoalsProgressService._update_goal_from_task_completion writes 20%.

        target_value=5 counts tasks; reading 20/5 as a ratio saturated at 1.0.
        """
        goal = _goal(
            measurement_type=MeasurementType.TASK_BASED,
            target_value=5.0,
            current_value=20.0,
            progress_percentage=20.0,
        )
        assert goal.calculate_progress() == 0.20

    def test_habit_based_percent_does_not_read_as_domain_units(self):
        """_update_goal_from_habit_completion: target_value=30 is a streak length."""
        goal = _goal(
            measurement_type=MeasurementType.HABIT_BASED,
            target_value=30.0,
            current_value=60.0,
            progress_percentage=60.0,
        )
        assert goal.calculate_progress() == 0.60

    def test_completed_goal_reads_full_without_a_settled_current_value(self):
        """complete_goal writes progress_percentage=100 and never touches current_value."""
        goal = _goal(
            measurement_type=MeasurementType.NUMERIC,
            target_value=10.0,
            current_value=0.0,
            progress_percentage=100.0,
            status=EntityStatus.COMPLETED,
        )
        assert goal.calculate_progress() == 1.0

    def test_percentage_measurement_type_reads_progress_percentage(self):
        goal = _goal(
            measurement_type=MeasurementType.PERCENTAGE,
            target_value=100.0,
            current_value=0.0,
            progress_percentage=42.0,
        )
        assert goal.calculate_progress() == 0.42

    def test_over_one_hundred_percent_clamps(self):
        assert _goal(progress_percentage=250.0).calculate_progress() == 1.0

    def test_negative_percent_clamps_to_zero(self):
        assert _goal(progress_percentage=-10.0).calculate_progress() == 0.0


class TestMeasurementIsNotAProgressSource:
    """``current_value``/``target_value`` never reach the answer, in either direction.

    An earlier revision consulted the ratio when ``progress_percentage`` was falsy, to
    seed a goal no writer had touched. That cannot distinguish "never recorded" from
    "explicitly reset to 0%" — ``progress_percentage`` has no unset state — so a 5-of-10
    goal reset to 0 read 0.5. The ratio is gone rather than made conditional.
    """

    def test_measurement_without_a_percent_reads_zero(self):
        """25 of 100 miles, no progress_percentage: the measurement is not progress."""
        goal = _goal(
            measurement_type=MeasurementType.NUMERIC,
            target_value=100.0,
            current_value=25.0,
            unit_of_measurement="miles",
        )
        assert goal.calculate_progress() == 0.0

    def test_reset_to_zero_is_not_overridden_by_a_stale_measurement(self):
        """The case that killed the fallback: 5 of 10 miles, progress explicitly 0%."""
        goal = _goal(
            measurement_type=MeasurementType.NUMERIC,
            target_value=10.0,
            current_value=5.0,
            progress_percentage=0.0,
        )
        assert goal.calculate_progress() == 0.0

    def test_measurement_does_not_cap_a_recorded_percent(self):
        """current_value far below target must not drag a recorded 80% down."""
        goal = _goal(target_value=100.0, current_value=1.0, progress_percentage=80.0)
        assert goal.calculate_progress() == 0.80

    def test_no_fields_at_all_is_zero(self):
        assert _goal().calculate_progress() == 0.0


class TestUninterpretableStoredValues:
    """Neo4j properties are untyped and vault ingestion does not narrow them.

    ``format_goal_gantt`` proved these reach a reader as-is. This method has no
    ``Result`` channel and runs on every goal card, list and sort, so it answers 0.0
    rather than raising; the Gantt formatter reads the raw field and still fails loudly.
    """

    def test_a_quoted_number_is_rescued_rather_than_zeroed(self):
        """``progress_percentage: "40"`` in vault frontmatter arrives as ``str``; the
        narrowing converts it, so the goal reads 40% instead of raising or reading 0."""
        assert _goal(progress_percentage="40").calculate_progress() == 0.40

    @pytest.mark.parametrize(
        "stored",
        ["forty", [], float("nan"), float("inf"), float("-inf"), None],
        ids=["unparseable-str", "list", "nan", "inf", "-inf", "none"],
    )
    def test_values_no_cast_can_rescue_read_as_no_progress(self, stored):
        assert _goal(progress_percentage=stored).calculate_progress() == 0.0
