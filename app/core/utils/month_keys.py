"""Calendar months as keys, in UTC.

A month key is ``YYYY-MM``, the calendar month an instant falls in when read in
UTC. The presence record (``(:User)-[:PRESENT_IN]->(:Month {key})``) is keyed by
it, and the admin growth and retention reads group by it. Keys of one length
sort as their months do.
"""

from __future__ import annotations

from datetime import UTC, datetime


def _in_utc(instant: datetime) -> datetime:
    """The instant read in UTC; a naive one is already UTC (the process clock is pinned)."""
    return instant if instant.tzinfo is None else instant.astimezone(UTC)


def month_key(instant: datetime) -> str:
    """The UTC calendar month an instant falls in, as ``YYYY-MM``."""
    return _in_utc(instant).strftime("%Y-%m")


def day_key(instant: datetime) -> str:
    """The UTC calendar day an instant falls in, as ``YYYY-MM-DD``."""
    return _in_utc(instant).strftime("%Y-%m-%d")


def shift_month(key: str, months: int) -> str:
    """The month key ``months`` after ``key`` (before it, when negative)."""
    year, month = (int(part) for part in key.split("-"))
    index = year * 12 + (month - 1) + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def trailing_months(current: str, count: int) -> list[str]:
    """The ``count`` month keys ending at ``current``, oldest first."""
    return [shift_month(current, offset) for offset in range(1 - count, 1)]
