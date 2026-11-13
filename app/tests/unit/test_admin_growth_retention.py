"""Growth and retention on ``/admin/analytics``: the month keys, the two tables, the cards.

The graph reads behind these are held in ``tests/integration/test_presence_record.py``;
here the rows are given, and the arithmetic and the rendering are what is tested.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from core.orchestrator.admin_orchestrator import AdminOrchestrator
from core.ports.query_types import (
    AccountMonthRow,
    AdminAnalyticsData,
    GrowthMonth,
    GrowthReport,
    PresenceMonthRow,
    RetentionMonth,
    RetentionReport,
)
from core.services.admin_stats_service import (
    ANALYTICS_MONTHS,
    DAYS_ACTIVE_COUNTED_FROM,
    build_growth_report,
    build_retention_report,
)
from core.utils.month_keys import day_key, month_key, shift_month, trailing_months
from core.utils.result_simplified import Errors, Result
from ui.admin.views import AdminAnalyticsComponents

# ----------------------------------------------------------------------------
# Month keys
# ----------------------------------------------------------------------------


def test_month_and_day_are_read_in_utc() -> None:
    late_in_tokyo = datetime(2026, 12, 1, 8, 30, tzinfo=timezone(timedelta(hours=9)))
    assert month_key(late_in_tokyo) == "2026-11"
    assert day_key(late_in_tokyo) == "2026-11-30"
    assert month_key(datetime(2026, 11, 30, 23, 59, tzinfo=UTC)) == "2026-11"
    # A naive instant is already UTC: the process clock is pinned.
    assert day_key(datetime(2026, 12, 1, 0, 0)) == "2026-12-01"


def test_shift_month_crosses_years() -> None:
    assert shift_month("2026-12", 1) == "2027-01"
    assert shift_month("2026-01", -1) == "2025-12"
    assert shift_month("2026-11", 0) == "2026-11"
    assert shift_month("2026-03", -14) == "2025-01"


def test_trailing_months_end_at_the_current_one() -> None:
    months = trailing_months("2026-02", 12)
    assert len(months) == 12
    assert months[0] == "2025-03"
    assert months[-1] == "2026-02"
    assert months == sorted(months)


# ----------------------------------------------------------------------------
# The typed rows
# ----------------------------------------------------------------------------


def test_rows_are_frozen() -> None:
    line = RetentionMonth(
        month="2026-10",
        present=3,
        returned=2,
        next_month_in_progress=True,
        days_active=9,
        days_active_is_floor=False,
    )
    with pytest.raises(AttributeError):
        line.present = 4  # type: ignore[misc]
    with pytest.raises(AttributeError):
        GrowthMonth(month="2026-10", new_accounts=1, change=1, total=1).total = 2  # type: ignore[misc]


def test_retention_rate() -> None:
    assert RetentionMonth("2026-09", 3, 2, False, 0, False).rate == pytest.approx(2 / 3)
    assert RetentionMonth("2026-09", 3, 0, False, 0, False).rate == 0.0
    # No one was present: there is no rate, and no division.
    assert RetentionMonth("2026-09", 0, 0, False, 0, False).rate is None
    # The month after has not begun.
    assert RetentionMonth("2026-11", 3, None, False, 0, False).rate is None


# ----------------------------------------------------------------------------
# Growth
# ----------------------------------------------------------------------------


def test_growth_with_no_accounts() -> None:
    report = build_growth_report([], "2026-11")
    assert len(report.months) == ANALYTICS_MONTHS
    assert all((m.new_accounts, m.change, m.total) == (0, 0, 0) for m in report.months)
    assert (report.total_accounts, report.deactivated_accounts) == (0, 0)
    assert (report.new_this_month, report.change_this_month) == (0, 0)


def test_growth_running_total_and_change() -> None:
    rows = [
        AccountMonthRow(month=None, new_accounts=1, deactivated=0),  # no creation stamp
        AccountMonthRow(month="2024-05", new_accounts=4, deactivated=1),  # before the window
        AccountMonthRow(month="2026-02", new_accounts=2, deactivated=0),
        AccountMonthRow(month="2026-07", new_accounts=1, deactivated=1),
        AccountMonthRow(month="2026-11", new_accounts=3, deactivated=0),
    ]
    report = build_growth_report(rows, "2026-11")
    by_month = {m.month: m for m in report.months}

    assert [m.month for m in report.months] == trailing_months("2026-11", 12)
    # Accounts from before the window, and those with no stamp, open the total.
    assert by_month["2025-12"].total == 5
    assert (by_month["2026-02"].new_accounts, by_month["2026-02"].change) == (2, 2)
    assert by_month["2026-02"].total == 7
    assert (by_month["2026-03"].new_accounts, by_month["2026-03"].change) == (0, -2)
    assert by_month["2026-07"].total == 8
    assert (by_month["2026-11"].new_accounts, by_month["2026-11"].change) == (3, 3)
    assert by_month["2026-11"].total == 11

    assert report.total_accounts == 11
    assert report.deactivated_accounts == 2
    assert report.accounts_not_deactivated == 9
    assert (report.new_this_month, report.change_this_month) == (3, 3)


def test_growth_change_of_the_first_line_reads_the_month_before_the_window() -> None:
    rows = [
        AccountMonthRow(month="2025-11", new_accounts=5, deactivated=0),
        AccountMonthRow(month="2025-12", new_accounts=2, deactivated=0),
    ]
    first = build_growth_report(rows, "2026-11").months[0]
    assert (first.month, first.new_accounts, first.change, first.total) == ("2025-12", 2, -3, 7)


# ----------------------------------------------------------------------------
# Retention
# ----------------------------------------------------------------------------


def test_retention_with_no_presence() -> None:
    report = build_retention_report([], "2026-11")
    assert len(report.months) == ANALYTICS_MONTHS
    assert all(m.present == 0 for m in report.months)
    assert all(m.rate is None for m in report.months)
    assert report.months[-1].returned is None
    assert report.months[-2].returned == 0
    assert report.present_this_month == 0


def test_retention_lines() -> None:
    rows = [
        PresenceMonthRow(month="2026-09", present=3, returned=2, days_active=12),
        PresenceMonthRow(month="2026-10", present=2, returned=1, days_active=3),
        PresenceMonthRow(month="2026-11", present=1, returned=0, days_active=1),
    ]
    report = build_retention_report(rows, "2026-11")
    september, october, november = report.months[-3:]

    assert (september.present, september.returned, september.next_month_in_progress) == (
        3,
        2,
        False,
    )
    # October is measured against November, which is still running.
    assert (october.present, october.returned, october.next_month_in_progress) == (2, 1, True)
    # November has no month after it yet, whatever the read returned for it.
    assert (november.present, november.returned, november.next_month_in_progress) == (
        1,
        None,
        False,
    )
    assert report.present_this_month == 1
    assert (september.days_active, october.days_active, november.days_active) == (12, 3, 1)
    assert september.mean_days_active == pytest.approx(4.0)
    assert october.mean_days_active == pytest.approx(1.5)


def test_days_active_with_no_one_present() -> None:
    report = build_retention_report([], "2026-11")
    assert all(m.days_active == 0 for m in report.months)
    # No one was present: there is no mean, and no division.
    assert all(m.mean_days_active is None for m in report.months)
    html = to_xml(AdminAnalyticsComponents.render_retention(report))
    assert "Days active" in html
    assert "≥" not in html.split("</table>")[0]


def test_days_active_is_a_floor_before_every_day_was_counted() -> None:
    months = trailing_months("2027-02", 4)  # 2026-11 .. 2027-02
    report = build_retention_report([PresenceMonthRow(m, 2, 1, 9) for m in months], "2027-02")
    november, december, january, february = report.months[-4:]
    assert DAYS_ACTIVE_COUNTED_FROM == "2026-12"
    assert november.days_active_is_floor
    assert not (
        december.days_active_is_floor
        or january.days_active_is_floor
        or february.days_active_is_floor
    )
    table = to_xml(AdminAnalyticsComponents.render_retention(report)).split("</table>")[0]
    assert table.count("≥ 4.5") == 1
    assert table.count(">4.5<") == 3


# ----------------------------------------------------------------------------
# The cards
# ----------------------------------------------------------------------------


def _page(**fields: object) -> AdminAnalyticsData:
    base: dict[str, object] = {
        "growth": build_growth_report([], "2026-11"),
        "retention": build_retention_report([], "2026-11"),
        "roles": {"total": 0, "admins": 0, "teachers": 0, "members": 0, "registered": 0},
        "activity": {"tasks": 0, "habits": 0, "goals": 0},
        "search_gaps": (),
        "search_event_total": 0,
    }
    return AdminAnalyticsData(**{**base, **fields})  # type: ignore[arg-type]


def _html(data: AdminAnalyticsData) -> str:
    return to_xml(AdminAnalyticsComponents.render_analytics_dashboard(data))


def test_cards_in_order_growth_and_retention_first() -> None:
    html = _html(_page())
    titles = [
        "Growth",
        "Retention",
        "User Distribution",
        "Activity Totals (all time)",
        "Search Gaps",
    ]
    positions = [html.index(f">{title}") for title in titles]
    assert positions == sorted(positions)
    assert "Activity Statistics (30 days)" not in html
    assert "Active Habits" not in html and "Active Goals" not in html
    assert html.count("Months are UTC") == 1
    assert html.count("Months and days are UTC") == 1


def test_empty_graph_renders_twelve_lines_of_zeros() -> None:
    html = _html(_page())
    assert "0 accounts" in html
    assert "0 users present this month" in html
    assert "2025-12" in html and "2026-11" in html
    assert "month not over" in html
    # No one present: a count, and no rate.
    assert "0 of 0" in html
    assert "%)" not in html


def test_one_month_of_history() -> None:
    growth = build_growth_report([AccountMonthRow("2026-11", 1, 0)], "2026-11")
    retention = build_retention_report([PresenceMonthRow("2026-11", 1, 0, 1)], "2026-11")
    html = _html(_page(growth=growth, retention=retention))
    assert "1 account ·" in html
    assert "1 new this month (+1 on last month)" in html
    assert "1 user present this month" in html


def test_twelve_months_of_history() -> None:
    months = trailing_months("2026-11", 12)
    growth = build_growth_report(
        [AccountMonthRow(month, index + 1, 0) for index, month in enumerate(months)], "2026-11"
    )
    retention = build_retention_report(
        [PresenceMonthRow(month, 3, 2, 14) for month in months], "2026-11"
    )
    html = _html(_page(growth=growth, retention=retention))

    assert "78 accounts" in html
    for month in months:
        assert html.count(month) == 2  # one line in each table
    # Newest month first in both tables.
    assert html.index("2026-11") < html.index("2026-10") < html.index("2025-12")
    assert html.count("2 of 3 (67%)") == 11
    assert html.count("2 of 3 (67%), so far") == 1
    assert html.count("month not over") == 1


def test_a_failed_read_shows_its_cards_error_and_not_zeros() -> None:
    html = _html(_page(growth=None, retention=None, roles=None, activity=None))
    for message in (
        "Growth figures unavailable",
        "Retention figures unavailable",
        "User distribution unavailable",
        "Activity totals unavailable",
    ):
        assert message in html
    assert "0 accounts" not in html
    assert "present this month" not in html
    assert "Months are UTC" not in html
    assert ">Tasks<" not in html

    # One card's failure leaves the others' figures standing.
    html = _html(_page(retention=None))
    assert "Retention figures unavailable" in html
    assert "0 accounts" in html
    assert html.count("Months are UTC") == 1


# ----------------------------------------------------------------------------
# The orchestrator
# ----------------------------------------------------------------------------


def _down(operation: str) -> Result[object]:
    return Result.fail(Errors.database(operation=operation, message="down"))


@pytest.mark.anyio
async def test_each_failed_read_is_none_and_the_rest_stand() -> None:
    admin_stats = MagicMock()
    admin_stats.get_growth = AsyncMock(return_value=_down("get_accounts_by_signup_month"))
    admin_stats.get_retention = AsyncMock(
        return_value=Result.ok(build_retention_report([], "2026-11"))
    )
    admin_stats.get_user_role_counts = AsyncMock(return_value=_down("get_user_role_counts"))
    admin_stats.get_activity_entity_counts = AsyncMock(
        return_value=Result.ok({"tasks": 4, "habits": 2, "goals": 1})
    )
    admin_stats.get_search_gaps = AsyncMock(return_value=Result.ok([]))
    admin_stats.get_search_event_total = AsyncMock(return_value=Result.ok(7))

    data = await AdminOrchestrator(
        user_service=MagicMock(), admin_stats=admin_stats
    ).get_analytics_data()

    assert data.growth is None
    assert data.roles is None
    assert isinstance(data.retention, RetentionReport)
    assert data.activity == {"tasks": 4, "habits": 2, "goals": 1}
    assert data.search_gaps == ()
    assert data.search_event_total == 7

    html = _html(data)
    assert "Growth figures unavailable" in html
    assert "User distribution unavailable" in html
    assert "Retention figures unavailable" not in html


def test_growth_report_properties_on_an_empty_window() -> None:
    report = GrowthReport(total_accounts=0, deactivated_accounts=0, months=())
    assert (report.new_this_month, report.change_this_month) == (0, 0)
    assert RetentionReport(months=()).present_this_month == 0
