"""
Timestamp Helpers
=================

Centralized timestamp and datetime handling utilities.
Eliminates duplication of timestamp operations across services.

DRY Principle:
- Timezone-aware "now" helpers
- Duration/age calculations (days_until, days_since, is_overdue, is_today)
- Calendar arithmetic (week_bounds, month_grid_bounds, prev/next month and week)
- Neo4j-tolerant scalar date parsing (parse_date_value)

Usage:
    from core.utils.timestamp_helpers import now_utc, days_until, week_bounds

    # Get current time
    created_at = now_utc()

Note: dict-level batch parsing for DTO deserialization lives in
``core/models/dto_helpers.py`` (the canonical from_dict parse layer);
this module only owns scalar/date arithmetic helpers.
"""

from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from typing import Any

# =============================================================================
# CURRENT TIME HELPERS
# =============================================================================


def now_utc() -> datetime:
    """
    Get current UTC datetime.

    Returns:
        Current datetime in UTC timezone
    """
    return datetime.now(UTC)


def now_local() -> datetime:
    """
    Get current local datetime.

    Returns:
        Current datetime in local timezone
    """
    return datetime.now()


def today() -> date:
    """
    Get today's date.

    Returns:
        Today's date
    """
    return date.today()


# =============================================================================
# PARSING HELPERS
# =============================================================================


def parse_iso_utc(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string, treating naive values as UTC.

    Learning-loop stamps have mixed provenance: entry ``created_at`` values
    are naive ISO strings (the mapper emits ``isoformat()``) while report/
    revision stamps are timezone-aware (server-side ``datetime()``,
    ``toString()``-ed at the Cypher boundary). Comparing them raw would
    TypeError — naive values are UTC by convention (feedback-loop UX arc).

    Returns:
        Timezone-aware datetime, or None for missing/unparseable input.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def parse_date_value(value: Any) -> date | None:
    """
    Parse a date value from Neo4j (string, date, or neo4j.time.Date).

    Neo4j returns dates as neo4j.time.Date objects; this helper normalizes
    them alongside strings and native date objects.

    Args:
        value: Date value in various formats

    Returns:
        Python date object or None
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    if getattr(type(value), "__module__", "") == "neo4j.time":
        return date(value.year, value.month, value.day)
    return None


# =============================================================================
# DURATION/AGE HELPERS
# =============================================================================


def days_until(target_date: date | None) -> int | None:
    """
    Calculate days until a target date.

    Args:
        target_date: Target date (or None)

    Returns:
        Days until date (negative if past), or None if no date

    Example:
        days = days_until(task.due_date)
        if days is not None and days < 0:
            print("Overdue!")
    """
    if target_date is None:
        return None
    return (target_date - date.today()).days


def days_since(past_date: date | None) -> int | None:
    """
    Calculate days since a past date.

    Args:
        past_date: Past date (or None)

    Returns:
        Days since date (negative if future), or None if no date

    Example:
        age = days_since(task.created_at.date())
    """
    if past_date is None:
        return None
    return (date.today() - past_date).days


def is_overdue(due_date: date | None) -> bool:
    """
    Check if a due date is in the past.

    Args:
        due_date: Due date to check (or None)

    Returns:
        True if due_date is before today, False otherwise

    Example:
        if is_overdue(task.due_date):
            print("Task is overdue!")
    """
    if due_date is None:
        return False
    return due_date < date.today()


def is_today(check_date: date | None) -> bool:
    """
    Check if a date is today.

    Args:
        check_date: Date to check (or None)

    Returns:
        True if date is today

    Example:
        if is_today(event.event_date):
            print("Event is today!")
    """
    if check_date is None:
        return False
    return check_date == date.today()


# =============================================================================
# SCORING HELPERS
# =============================================================================


FREQUENCY_WINDOWS_DAYS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
}


def get_frequency_window_days(
    recurrence_pattern: str | None,
    default: int = 1,
) -> int:
    """Return recurrence window in days for a frequency pattern.

    Args:
        recurrence_pattern: Frequency string (daily/weekly/monthly) or None
        default: Window days when pattern is None or unknown
    """
    if not recurrence_pattern:
        return default
    return FREQUENCY_WINDOWS_DAYS.get(recurrence_pattern, default)


def week_bounds(d: date) -> tuple[date, date]:
    """
    Get Monday-Sunday bounds for the week containing ``d``.

    Returns:
        (monday, sunday) tuple
    """
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def month_grid_bounds(year: int, month: int) -> tuple[date, date]:
    """
    Get the full visible range of a Monday-start month grid.

    The grid renders whole weeks, so it starts on the Monday on/before the
    1st and ends on the Sunday on/after the month's last day — lead-in and
    tail cells belonging to adjacent months included.

    Returns:
        (grid_start, grid_end) tuple, both inclusive
    """
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    grid_start = first - timedelta(days=first.weekday())
    grid_end = last + timedelta(days=6 - last.weekday())
    return grid_start, grid_end


def prev_month(year: int, month: int) -> tuple[int, int]:
    """Return (year, month) for the previous month."""
    if month == 1:
        return (year - 1, 12)
    return (year, month - 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    """Return (year, month) for the next month."""
    if month == 12:
        return (year + 1, 1)
    return (year, month + 1)


def prev_week(d: date) -> str:
    """Return previous week as ISO date string."""
    return (d - timedelta(days=7)).isoformat()


def next_week(d: date) -> str:
    """Return next week as ISO date string."""
    return (d + timedelta(days=7)).isoformat()


def score_deadline_proximity(
    days_until: int,
    bands: tuple[tuple[int, int], ...],
    default_score: int = 5,
) -> int:
    """Score entity priority based on deadline proximity.

    Bands are (max_days, score) pairs checked in ascending order.
    First matching band wins.

    Args:
        days_until: Days until deadline (negative = overdue)
        bands: Threshold boundaries as (max_days, score) pairs
        default_score: Score when beyond all bands
    """
    for max_days, score in bands:
        if days_until <= max_days:
            return score
    return default_score
