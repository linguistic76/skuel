"""The URL and labels of a periodic note's period — one place, three surfaces.

A periodic note is addressed by the period that CONTAINS a reference date, and
three surfaces need that mapping: the in-note period ladder (``ui/journals/
chat_page.py``), the navbar "Notes" picker (``ui/layouts/period_notes.py``),
and any future door. Deriving the URL twice is how a quarter boundary drifts
between them, so it is derived once here.

The reference date is a date INSIDE the period, never a period key — the
key-parsing direction is ``ui/journals/period_panel.py``'s job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

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


@dataclass(frozen=True)
class PeriodLink:
    """One period's note: where it lives and what to call it.

    ``label`` names the period in full ("Week 36", "September 2026", "Q3 2026")
    — the ladder's rung text. ``short_label`` is the same period at a glance
    ("W36", "September", "Q3") for a column where the row heading already
    supplies the kind.
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
            ref_date.strftime("%A, %B %d, %Y"),
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


__all__ = ["PERIOD_KINDS", "PERIOD_NAMES", "PeriodLink", "period_link"]
