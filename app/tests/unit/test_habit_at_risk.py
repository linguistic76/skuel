"""The one at-risk definition — ``habit_overdue`` and ``habit_at_risk``.

An active habit is at risk when it is overdue for its own cadence, or when its
adherence is under ``HabitAtRisk.RATE_THRESHOLD`` and the measured span asked
for at least ``HabitAtRisk.MIN_EXPECTED`` completions. Ruled 2026-10-02.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.constants import HabitAtRisk
from core.models.enums import EntityStatus, RecurrencePattern
from core.models.habit.adherence import habit_at_risk, habit_overdue, measured_span_expected

TODAY = date(2026, 10, 2)  # a Friday


def _days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def _overdue(pattern: str | None, *, done: int | None, created: int | None = 400, target=None):
    return habit_overdue(
        pattern,
        target,
        last_completed_on=_days_ago(done) if done is not None else None,
        created_on=_days_ago(created) if created is not None else None,
        today=TODAY,
    )


@pytest.mark.parametrize(
    ("pattern", "on_time", "late"),
    [
        (RecurrencePattern.DAILY, 1, 2),
        (None, 1, 2),
        (RecurrencePattern.WEEKLY, 7, 8),
        (RecurrencePattern.BIWEEKLY, 14, 15),
        (RecurrencePattern.MONTHLY, 31, 32),
        (RecurrencePattern.QUARTERLY, 92, 93),
        (RecurrencePattern.YEARLY, 366, 367),
    ],
)
def test_a_habit_is_overdue_once_more_than_its_period_has_passed(
    pattern: str | None, on_time: int, late: int
) -> None:
    """Today is still open: a daily habit done yesterday is on time, one done the day before is not."""
    assert not _overdue(pattern, done=on_time)
    assert _overdue(pattern, done=late)


def test_a_weekdays_habit_is_late_only_for_a_weekday_it_missed() -> None:
    """Friday → Monday skips no weekday; Thursday → Monday skips Friday."""
    monday = date(2026, 10, 5)
    friday, thursday = date(2026, 10, 2), date(2026, 10, 1)
    weekdays = RecurrencePattern.WEEKDAYS
    on_time = habit_overdue(weekdays, None, last_completed_on=friday, created_on=None, today=monday)
    late = habit_overdue(weekdays, None, last_completed_on=thursday, created_on=None, today=monday)
    assert not on_time
    assert late


def test_a_weekends_habit_is_late_only_for_a_weekend_day_it_missed() -> None:
    """Sunday → the next Saturday skips no weekend day; Saturday → Monday skips Sunday."""
    weekends = RecurrencePattern.WEEKENDS
    sunday, saturday = date(2026, 10, 4), date(2026, 10, 3)
    next_saturday, monday = date(2026, 10, 10), date(2026, 10, 5)
    on_time = habit_overdue(
        weekends, None, last_completed_on=sunday, created_on=None, today=next_saturday
    )
    late = habit_overdue(weekends, None, last_completed_on=saturday, created_on=None, today=monday)
    assert not on_time
    assert late


def test_a_custom_habit_may_go_seven_over_its_target_days_rounded_up() -> None:
    """Three a week: three days between completions is on time, four is late."""
    assert not _overdue(RecurrencePattern.CUSTOM, done=3, target=3)
    assert _overdue(RecurrencePattern.CUSTOM, done=4, target=3)
    assert not _overdue(RecurrencePattern.CUSTOM, done=300, target=None)


def test_a_one_time_habit_is_never_overdue() -> None:
    assert not _overdue(RecurrencePattern.NONE, done=300)


def test_a_never_completed_habit_counts_from_the_day_before_its_creation() -> None:
    """Its first period counts: created today is on time, a daily created yesterday missed a day."""
    assert not _overdue(RecurrencePattern.DAILY, done=None, created=0)
    assert _overdue(RecurrencePattern.DAILY, done=None, created=1)
    assert not _overdue(RecurrencePattern.WEEKLY, done=None, created=6)
    assert _overdue(RecurrencePattern.WEEKLY, done=None, created=7)


def test_with_no_completion_and_no_creation_day_there_is_nothing_to_be_late_against() -> None:
    assert not _overdue(RecurrencePattern.DAILY, done=None, created=None)


def test_a_completion_stamped_in_the_future_is_not_late() -> None:
    assert not _overdue(RecurrencePattern.DAILY, done=-3)


def _at_risk(
    *,
    rate: float | None,
    done: int | None = 1,
    created: int = 60,
    status: str = EntityStatus.ACTIVE,
    pattern: str = RecurrencePattern.DAILY,
) -> bool:
    return habit_at_risk(
        status,
        pattern,
        None,
        rate=rate,
        last_completed_on=_days_ago(done) if done is not None else None,
        created_on=_days_ago(created),
        today=TODAY,
    )


def test_an_overdue_active_habit_is_at_risk_whatever_its_rate() -> None:
    assert _at_risk(rate=1.0, done=3)
    assert _at_risk(rate=None, done=3)


def test_a_measured_rate_under_the_threshold_is_at_risk_on_enough_evidence() -> None:
    """Created three days ago (today included): three due days — enough."""
    assert _at_risk(rate=0.3, created=2)
    assert not _at_risk(rate=HabitAtRisk.RATE_THRESHOLD)


def test_too_little_evidence_does_not_judge_the_rate() -> None:
    """A daily habit two days old has asked for two completions — below the minimum."""
    assert not _at_risk(rate=0.0, created=1, done=0)
    assert not _at_risk(rate=0.0, created=0, done=None)


def test_no_rate_is_judged_on_lateness_alone() -> None:
    """A quarterly habit has no rate in a 30-day window; kept on time it is not at risk."""
    assert not _at_risk(rate=None, done=40, pattern=RecurrencePattern.QUARTERLY)
    assert _at_risk(rate=None, done=100, pattern=RecurrencePattern.QUARTERLY)


def test_an_inactive_habit_is_never_at_risk() -> None:
    assert not _at_risk(rate=0.0, done=30, status=EntityStatus.PAUSED)
    assert not _at_risk(rate=0.0, done=30, status=EntityStatus.ARCHIVED)


def test_the_stored_status_string_reads_the_same_as_the_enum() -> None:
    assert _at_risk(rate=None, done=3, status="active")


def test_the_evidence_is_counted_over_the_span_the_rate_measures() -> None:
    """The window cut short at creation: 30 for an old daily habit, 3 for one created two days ago."""
    daily = RecurrencePattern.DAILY
    assert measured_span_expected(daily, None, created_on=_days_ago(400), today=TODAY) == 30
    assert measured_span_expected(daily, None, created_on=_days_ago(2), today=TODAY) == 3
    assert measured_span_expected(daily, None, created_on=_days_ago(-1), today=TODAY) == 0
    quarterly = RecurrencePattern.QUARTERLY
    assert measured_span_expected(quarterly, None, created_on=None, today=TODAY) == 0
