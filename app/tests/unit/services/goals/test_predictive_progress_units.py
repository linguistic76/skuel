"""Unit-and-source guard for the goal prediction helpers.

Every comparison in ``_predictive_mixin`` is **percentage-scaled**: expected
progress is ``(elapsed / total) * 100``, the sigmoid steepness is tuned for
percentage-point differences, remaining work is ``100 - progress``, and the
momentum rate is divided by 100. All seven sites used to read
``Goal.calculate_progress()``, a **0.0-1.0 fraction**, straight into it.

That broke four behaviours: the "already complete" short-circuit, the "Over
halfway to goal" factor and ``progress_factor > 0.7`` could never fire, and
predicted dates were inflated ~100x. ``_progress_percent`` is now the one
place progress is read, and it reads ``progress_percentage`` rather than
``calculate_progress()`` — a 0.0-1.0 fraction is simply not this module's unit.

The unit *mismatch* that once separated the two readers by value — a
``current_value / target_value`` branch dividing a percent by domain units — is
fixed, and ``calculate_progress()`` reads ``progress_percentage`` too. The scale
gap is what survives, and it is the whole reason this helper exists.

So the tests come in two layers: the **unit** ones use PERCENTAGE goals, where
the two readers differ only by the factor of 100, and stay valid under either
source; the **source** ones use states the live writers in
``goals_progress_service`` actually produce.

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

    PERCENTAGE measurement deliberately — it leaves ``current_value`` and
    ``target_value`` unset, so these tests turn on the scale of the reading and
    nothing else.
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


def _measured_goal(
    *,
    measurement_type: MeasurementType,
    current_value: float,
    target_value: float,
    progress_percentage: float,
) -> Goal:
    """A goal in a state the live writers in ``goals_progress_service`` produce.

    ``current_value`` and ``progress_percentage`` disagree here — historically the
    percent-in-a-unit-field defect, and still so for legacy rows the audit script
    surfaces — which keeps the choice of reader observable on real data.
    """
    today = date.today()
    return Goal(
        uid="goal_predictive_units_measured",
        title="Live-writer state",
        user_uid=_USER,
        measurement_type=measurement_type,
        current_value=current_value,
        target_value=target_value,
        progress_percentage=progress_percentage,
        start_date=today - timedelta(days=25),
        target_date=today + timedelta(days=25),
    )


def _habit(streak: int) -> Habit:
    return Habit(
        uid=f"habit_predictive_units_{streak}",
        title="Supporting habit",
        user_uid=_USER,
        current_streak=streak,
    )


class TestProgressPercentBoundary:
    """The one place this module reads goal progress."""

    def test_reads_the_maintained_percentage(self):
        goal = _goal(progress=25.0, started_days_ago=1)

        assert _progress_percent(goal) == pytest.approx(25.0)

    def test_task_goal_partway_through_is_not_read_as_complete(self):
        """1 of 5 tasks done, on the 0-100 scale this module's arithmetic assumes.

        The guard used to assert ``calculate_progress()`` saturating at 1.0, because
        ``current_value`` then held a percent against a unit ``target_value``. That
        defect is fixed, so the two readers now agree on the *value* and differ only
        on scale — which is the mismatch that killed four behaviours here: 0.2 fed
        into ``100 - progress`` and a percentage-point sigmoid is still wrong.
        """
        goal = _measured_goal(
            measurement_type=MeasurementType.TASK_BASED,
            current_value=20.0,
            target_value=5.0,
            progress_percentage=20.0,
        )

        assert goal.calculate_progress() == pytest.approx(0.2), (
            "guard: this test is meaningless if the two readers stop differing in scale"
        )
        assert _progress_percent(goal) == pytest.approx(20.0)

    def test_completed_numeric_goal_is_not_read_as_stale(self):
        """``complete_goal`` writes only ``progress_percentage``, leaving
        ``current_value`` at whatever the last measurement was.

        The guard used to assert 0.3 — the stale ``3/10`` division. That branch is
        deleted, so a finished goal now reads 1.0 rather than a third done. The
        scale gap is what remains: 1.0 into a ``>= 100`` short-circuit never fires.
        """
        goal = _measured_goal(
            measurement_type=MeasurementType.NUMERIC,
            current_value=3.0,
            target_value=10.0,
            progress_percentage=100.0,
        )

        assert goal.calculate_progress() == pytest.approx(1.0), (
            "guard: this test is meaningless if the two readers stop differing in scale"
        )
        assert _progress_percent(goal) == pytest.approx(100.0)


class TestUnusableStoredValues:
    """Neo4j properties carry no type and vault frontmatter is copied in unchecked."""

    def test_string_percentage_does_not_raise_into_the_callers(self):
        goal = _measured_goal(
            measurement_type=MeasurementType.TASK_BASED,
            current_value=20.0,
            target_value=5.0,
            progress_percentage="40",  # type: ignore[arg-type]  # what Neo4j hands back
        )

        assert _progress_percent(goal) == pytest.approx(40.0)

    @pytest.mark.parametrize("stored", ["not a number", None, float("nan"), float("inf")])
    def test_unusable_percentage_predicts_from_zero(self, stored):
        goal = _measured_goal(
            measurement_type=MeasurementType.TASK_BASED,
            current_value=20.0,
            target_value=5.0,
            progress_percentage=stored,
        )

        assert _progress_percent(goal) == 0.0

    def test_percentage_above_one_hundred_is_clamped(self):
        """Restores the ceiling ``calculate_progress()``'s ``min(1.0, ...)`` applied."""
        goal = _goal(progress=150.0, started_days_ago=25, target_in_days=25)

        assert _progress_percent(goal) == 100.0

    def test_negative_percentage_is_clamped(self):
        """Unclamped, -40 over 25 days gives ``_calculate_momentum_factor`` a
        negative rate, and ``min(1.0, ...)`` passes it straight through as a
        negative momentum weight into the combined probability.
        """
        goal = _goal(progress=-40.0, started_days_ago=25, target_in_days=25)

        assert _progress_percent(goal) == 0.0
        assert _MIXIN._calculate_momentum_factor(goal, [], 30) == 0.0


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

    def test_task_goal_partway_through_does_not_predict_completion_today(self):
        """The consequence of the reader choice, through the public helpers.

        Reading ``calculate_progress()`` here saturates a 20%-complete goal at
        1.0, and once the ``>= 100`` guard is live that turns into a confident
        "finished today" plus "Ahead of schedule" and "Over halfway to goal".
        """
        goal = _measured_goal(
            measurement_type=MeasurementType.TASK_BASED,
            current_value=20.0,
            target_value=5.0,
            progress_percentage=20.0,
        )

        factor = _MIXIN._calculate_progress_factor(goal)

        assert _MIXIN._predict_completion_date(goal, 0.5, 0.5) != date.today()
        assert _MIXIN._identify_success_factors(goal, [], factor, 0.5) == []

    def test_completed_numeric_goal_predicts_today(self):
        """The mirror: ``complete_goal`` writes only ``progress_percentage``, so
        reading the stale division would miss a goal that is actually finished.
        """
        goal = _measured_goal(
            measurement_type=MeasurementType.NUMERIC,
            current_value=3.0,
            target_value=10.0,
            progress_percentage=100.0,
        )

        assert _MIXIN._predict_completion_date(goal, 0.5, 0.5) == date.today()

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
