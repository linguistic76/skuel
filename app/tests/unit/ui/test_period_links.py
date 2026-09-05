"""``period_link`` / ``period_step`` — one derivation of a periodic note's
URL, labels and neighbours.

Two doors read them (the in-note period rail and the navbar "Notes" picker), so
a boundary that resolved differently between them would be invisible on either
page alone. These pin the boundaries.
"""

from datetime import date

import pytest

from ui.journals.period_links import (
    PERIOD_ICONS,
    PERIOD_KINDS,
    PERIOD_NAMES,
    period_link,
    period_step,
)


def test_every_kind_has_a_name_and_a_link() -> None:
    """The picker iterates PERIOD_KINDS and indexes PERIOD_NAMES — a kind
    missing from either raises at render, not in review."""
    for kind in PERIOD_KINDS:
        assert kind in PERIOD_NAMES
        assert kind in PERIOD_ICONS
        link = period_link(kind, date(2026, 8, 2))
        assert link.kind == kind
        assert link.href.startswith("/journals/")
        assert link.label and link.short_label


@pytest.mark.parametrize(
    ("kind", "href"),
    [
        ("daily", "/journals/daily/2026-08-02"),
        ("weekly", "/journals/weekly/2026/31"),
        ("monthly", "/journals/monthly/2026/8"),
        ("quarterly", "/journals/quarterly/2026/3"),
        ("yearly", "/journals/yearly/2026"),
    ],
)
def test_href_matches_the_route_each_kind_is_served_by(kind: str, href: str) -> None:
    assert period_link(kind, date(2026, 8, 2)).href == href


def test_quarter_boundaries() -> None:
    """The month→quarter fold is the arithmetic most likely to drift: each
    quarter's first and last month must land on the same quarter number."""
    for quarter, (first, last) in enumerate([(1, 3), (4, 6), (7, 9), (10, 12)], start=1):
        assert period_link("quarterly", date(2026, first, 1)).href.endswith(f"/{quarter}")
        assert period_link("quarterly", date(2026, last, 28)).href.endswith(f"/{quarter}")


def test_iso_week_uses_the_iso_year_not_the_calendar_year() -> None:
    """2026-12-31 is a Thursday in ISO week 53 of 2026; 2027-01-01 (Friday) is
    still week 53 of 2026 — a calendar-year href would mint week 53 of 2027,
    a period no parser accepts as that week."""
    assert period_link("weekly", date(2027, 1, 1)).href == "/journals/weekly/2026/53"


def test_labels_are_full_for_the_rail_short_for_the_picker() -> None:
    """The rail names the period unambiguously — an arrow that crossed a year
    must say so. The picker's row heading already supplies the kind, so its
    label drops the year."""
    link = period_link("quarterly", date(2026, 8, 2))
    assert link.label == "Q3 2026"
    assert link.short_label == "Q3"
    assert period_link("monthly", date(2026, 8, 2)).label == "August 2026"
    assert period_link("monthly", date(2026, 8, 2)).short_label == "August"


def test_daily_label_fits_a_sidebar_row_and_still_carries_the_year() -> None:
    """The rail renders the label in a ~150px column, so the daily label is
    abbreviated — but never to the point of dropping the year, which is the
    one thing a stepped-into period must state."""
    assert period_link("daily", date(2026, 8, 2)).label == "Sun, Aug 2, 2026"


# ---------------------------------------------------------------------------
# period_step — the arithmetic behind every prev/next arrow
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "steps", "href"),
    [
        # Plain offsets.
        ("daily", -1, "/journals/daily/2026-08-01"),
        ("daily", 1, "/journals/daily/2026-08-03"),
        ("weekly", -1, "/journals/weekly/2026/30"),
        ("weekly", 1, "/journals/weekly/2026/32"),
        ("monthly", -1, "/journals/monthly/2026/7"),
        ("monthly", 1, "/journals/monthly/2026/9"),
        ("quarterly", -1, "/journals/quarterly/2026/2"),
        ("quarterly", 1, "/journals/quarterly/2026/4"),
        ("yearly", -1, "/journals/yearly/2025"),
        ("yearly", 1, "/journals/yearly/2027"),
    ],
)
def test_a_step_lands_in_the_neighbouring_period(kind: str, steps: int, href: str) -> None:
    """The anchor a step returns is fed straight back to ``period_link``, so
    the pin is on the URL the arrow actually points at."""
    assert period_link(kind, period_step(kind, date(2026, 8, 2), steps)).href == href


@pytest.mark.parametrize(
    ("kind", "start", "steps", "href"),
    [
        # The year boundary each kind wraps at — the arithmetic that a naive
        # month/quarter ±1 gets wrong by overflowing the number instead of the
        # year.
        ("monthly", date(2026, 1, 15), -1, "/journals/monthly/2025/12"),
        ("monthly", date(2026, 12, 15), 1, "/journals/monthly/2027/1"),
        ("quarterly", date(2026, 1, 15), -1, "/journals/quarterly/2025/4"),
        ("quarterly", date(2026, 11, 15), 1, "/journals/quarterly/2027/1"),
        ("daily", date(2026, 1, 1), -1, "/journals/daily/2025-12-31"),
        ("weekly", date(2027, 1, 4), -1, "/journals/weekly/2026/53"),
    ],
)
def test_a_step_across_a_year_boundary_carries_the_year(
    kind: str, start: date, steps: int, href: str
) -> None:
    assert period_link(kind, period_step(kind, start, steps)).href == href


def test_a_step_from_a_month_end_does_not_overflow_the_short_month() -> None:
    """A monthly step anchors on the 1st, so stepping from the 31st into a
    30-day month is a month away, not a ``day is out of range`` crash."""
    assert period_link("monthly", period_step("monthly", date(2026, 3, 31), 1)).href == (
        "/journals/monthly/2026/4"
    )


def test_stepping_is_reversible_for_every_kind() -> None:
    """Back-then-forward returns to the period you started in — the property
    that makes an arrow pair safe to hold down."""
    origin = date(2026, 8, 2)
    for kind in PERIOD_KINDS:
        there = period_step(kind, origin, 1)
        back = period_step(kind, there, -1)
        assert period_link(kind, back).href == period_link(kind, origin).href
