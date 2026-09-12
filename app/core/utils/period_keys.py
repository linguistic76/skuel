"""The period-key contract — how a calendar period is spelled as a string.

One key form per period kind, shared by every surface that addresses a period
by name rather than by a date inside it: the periodic notes' persistence
contract (``ensure_periodic_note``), the planning panel's key parsing, and the
activity reports' calendar-aligned ``time_period`` tokens.

    weekly    ``{year}-W{week:02d}``   ISO week (``2026-W37``)
    monthly   ``{year}-{month:02d}``   calendar month (``2026-09``)
    quarterly ``{year}-Q{quarter}``    (``2026-Q3``)
    yearly    ``{year}``               (``2026``)

Parsers accept the canonical spelling ONLY and return ``None`` for anything
else — a weekly key handed to the monthly parser, a daily date, a padded or
unpadded variant (``02026-09``, ``2026-W037``, ``2026-9``), junk — so callers
degrade to "no period" rather than guess one, and two spellings can never name
one period (the report cooldown and the period door compare stored tokens
exactly). The builders are the inverse for the two kinds reports speak.

Reference date → key is the direction here; a date INSIDE a period → its note's
URL and label is ``ui/journals/period_links.py``'s.
"""

from __future__ import annotations

import re
from datetime import date

_WEEKLY_KEY = re.compile(r"^(\d{4})-W(\d{2})$")
_MONTHLY_KEY = re.compile(r"^(\d{4})-(\d{2})$")
_QUARTERLY_KEY = re.compile(r"^(\d{4})-Q([1-4])$")
_YEARLY_KEY = re.compile(r"^(\d{4})$")


def weekly_period_start(period_key: str) -> date | None:
    """Monday of the ISO week a weekly period key names (``2026-W32``)."""
    match = _WEEKLY_KEY.match(period_key)
    if match is None:
        return None
    try:
        return date.fromisocalendar(int(match[1]), int(match[2]), 1)
    except ValueError:
        return None


def monthly_period_start(period_key: str) -> date | None:
    """First day of the month a monthly period key names (``2026-08``).

    A weekly key (``2026-W32``) and a daily key (``2026-08-03``) are both
    rejected, never coerced.
    """
    match = _MONTHLY_KEY.match(period_key)
    if match is None:
        return None
    try:
        return date(int(match[1]), int(match[2]), 1)
    except ValueError:
        return None


def quarterly_period_start(period_key: str) -> date | None:
    """First day of the quarter a quarterly period key names (``2026-Q3``)."""
    match = _QUARTERLY_KEY.match(period_key)
    if match is None:
        return None
    try:
        return date(int(match[1]), 3 * (int(match[2]) - 1) + 1, 1)
    except ValueError:
        return None


def yearly_period_start(period_key: str) -> date | None:
    """January 1 of the year a yearly period key names (``2026``).

    Only a bare four-digit year parses — ``2026-W32``, ``2026-08``, ``2026-Q3``
    and ``2026-08-03`` are all rejected.
    """
    match = _YEARLY_KEY.match(period_key)
    if match is None:
        return None
    try:
        return date(int(match[1]), 1, 1)
    except ValueError:
        return None


def weekly_period_key(ref_date: date) -> str:
    """The weekly key of the ISO week containing ``ref_date``."""
    iso_year, iso_week, _ = ref_date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def monthly_period_key(ref_date: date) -> str:
    """The monthly key of the calendar month containing ``ref_date``."""
    return f"{ref_date.year}-{ref_date.month:02d}"


__all__ = [
    "monthly_period_key",
    "monthly_period_start",
    "quarterly_period_start",
    "weekly_period_key",
    "weekly_period_start",
    "yearly_period_start",
]
