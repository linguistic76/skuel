"""How a periodic note is named, reached, iconified and stepped through.

A periodic note is addressed by the period that CONTAINS a reference date, and
several surfaces need that mapping: the in-note period rail (``ui/journals/
chat_page.py``), the navbar "Notes" picker (``ui/layouts/period_notes.py``),
and any future door. Deriving the URL twice is how a quarter boundary drifts
between them, so it is derived once here — and :func:`period_step`, the
neighbour arithmetic behind every prev/next arrow, lives beside it for the same
reason: month, quarter and year all wrap at a boundary the calendar hides.

The reference date is a date INSIDE the period, never a period key — the
key-parsing direction is ``ui/journals/period_panel.py``'s job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# Narrowest first — the picker renders in this order, and the ladder reverses
# its slice of it. Matches ``PERIODIC_NOTE_KINDS`` (core/models/user_entry).
PERIOD_KINDS: tuple[str, ...] = ("daily", "weekly", "monthly", "quarterly", "yearly")

# The picker's row headings — the period NAME, distinct from the label naming
# the specific period ("Quarterly" vs "Q3 2026").
PERIOD_NAMES: dict[str, str] = {
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
    "quarterly": "Quarterly",
    "yearly": "Yearly",
}

# The rail's row headings where the picker uses a word: on a 240px sidebar the
# icon names the KIND so the text is free to name the period. Widening zoom —
# one day (sun, as "Today" wears elsewhere), a span of days, a month grid,
# three months stacked, one orbit.
PERIOD_ICONS: dict[str, str] = {
    "daily": "sun",
    "weekly": "calendar-range",
    "monthly": "calendar-days",
    "quarterly": "layers",
    "yearly": "orbit",
}


@dataclass(frozen=True)
class PeriodLink:
    """One period's note: where it lives and what to call it.

    ``label`` names the period in full and unambiguously ("Week 36",
    "September 2026", "Q3 2026") — enough on its own to tell which period an
    arrow just stepped into, across a year boundary included. ``short_label``
    is the same period at a glance ("W36", "September", "Q3") for a column
    where the row heading already supplies the kind.
    """

    kind: str
    href: str
    label: str
    short_label: str


def period_link(kind: str, ref_date: date) -> PeriodLink:
    """The note of ``kind`` whose period contains ``ref_date``.

    ``ref_date`` is any date inside the period, so a week that crosses a month
    boundary resolves to its Monday's month — the same anchor the ISO week and
    the planning panel's range already use. An unknown ``kind`` resolves to the
    yearly note rather than raising: every caller iterates ``PERIOD_KINDS``, so
    a miss here would mean a typo, not user input.
    """
    if kind == "daily":
        return PeriodLink(
            kind,
            f"/journals/daily/{ref_date.isoformat()}",
            ref_date.strftime("%a, %b %-d, %Y"),
            f"{ref_date:%b} {ref_date.day}",
        )
    if kind == "weekly":
        iso_year, iso_week, _ = ref_date.isocalendar()
        return PeriodLink(
            kind,
            f"/journals/weekly/{iso_year}/{iso_week}",
            f"Week {iso_week}",
            f"W{iso_week}",
        )
    if kind == "monthly":
        return PeriodLink(
            kind,
            f"/journals/monthly/{ref_date.year}/{ref_date.month}",
            ref_date.strftime("%B %Y"),
            ref_date.strftime("%B"),
        )
    if kind == "quarterly":
        quarter = (ref_date.month - 1) // 3 + 1
        return PeriodLink(
            kind,
            f"/journals/quarterly/{ref_date.year}/{quarter}",
            f"Q{quarter} {ref_date.year}",
            f"Q{quarter}",
        )
    return PeriodLink(
        "yearly",
        f"/journals/yearly/{ref_date.year}",
        str(ref_date.year),
        str(ref_date.year),
    )


def period_step(kind: str, ref_date: date, steps: int) -> date:
    """A date inside the period ``steps`` periods away from ``ref_date``'s.

    The return value is an *anchor*, not a period key — hand it straight to
    :func:`period_link` to name or address the neighbour. Month and quarter
    steps go through a flat period index so December→January and Q4→Q1 carry
    the year with them instead of overflowing a month number; the day and week
    steps are plain offsets, and the ISO week they land in is whatever
    :func:`period_link` reads off the shifted date.

    ``steps`` is signed: ``-1`` is the previous period, ``+1`` the next. An
    unknown ``kind`` steps years, matching :func:`period_link`'s fallback.
    """
    if kind == "daily":
        return ref_date + timedelta(days=steps)
    if kind == "weekly":
        return ref_date + timedelta(weeks=steps)
    if kind == "monthly":
        index = ref_date.year * 12 + (ref_date.month - 1) + steps
        return date(index // 12, index % 12 + 1, 1)
    if kind == "quarterly":
        index = ref_date.year * 4 + (ref_date.month - 1) // 3 + steps
        return date(index // 4, (index % 4) * 3 + 1, 1)
    return date(ref_date.year + steps, 1, 1)


__all__ = [
    "PERIOD_ICONS",
    "PERIOD_KINDS",
    "PERIOD_NAMES",
    "PeriodLink",
    "period_link",
    "period_step",
]
