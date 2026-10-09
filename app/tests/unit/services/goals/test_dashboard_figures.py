"""The goal progress dashboard's three derived figures (F8-4, ruling Q6).

``needs_more_tasks`` reads the contribution tally, ``habit_support_contribution``
is the essentiality-weighted mean adherence of the goal's supporting habits, and
``knowledge_mastery_contribution`` is the share of required knowledge mastered —
each over the one read made for the goal, never over the neighbourhood's size.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.constants import GoalDashboard, HabitEssentialityWeight
from core.models.enums import RecurrencePattern
from core.models.enums.goal_enums import HabitEssentiality
from core.models.habit.habit import Habit
from core.ports.query_types import RequiredKnowledgeTally, SupportingHabitWindow
from core.services.goals.dashboard_figures import (
    habit_support_contribution,
    knowledge_mastery_contribution,
    needs_more_tasks,
)
from core.utils.timestamp_helpers import today_in

ZONE = ZoneInfo("UTC")
TODAY = today_in(ZONE)
SPAN_DAYS = 4  # a habit started three days ago is measured over four days


def _habit(uid: str, pattern: RecurrencePattern, *, age_days: int = SPAN_DAYS - 1) -> Habit:
    return Habit(
        uid=uid,
        user_uid="user_figures",
        title=uid,
        recurrence_pattern=pattern,
        created_at=datetime.combine(TODAY - timedelta(days=age_days), time(12), tzinfo=ZONE),
    )


def _window(habit: Habit, essentiality: str | None, kept_days: int) -> SupportingHabitWindow:
    """``kept_days`` completions, one per day counting back from today."""
    return SupportingHabitWindow(
        habit=habit,
        essentiality=essentiality,
        completion_stamps=[
            datetime.combine(TODAY - timedelta(days=n), time(9), tzinfo=ZONE)
            for n in range(kept_days)
        ],
    )


class TestNeedsMoreTasks:
    def test_fewer_counting_contributions_than_the_threshold(self) -> None:
        tally = {
            "total_contributions": GoalDashboard.MIN_COUNTING_CONTRIBUTIONS - 1,
            "completed_contributions": 0,
        }
        assert needs_more_tasks(tally) is True

    def test_the_threshold_itself_is_enough(self) -> None:
        tally = {
            "total_contributions": GoalDashboard.MIN_COUNTING_CONTRIBUTIONS,
            "completed_contributions": 0,
        }
        assert needs_more_tasks(tally) is False


class TestHabitSupportContribution:
    def test_one_essential_habit_kept_half_the_time_reads_fifty(self) -> None:
        rows = [_window(_habit("h", RecurrencePattern.DAILY), "essential", SPAN_DAYS // 2)]
        assert habit_support_contribution(rows, ZONE) == pytest.approx(50.0)

    def test_the_mean_is_weighted_by_essentiality(self) -> None:
        """An essential habit fully kept and an optional one never kept: 1.0 at weight 1
        and 0.0 at weight 0.25 is 80, not the unweighted 50."""
        rows = [
            _window(_habit("essential", RecurrencePattern.DAILY), "essential", SPAN_DAYS),
            _window(_habit("optional", RecurrencePattern.DAILY), "optional", 0),
        ]
        expected = HabitEssentialityWeight.ESSENTIAL / (
            HabitEssentialityWeight.ESSENTIAL + HabitEssentialityWeight.OPTIONAL
        )
        assert habit_support_contribution(rows, ZONE) == pytest.approx(expected * 100)

    def test_a_habit_with_no_rate_yet_is_left_out_of_both_sides(self) -> None:
        """A weekly habit started today has nothing due: it neither drags the mean
        down nor pads the denominator."""
        rows = [
            _window(_habit("kept", RecurrencePattern.DAILY), "essential", SPAN_DAYS // 2),
            _window(_habit("new", RecurrencePattern.WEEKLY, age_days=0), "essential", 0),
        ]
        assert habit_support_contribution(rows, ZONE) == pytest.approx(50.0)

    def test_no_measurable_habit_reads_zero(self) -> None:
        unmeasurable = [
            _window(_habit("new", RecurrencePattern.WEEKLY, age_days=0), "essential", 0)
        ]
        assert habit_support_contribution(unmeasurable, ZONE) == 0.0
        assert habit_support_contribution([], ZONE) == 0.0

    def test_an_edge_without_a_tier_weighs_as_supporting(self) -> None:
        """The tier every link door writes by default, so an untagged edge reads as
        it would have been written."""
        rows = [
            _window(_habit("untagged", RecurrencePattern.DAILY), None, SPAN_DAYS),
            _window(_habit("essential", RecurrencePattern.DAILY), "essential", 0),
        ]
        expected = HabitEssentialityWeight.SUPPORTING / (
            HabitEssentialityWeight.SUPPORTING + HabitEssentialityWeight.ESSENTIAL
        )
        assert habit_support_contribution(rows, ZONE) == pytest.approx(expected * 100)


class TestKnowledgeMasteryContribution:
    def test_half_of_the_required_knowledge_mastered_reads_fifty(self) -> None:
        tally = RequiredKnowledgeTally(required_knowledge=2, mastered_knowledge=1)
        assert knowledge_mastery_contribution(tally) == pytest.approx(50.0)

    def test_a_goal_that_requires_nothing_reads_zero(self) -> None:
        tally = RequiredKnowledgeTally(required_knowledge=0, mastered_knowledge=0)
        assert knowledge_mastery_contribution(tally) == 0.0


class TestHabitEssentialityWeights:
    def test_each_tier_has_its_constant(self) -> None:
        assert HabitEssentiality.ESSENTIAL.get_weight() == HabitEssentialityWeight.ESSENTIAL
        assert HabitEssentiality.CRITICAL.get_weight() == HabitEssentialityWeight.CRITICAL
        assert HabitEssentiality.SUPPORTING.get_weight() == HabitEssentialityWeight.SUPPORTING
        assert HabitEssentiality.OPTIONAL.get_weight() == HabitEssentialityWeight.OPTIONAL

    def test_the_tiers_are_ordered(self) -> None:
        weights = [tier.get_weight() for tier in HabitEssentiality]
        assert weights == sorted(weights, reverse=True)
        assert len(set(weights)) == len(weights)

    @pytest.mark.parametrize("stored", [None, "bogus", "supporting"])
    def test_an_absent_or_unknown_stored_tier_reads_as_supporting(self, stored: str | None) -> None:
        assert HabitEssentiality.from_stored(stored) is HabitEssentiality.SUPPORTING

    def test_a_stored_tier_reads_as_itself(self) -> None:
        assert HabitEssentiality.from_stored("essential") is HabitEssentiality.ESSENTIAL
