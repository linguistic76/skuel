"""Unit-scale guard for the goal prediction helpers.

``Goal.calculate_progress()`` returns a **0.0-1.0 fraction** (pinned by its
docstring, by ``tests/integration/test_goals_core_operations.py`` asserting
0.25 for 25/100, and by both UI consumers doing ``int(progress * 100)``).
Every comparison in ``_predictive_mixin`` is **percentage-scaled**: expected
progress is ``(elapsed / total) * 100``, the sigmoid steepness is tuned for
percentage-point differences, remaining work is ``100 - progress``, and the
momentum rate is divided by 100.

Feeding the fraction into that arithmetic silently broke four behaviours:
the "already complete" short-circuit and the "Over halfway to goal" factor
could never fire, predicted completion dates were inflated ~100x, and the
progress factor was pinned near zero so every goal read as behind schedule.
``_progress_percent`` is the one place the fraction is scaled; these tests
pin each consequence so the units can't drift apart again.

These helpers are pure functions of a ``Goal`` — no graph, no mocks.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.services.goals._predictive_mixin import _PredictiveMixin, _progress_percent
from core.services.intelligence.trend_analyzer import Trend

_USER = "user_test_goal_predictive_units"

# The helpers under test are pure; a bare mixin instance is enough.
_MIXIN = _PredictiveMixin()


def _goal(
    *,
    progress: float,
    started_days_ago: int | None = None,
    target_in_days: int | None = None,
) -> Goal:
    """A percentage-measured goal sitting at ``progress`` percent complete.

    PERCENTAGE measurement deliberately — it keeps these tests off the
    ``current_value / target_value`` branch, which has its own open defect.
    """
    today = date.today()
    return Goal(
        uid="goal_predictive_units",
        title="Unit-scale probe",
        user_uid=_USER,
        measurement_type=MeasurementType.PERCENTAGE,
        progress_percentage=progress,
        start_date=today - timedelta(days=started_days_ago)
        if started_days_ago is not None
        else None,
        target_date=today + timedelta(days=target_in_days) if target_in_days is not None else None,
    )


def _habit(streak: int) -> Habit:
    return Habit(
        uid=f"habit_predictive_units_{streak}",
        title="Supporting habit",
        user_uid=_USER,
        current_streak=streak,
    )


class TestProgressPercentBoundary:
    """The one conversion point between the model's unit and this module's."""

    def test_scales_the_models_fraction_to_a_percentage(self):
        goal = _goal(progress=25.0, started_days_ago=1)

        assert goal.calculate_progress() == pytest.approx(0.25), (
            "Goal.calculate_progress() is the 0.0-1.0 contract this module converts from"
        )
        assert _progress_percent(goal) == pytest.approx(25.0)


class TestProgressFactor:
    def test_on_schedule_goal_lands_on_the_sigmoid_midpoint(self):
        """50% done at 50% elapsed is diff=0, which the sigmoid maps to 0.5.

        With the fraction fed in raw, diff was 0.5 - 50 = -49.5 and the factor
        collapsed to ~0.007.
        """
        goal = _goal(progress=50.0, started_days_ago=25, target_in_days=25)

        assert _MIXIN._calculate_progress_factor(goal) == pytest.approx(0.5)

    def test_ahead_of_schedule_clears_the_success_threshold(self):
        """90% done at 50% elapsed: diff=+40 percentage points, factor ~0.98."""
        goal = _goal(progress=90.0, started_days_ago=25, target_in_days=25)

        factor = _MIXIN._calculate_progress_factor(goal)

        assert factor > 0.7
        assert "Ahead of schedule" in _MIXIN._identify_success_factors(goal, [], factor, 0.9)

    def test_ahead_of_schedule_goal_is_not_flagged_behind_schedule(self):
        """The mirror of the above — the risk factor must not fire for a leader."""
        goal = _goal(progress=90.0, started_days_ago=25, target_in_days=25)

        factor = _MIXIN._calculate_progress_factor(goal)
        risks = _MIXIN._identify_risk_factors(goal, [], factor, 0.9)

        assert not any("Behind schedule" in risk for risk in risks)

    def test_behind_schedule_goal_is_still_flagged(self):
        """Negative control: the risk factor must remain reachable."""
        goal = _goal(progress=10.0, started_days_ago=25, target_in_days=25)

        factor = _MIXIN._calculate_progress_factor(goal)
        risks = _MIXIN._identify_risk_factors(goal, [], factor, 0.9)

        assert factor < 0.4
        assert any("Behind schedule" in risk for risk in risks)


class TestMomentumFactor:
    def test_momentum_uses_percent_per_day(self):
        """50% over 25 days = 2%/day; ``/100`` turns that into 0.02 of the goal.

        The raw fraction produced 0.5/25/100 = 0.0002 — momentum was a 100x
        under-count and contributed nothing to the weighted probability.
        """
        goal = _goal(progress=50.0, started_days_ago=25)

        assert _MIXIN._calculate_momentum_factor(goal, [], 30) == pytest.approx(0.02)


class TestPredictCompletionDate:
    def test_completed_goal_short_circuits_to_today(self):
        """The ``>= 100`` guard was unreachable against a value capped at 1.0."""
        goal = _goal(progress=100.0, started_days_ago=100, target_in_days=30)

        assert _MIXIN._predict_completion_date(goal, 0.5, 0.5) == date.today()

    def test_prediction_is_not_inflated_a_hundredfold(self):
        """40% in 20 days = 2%/day. Momentum 0.5 keeps the rate at 2.0, so the
        remaining 60 points need 30 days, plus int(30 * 0.5 * 0.5) = 7 buffer.

        Before the fix: remaining was 100 - 0.4 = 99.6 against a rate of 0.02,
        which predicted ~6225 days out — roughly 17 years.
        """
        goal = _goal(progress=40.0, started_days_ago=20)

        predicted = _MIXIN._predict_completion_date(goal, 0.5, 0.5)

        assert predicted == date.today() + timedelta(days=37)

    def test_unlikely_goal_still_predicts_nothing(self):
        """Negative control: the low-probability guard is unaffected."""
        goal = _goal(progress=40.0, started_days_ago=20)

        assert _MIXIN._predict_completion_date(goal, 0.2, 0.5) is None


class TestSuccessFactors:
    def test_over_halfway_fires_above_fifty_percent(self):
        goal = _goal(progress=60.0, started_days_ago=10, target_in_days=10)

        assert "Over halfway to goal" in _MIXIN._identify_success_factors(goal, [], 0.5, 0.5)

    def test_over_halfway_stays_silent_below_fifty_percent(self):
        goal = _goal(progress=40.0, started_days_ago=10, target_in_days=10)

        assert "Over halfway to goal" not in _MIXIN._identify_success_factors(goal, [], 0.5, 0.5)


class TestTrend:
    def test_progress_ahead_of_schedule_reads_as_improving(self):
        """80% at 50% elapsed with a live streak. Against a 0-100 expectation,
        the raw fraction could never exceed it, so "improving" never returned.
        """
        goal = _goal(progress=80.0, started_days_ago=25, target_in_days=25)

        trend = _MIXIN._determine_trend(goal, [_habit(streak=10)], 30)

        assert trend == Trend.IMPROVING.value

    def test_progress_behind_schedule_does_not_read_as_improving(self):
        goal = _goal(progress=20.0, started_days_ago=25, target_in_days=25)

        trend = _MIXIN._determine_trend(goal, [_habit(streak=10)], 30)

        assert trend == Trend.STABLE.value
