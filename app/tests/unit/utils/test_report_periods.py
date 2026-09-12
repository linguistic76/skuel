"""The report-period vocabulary (``core/utils/report_periods.py``) and the
period-key contract it reads (``core/utils/period_keys.py``).

One resolver serves the rich context builder, the generator and the admin
snapshot, so its verdicts are pinned here once: trailing tokens end now,
calendar tokens carry a fixed end, the data cutoff never passes that end, and
an unknown token raises rather than becoming some default window.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from core.models.enums.user_entry_enums import ReportPeriodKind
from core.utils.period_keys import (
    monthly_period_key,
    monthly_period_start,
    weekly_period_key,
    weekly_period_start,
)
from core.utils.report_periods import (
    UnknownReportPeriodError,
    report_period_token,
    resolve_report_period,
)

NOW = datetime(2026, 9, 12, 10, 30, 0)


# ---------------------------------------------------------------------------
# Trailing windows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("token", "days"), [("7d", 7), ("14d", 14), ("30d", 30), ("90d", 90)])
def test_trailing_tokens_end_now_and_reach_back_their_days(token: str, days: int) -> None:
    period = resolve_report_period(token, NOW)
    assert period.kind is ReportPeriodKind.TRAILING
    assert not period.is_calendar
    assert period.end == NOW
    assert (period.end - period.start).days == days
    assert period.label == f"the last {days} days"
    # A trailing window is never partial and never closes: it ends where it was asked.
    assert period.data_cutoff(NOW) == NOW
    assert not period.is_closed(NOW)
    assert not period.is_partial_at(NOW)


# ---------------------------------------------------------------------------
# Calendar periods
# ---------------------------------------------------------------------------


def test_month_token_spans_the_calendar_month() -> None:
    period = resolve_report_period("2026-09", NOW)
    assert period.kind is ReportPeriodKind.MONTH
    assert period.is_calendar
    assert period.start == datetime(2026, 9, 1, 0, 0, 0)
    assert period.end.date() == date(2026, 9, 30)
    assert period.end > datetime(2026, 9, 30, 23, 59, 59)
    assert period.label == "September 2026"


def test_week_token_spans_monday_to_sunday_of_the_iso_week() -> None:
    period = resolve_report_period("2026-W37", NOW)
    assert period.kind is ReportPeriodKind.WEEK
    assert period.start == datetime(2026, 9, 7, 0, 0, 0)  # Monday
    assert period.end.date() == date(2026, 9, 13)  # Sunday
    assert period.label == "week 37 of 2026"


def test_data_cutoff_is_now_while_the_period_is_open_and_its_end_once_closed() -> None:
    september = resolve_report_period("2026-09", NOW)
    assert september.data_cutoff(NOW) == NOW  # the 12th: partial
    assert september.is_partial_at(september.data_cutoff(NOW))
    assert not september.is_closed(NOW)

    october_first = datetime(2026, 10, 1, 8, 0, 0)
    assert september.data_cutoff(october_first) == september.end
    assert september.is_closed(october_first)
    assert not september.is_partial_at(september.data_cutoff(october_first))


def test_a_report_counted_before_the_end_stays_partial_even_after_the_period_closes() -> None:
    """The staleness rule's premise: partiality is a fact about the CUTOFF the
    report was counted at, not about when it is looked at."""
    september = resolve_report_period("2026-09", NOW)
    counted_on_the_11th = datetime(2026, 9, 11, 9, 0, 0)
    assert september.is_partial_at(counted_on_the_11th)


def test_a_period_has_started_once_its_first_instant_has_passed() -> None:
    assert resolve_report_period("2026-09", NOW).has_started(NOW)
    assert resolve_report_period("2026-W37", NOW).has_started(NOW)
    assert not resolve_report_period("2026-10", NOW).has_started(NOW)
    assert not resolve_report_period("2026-W38", NOW).has_started(NOW)
    assert resolve_report_period("7d", NOW).has_started(NOW)


# ---------------------------------------------------------------------------
# No default
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("token", ["unknown", "", "2026", "2026-Q3", "2026-13", "2026-W99", "7"])
def test_unknown_tokens_raise_instead_of_defaulting(token: str) -> None:
    with pytest.raises(UnknownReportPeriodError):
        resolve_report_period(token, NOW)


# ---------------------------------------------------------------------------
# Tokens from a date — the calendar doors' direction
# ---------------------------------------------------------------------------


def test_period_token_names_the_period_containing_the_date() -> None:
    assert report_period_token("monthly", date(2026, 9, 12)) == "2026-09"
    assert report_period_token("weekly", date(2026, 9, 12)) == "2026-W37"
    # A week that straddles a year boundary belongs to its ISO year.
    assert report_period_token("weekly", date(2027, 1, 1)) == "2026-W53"


def test_period_token_rejects_kinds_reports_do_not_have() -> None:
    with pytest.raises(UnknownReportPeriodError):
        report_period_token("quarterly", date(2026, 9, 12))


def test_key_builders_and_parsers_round_trip() -> None:
    for day in (date(2026, 1, 1), date(2026, 9, 12), date(2026, 12, 31)):
        assert weekly_period_start(weekly_period_key(day)) is not None
        assert monthly_period_start(monthly_period_key(day)) == day.replace(day=1)
        assert resolve_report_period(weekly_period_key(day), NOW).start.date() <= day
        assert resolve_report_period(monthly_period_key(day), NOW).start.date() <= day
