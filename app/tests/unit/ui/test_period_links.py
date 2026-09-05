"""``period_link`` — the one derivation of a periodic note's URL and labels.

Two doors read it (the in-note period ladder and the calendar/Today "Notes"
picker), so a boundary that resolved differently between them would be
invisible on either page alone. These pin the boundaries.
"""

from datetime import date

import pytest

from ui.journals.period_links import PERIOD_KINDS, PERIOD_NAMES, period_link


def test_every_kind_has_a_name_and_a_link() -> None:
    """The picker iterates PERIOD_KINDS and indexes PERIOD_NAMES — a kind
    missing from either raises at render, not in review."""
    for kind in PERIOD_KINDS:
        assert kind in PERIOD_NAMES
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


def test_labels_are_long_for_the_ladder_short_for_the_picker() -> None:
    """The ladder names the period in full; the picker's row heading already
    supplies the kind, so its label drops the year."""
    link = period_link("quarterly", date(2026, 8, 2))
    assert link.label == "Q3 2026"
    assert link.short_label == "Q3"
    assert period_link("monthly", date(2026, 8, 2)).label == "August 2026"
    assert period_link("monthly", date(2026, 8, 2)).short_label == "August"
