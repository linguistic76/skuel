"""
Timestamp Helpers
=================

Centralized timestamp and datetime handling utilities.
Eliminates duplication of timestamp operations across services.

DRY Principle:
- Timezone-aware "now" helpers
- The stored clock (STORED_INSTANT_CLOCK): how an offset-less stored stamp is
  read. Instants as aware UTC (as_utc) for comparison and arithmetic — a stored
  stamp of any shape read as one (instant_of), a sort key that tolerates an
  absent one (instant_key), the whole days a set of them spans (span_days) —
  and as a naive reading of the stored clock (as_stored_clock), the form the
  naive writers store
- Display of a stored instant (shown_in, age_of), whatever shape it arrives
  in (parse_stamp)
- Zone helpers, each taking the zone: now_in, wall_clock_in, today_in, day_of
  and hour_of (an instant's day and hour), local_day_bounds (a day's UTC
  bounds), stored_day_bounds (days' bounds on the stored clock, for comparison
  with stored stamps), from_wall_clock and to_wall_clock (a client's offset-less
  datetime read on a zone's clock, and a stored instant as that clock shows it). Whose zone it is — the user's choice or the app default — is
  core/utils/zone_context.py, which also gives today in the current zone
  (today_in_current_zone)
- The type rule (is_instant_field): a model's ``datetime`` field holds an
  instant, a ``date`` field a calendar day
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

import dataclasses
import types
from calendar import monthrange
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Any, Union, get_args, get_origin

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

#: The zone an offset-less stored stamp is read in: ``UTC``. The stored corpus is
#: migrated to UTC and every process is pinned to it (``core/utils/process_clock.py``),
#: so every naive writer stamps UTC digits (ADR-089; the cutover row of
#: /docs/roadmap/utc-instants-arc.md). ``None`` reads a naive stamp in the host's
#: local zone instead — the helpers keep that reading, pinned by their unit tests,
#: until the constant is removed with the pin. Every reading of a stored stamp goes
#: through the helpers below, so this one assignment moves them all.
STORED_INSTANT_CLOCK: tzinfo | None = UTC


def as_utc(value: datetime) -> datetime:
    """An instant as an aware UTC datetime — the one form two instants are compared in.

    An aware value is converted to UTC. A naive value is read in
    ``STORED_INSTANT_CLOCK`` — UTC, whatever zone the process runs in (on
    ``None``, the process's local zone). So a naive stamp and an aware one
    subtract and compare without a ``TypeError``.

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


#: The earliest and the latest aware instants — the sort key an absent instant
#: takes among aware ones (:func:`instant_key`), first or last.
EARLIEST_INSTANT = datetime.min.replace(tzinfo=UTC)
LATEST_INSTANT = datetime.max.replace(tzinfo=UTC)


def instant_key(value: datetime | None, missing: datetime = EARLIEST_INSTANT) -> datetime:
    """An instant as a sort key — aware UTC whatever its shape, ``missing`` when absent.

    A column written by more than one writer holds naive stamps, aware ones and
    gaps at once, and a sort or a ``max`` over them raw raises ``TypeError``.
    Each value reads through :func:`as_utc`; an absent one sorts first, or last
    given ``LATEST_INSTANT``.

    Example:
        newest = max(instant_key(entry.created_at) for entry in entries)
    """
    return as_utc(value) if value is not None else missing


def span_days(instants: Iterable[datetime]) -> int:
    """Whole days from the earliest of ``instants`` to the latest — naive or aware alike.

    Order does not matter; each value reads through :func:`as_utc`. At least one
    instant is required.

    Example:
        timeframe = span_days(task.created_at for task in tasks)
    """
    moments = [as_utc(instant) for instant in instants]
    return (max(moments) - min(moments)).days


def shown_in(instant: datetime, zone: tzinfo) -> datetime:
    """How a stored instant is shown in ``zone`` — a naive wall clock, for display.

    A naive stamp is read in the stored clock (:func:`as_utc`) and shown on
    ``zone``'s clock, and so is an aware one. On the host-zone stored clock
    (``None``) an aware stamp is shown as stored, its own digits: a corpus not
    migrated to UTC holds natives that carry the host's wall clock labelled UTC,
    which nothing short of the migration tells from true UTC ones.

    Example:
        shown_in(entry.created_at, current_zone()).strftime("%b %d, %H:%M")
    """
    if instant.tzinfo is not None and STORED_INSTANT_CLOCK is None:
        return instant.replace(tzinfo=None)
    return as_utc(instant).astimezone(zone).replace(tzinfo=None)


def age_of(instant: datetime) -> timedelta | None:
    """How long ago a stored instant was — ``None`` when it is not to be told.

    On the UTC stored clock every stamp has an age. On the host-zone stored
    clock (``None``) a naive stamp's age is not told, and a relative label
    ("3h ago") shows the stamp by its date instead.

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


def hour_of(instant: datetime, zone: tzinfo) -> int:
    """The hour of the day (0 to 23) an instant falls in on ``zone``'s clock.

    Read like :func:`day_of`: the instant goes through :func:`as_utc` first.

    Example:
        TimeOfDay.from_hour(hour_of(completion.completed_at, current_zone()))
    """
    return as_utc(instant).astimezone(zone).hour


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


def stored_day_bounds(first_day: date, last_day: date, zone: tzinfo) -> tuple[datetime, datetime]:
    """The local days ``first_day`` … ``last_day`` in ``zone``, on the stored clock: ``[start, end)``.

    ``start`` is the first day's first instant and ``end`` the first instant
    after the last day, each read on the stored clock (:func:`as_stored_clock`)
    — the naive form a stored naive stamp takes. A query compares a stored
    instant with these bounds rather than slicing the stamp's own digits to a
    day, so the days are the zone's whatever the stored clock: UTC digits on
    ``UTC``, the host's on ``None``.

    Example:
        start, end = stored_day_bounds(week_start, week_end, current_zone())
        # Cypher: datetime(n.created_at) >= datetime($start)
        #     AND datetime(n.created_at) < datetime($end)
    """
    start, _ = local_day_bounds(first_day, zone)
    _, end = local_day_bounds(last_day, zone)
    return as_stored_clock(start), as_stored_clock(end)


def from_wall_clock(value: datetime, zone: tzinfo) -> datetime:
    """A client's datetime as the stored form of the instant it names.

    An offset-less value is a wall clock in ``zone`` (a ``datetime-local``
    field, a time written in a note), read there and returned on the stored
    clock (:func:`as_stored_clock`). An aware value already names its instant
    and is returned as it came. The inverse of :func:`to_wall_clock`.

    Example:
        deadline = from_wall_clock(datetime(2026, 9, 27, 17, 0), current_zone())
    """
    if value.tzinfo is not None:
        return value
    return as_stored_clock(value.replace(tzinfo=zone))


def to_wall_clock(instant: datetime, zone: tzinfo) -> datetime:
    """A stored instant as the wall clock in ``zone`` that names it — naive.

    What a ``datetime-local`` field is filled with, so that the value it posts
    back reads (:func:`from_wall_clock`) as the same instant: an unchanged edit
    keeps its instant, naive or aware. Unlike :func:`shown_in`, an aware value
    is always the instant it names — never its own digits.

    Example:
        value = to_wall_clock(choice.decision_deadline, current_zone()).isoformat(
            timespec="minutes"
        )
    """
    return as_utc(instant).astimezone(zone).replace(tzinfo=None)


def is_instant_field(model: type, field_name: str) -> bool:
    """Whether a dataclass model's field holds an instant — the type rule (ADR-089 §3).

    A ``datetime`` field (``datetime | None`` included) holds an instant; a
    ``date`` field, or any other, holds a calendar value or none. A name the
    model does not declare is not an instant field.

    Example:
        is_instant_field(Choice, "decision_deadline")  # True
        is_instant_field(Task, "due_date")  # False
    """
    if not dataclasses.is_dataclass(model):
        return False
    for field in dataclasses.fields(model):
        if field.name == field_name:
            union = get_origin(field.type) in (types.UnionType, Union)
            return datetime in (get_args(field.type) if union else (field.type,))
    return False


# =============================================================================
# PARSING HELPERS
# =============================================================================


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


def instant_of(value: object, zone: tzinfo) -> datetime | None:
    """A stored stamp in whatever shape it arrives, as an aware UTC instant — or None.

    Reads every shape :func:`parse_stamp` reads. A moment goes through
    :func:`as_utc`; a bare day (a ``date``, a date-only string) is its first
    instant in ``zone`` — the zone of the user whose day it is. Absent or
    unreadable: None.

    Example:
        cutoff = instant_of(report.data_cutoff, current_zone())
        closed = cutoff is not None and cutoff <= now_utc()
    """
    stamp = parse_stamp(value)
    if isinstance(stamp, datetime):
        return as_utc(stamp)
    if isinstance(stamp, date):
        start, _ = local_day_bounds(stamp, zone)
        return start
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
