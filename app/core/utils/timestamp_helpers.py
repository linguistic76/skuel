"""
Timestamp Helpers
=================

Centralized timestamp and datetime handling utilities.
Eliminates duplication of timestamp operations across services.

DRY Principle:
- Timezone-aware "now" helpers
- The stored clock (STORED_INSTANT_CLOCK): how an offset-less stored stamp is
  read. Instants as aware UTC (as_utc) for comparison and arithmetic, and as a
  naive reading of the stored clock (as_stored_clock) for comparison with the
  naive stamps the writers store
- Display of a stored instant (shown_in, age_of), whatever shape it arrives
  in (parse_stamp)
- Zone helpers, each taking the zone: now_in, wall_clock_in, today_in, day_of
  (an instant's day), local_day_bounds (a day's UTC bounds). Whose zone it is —
  the user's choice or the app default — is core/utils/zone_context.py, which
  also gives today in the current zone (today_in_current_zone)
- Calendar arithmetic (week_bounds, month_grid_bounds, prev/next month and week)
- Neo4j-tolerant scalar date parsing (parse_date_value)

Usage:
    from core.utils.timestamp_helpers import now_utc, today_in, week_bounds
    from core.utils.zone_context import current_zone

    # Get current time
    created_at = now_utc()

    # "Today" is today in the current zone, never the host's day
    overdue = task.due_date < today_in(current_zone())

Note: dict-level batch parsing for DTO deserialization lives in
``core/models/dto_helpers.py`` (the canonical from_dict parse layer);
this module only owns scalar/date arithmetic helpers.
"""

from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta, tzinfo
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


# =============================================================================
# THE STORED CLOCK — what an offset-less stored stamp's digits mean
# =============================================================================

#: The zone an offset-less stored stamp is read in. ``None`` is the host's local
#: zone — the clock every naive writer stamps with, and so the zone the stored
#: corpus's offset-less digits are in; it becomes ``UTC`` when the corpus is
#: migrated to UTC and the process clock is pinned to it (ADR-089; the cutover
#: row of /docs/roadmap/utc-instants-arc.md). Every reading of a stored stamp
#: goes through the helpers below, so that one assignment moves them all.
STORED_INSTANT_CLOCK: tzinfo | None = None


def as_utc(value: datetime) -> datetime:
    """An instant as an aware UTC datetime — the one form two instants are compared in.

    An aware value is converted to UTC. A naive value is read in
    ``STORED_INSTANT_CLOCK`` — while that is the host's zone (``None``), the
    process's local zone: the laptop's zone on the laptop, UTC in CI and in the
    cloud. So a naive stamp and an aware one subtract and compare without a
    ``TypeError``, and a naive value is never read in a hard-coded zone.

    Example:
        age = now_utc() - as_utc(goal.created_at)

    See: /docs/roadmap/utc-instants-arc.md (the arc that routes every instant here)
    """
    if value.tzinfo is None and STORED_INSTANT_CLOCK is not None:
        return value.replace(tzinfo=STORED_INSTANT_CLOCK).astimezone(UTC)
    return value.astimezone(UTC)


def as_stored_clock(value: datetime) -> datetime:
    """An instant as a naive reading of the stored clock — the form a naive stamp takes.

    The inverse of :func:`as_utc` for a naive value: the writers store naive
    values on the stored clock (a default factory, ``datetime.now()``) and
    :func:`as_utc` reads them back in ``STORED_INSTANT_CLOCK``, so
    ``as_utc(as_stored_clock(x)) == as_utc(x)``. A calendar day widened to a
    moment — a period's bounds, a date-only completion — is compared with those
    naive values in this form.

    Example:
        start, _ = local_day_bounds(day, zone)
        completed_at = as_stored_clock(start)  # the day's first instant, stored naive
    """
    return as_utc(value).astimezone(STORED_INSTANT_CLOCK).replace(tzinfo=None)


def shown_in(instant: datetime, zone: tzinfo) -> datetime:
    """How a stored instant is shown in ``zone`` — a naive wall clock, for display.

    A naive stamp is read in the stored clock (:func:`as_utc`) and shown on
    ``zone``'s clock. An aware stamp is shown on ``zone``'s clock too — except
    while the stored clock is the host's (``None``), when it is shown as stored,
    its own digits: until the corpus is migrated, some stored natives carry the
    host's wall clock labelled UTC, and nothing short of the migration tells
    them from true UTC ones. On the laptop, for a user on the default zone, both
    readings give the digits as stored.

    Example:
        shown_in(entry.created_at, current_zone()).strftime("%b %d, %H:%M")
    """
    if instant.tzinfo is not None and STORED_INSTANT_CLOCK is None:
        return instant.replace(tzinfo=None)
    return as_utc(instant).astimezone(zone).replace(tzinfo=None)


def age_of(instant: datetime) -> timedelta | None:
    """How long ago a stored instant was — ``None`` when it is not to be told.

    While the stored clock is the host's (``None``), a naive stamp's age is not
    told, and a relative label ("3h ago") shows the stamp by its date instead.
    Once the stored clock is UTC, every stamp has an age.

    Example:
        age = age_of(shared_at)
        label = "just now" if age is not None and age < timedelta(minutes=1) else ...
    """
    if instant.tzinfo is None and STORED_INSTANT_CLOCK is None:
        return None
    return now_utc() - as_utc(instant)


# =============================================================================
# ZONE HELPERS — each takes the zone; core/utils/zone_context.py says whose
# =============================================================================


def now_in(zone: tzinfo) -> datetime:
    """The current moment as a wall clock in ``zone`` — an aware datetime.

    Example:
        now_in(ZoneInfo("Asia/Bangkok")).hour  # the hour on a Bangkok clock
    """
    return datetime.now(zone)


def wall_clock_in(zone: tzinfo) -> datetime:
    """The wall clock in ``zone`` as a naive datetime.

    For comparison with a calendar wall time, which carries no zone of its own:
    an event's start (its ``event_date`` and ``start_time``), a free slot on a
    day's grid, a client's ``datetime-local`` value.

    Example:
        start = event.start_datetime()
        upcoming = start is not None and start > wall_clock_in(current_zone())
    """
    return datetime.now(zone).replace(tzinfo=None)


def today_in(zone: tzinfo) -> date:
    """Today's date in ``zone``.

    Example:
        today_in(current_zone())  # "today" for the in-flight request
    """
    return datetime.now(zone).date()


def day_of(instant: datetime, zone: tzinfo) -> date:
    """The calendar day an instant falls on in ``zone``.

    The instant is read through :func:`as_utc` first, so an aware value and a
    naive one give the day by the same rule.

    Example:
        day_of(entry.created_at, current_zone())
    """
    return as_utc(instant).astimezone(zone).date()


def local_day_bounds(day: date, zone: tzinfo) -> tuple[datetime, datetime]:
    """The instants a calendar day in ``zone`` spans, as aware UTC: ``[start, end)``.

    ``start`` is the day's local midnight and ``end`` the next day's, so a day
    that gains or loses a daylight-saving hour spans 25 or 23 hours. A local
    midnight that occurs twice reads as its first occurrence.

    Example:
        start, end = local_day_bounds(today_in(zone), zone)
        # instants on that local day: start <= as_utc(stamp) < end
    """
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


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


def parse_stamp(value: object) -> datetime | date | None:
    """A stored timestamp in whatever shape it arrives — or None when absent or unreadable.

    Accepts a native ``datetime`` or ``date``, a Neo4j temporal (``to_native()``),
    or an ISO string. A date-only string is a calendar day and parses to a
    ``date``, never to its midnight: a day is never read as an instant.

    Example:
        stamp = parse_stamp(row["created_at"])
        if isinstance(stamp, datetime):
            label = shown_in(stamp, current_zone()).strftime("%b %d")
    """
    if value is None or value == "":
        return None
    to_native = getattr(value, "to_native", None)
    try:
        if callable(to_native):
            native = to_native()
            return native if isinstance(native, date) else None
        if isinstance(value, date):
            return value
        text = str(value)
        if len(text) == len("YYYY-MM-DD"):
            return date.fromisoformat(text)
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):  # fmt: skip
        return None


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
