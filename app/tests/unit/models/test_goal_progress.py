"""Tests for Goal.calculate_progress() — the current_value unit contract.

``current_value``/``target_value`` are DOMAIN UNITS (25 of 100 miles, a 30-day
streak) named by ``unit_of_measurement``; ``progress_percentage`` is the 0-100
percent. Reading the ratio when a writer had stored a percent in ``current_value``
is what produced the bugs pinned below, so each case names the writer it came from.
"""

from __future__ import annotations

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


class TestDomainUnitSeeding:
    """The ratio is a seed for goals no writer has touched yet, not a second truth."""

    def test_authored_measurement_reads_before_any_writer_runs(self):
        """25 of 100 miles, progress_percentage still at its 0.0 default."""
        goal = _goal(
            measurement_type=MeasurementType.NUMERIC,
            target_value=100.0,
            current_value=25.0,
            unit_of_measurement="miles",
        )
        assert goal.calculate_progress() == 0.25

    def test_measurement_beyond_target_clamps(self):
        goal = _goal(target_value=100.0, current_value=120.0)
        assert goal.calculate_progress() == 1.0

    def test_zero_target_does_not_divide(self):
        assert _goal(target_value=0.0, current_value=5.0).calculate_progress() == 0.0

    def test_no_target_and_no_percent_is_zero(self):
        assert _goal().calculate_progress() == 0.0
