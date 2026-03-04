"""
Timestamp Helpers
=================

Centralized timestamp and datetime handling utilities.
Eliminates duplication of timestamp operations across services.

DRY Principle:
- Consistent timestamp formatting
- Standard ISO serialization
- Timezone-aware operations
- Frozen dataclass timestamp setting

Usage:
    from core.utils.timestamp_helpers import (
        now_utc,
        now_local,
        set_timestamps,
        serialize_datetime,
    )

    # Set timestamps on frozen dataclass
    task = set_timestamps(task)

    # Get current time
    created_at = now_utc()
"""

from datetime import UTC, date, datetime, time
from typing import TypeVar

T = TypeVar("T")


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
# FROZEN DATACLASS TIMESTAMP SETTING
# =============================================================================


def set_timestamps[T](
    entity: T,
    set_created: bool = True,
    set_updated: bool = True,
    use_utc: bool = False,
) -> T:
    """
    Set created_at and updated_at timestamps on a frozen dataclass.

    Uses object.__setattr__ to bypass frozen constraint during initialization.

    Args:
        entity: Frozen dataclass entity to update
        set_created: Whether to set created_at if None (default: True)
        set_updated: Whether to set updated_at (default: True)
        use_utc: Whether to use UTC time (default: False, uses local time)

    Returns:
        Same entity with timestamps set

    Example:
        @dataclass(frozen=True)
        class Task:
            uid: str
            created_at: datetime = None  # type: ignore[assignment]
            updated_at: datetime = None  # type: ignore[assignment]

        task = Task(uid="task:123")
        task = set_timestamps(task)
        # task.created_at and task.updated_at are now set
    """
    current_time = now_utc() if use_utc else now_local()

    if set_created and getattr(entity, "created_at", None) is None:
        object.__setattr__(entity, "created_at", current_time)

    if set_updated:
        object.__setattr__(entity, "updated_at", current_time)

    return entity


def update_timestamp[T](entity: T, use_utc: bool = False) -> T:
    """
    Update only the updated_at timestamp on a frozen dataclass.

    Args:
        entity: Frozen dataclass entity to update
        use_utc: Whether to use UTC time (default: False)

    Returns:
        Same entity with updated_at refreshed

    Example:
        task = update_timestamp(task)
        # task.updated_at is now current time
    """
    current_time = now_utc() if use_utc else now_local()
    object.__setattr__(entity, "updated_at", current_time)
    return entity


# =============================================================================
# SERIALIZATION HELPERS
# =============================================================================


def serialize_datetime(dt: datetime | None) -> str | None:
    """
    Serialize datetime to ISO format string.

    Args:
        dt: Datetime to serialize (or None)

    Returns:
        ISO format string or None

    Example:
        iso_str = serialize_datetime(task.created_at)
        # "2025-11-28T10:30:00"
    """
    return dt.isoformat() if dt else None


def serialize_date(d: date | None) -> str | None:
    """
    Serialize date to ISO format string.

    Args:
        d: Date to serialize (or None)

    Returns:
        ISO format string or None

    Example:
        iso_str = serialize_date(task.due_date)
        # "2025-11-28"
    """
    return d.isoformat() if d else None


def serialize_time(t: time | None) -> str | None:
    """
    Serialize time to ISO format string.

    Args:
        t: Time to serialize (or None)

    Returns:
        ISO format string or None

    Example:
        iso_str = serialize_time(event.start_time)
        # "10:30:00"
    """
    return t.isoformat() if t else None


# =============================================================================
# PARSING HELPERS
# =============================================================================


def parse_datetime(value: str | datetime | None) -> datetime | None:
    """
    Parse datetime from string or pass through if already datetime.

    Args:
        value: String to parse, datetime to pass through, or None

    Returns:
        Parsed datetime or None

    Example:
        dt = parse_datetime("2025-11-28T10:30:00")
        dt = parse_datetime(existing_datetime)  # passes through
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def parse_date(value: str | date | None) -> date | None:
    """
    Parse date from string or pass through if already date.

    Args:
        value: String to parse, date to pass through, or None

    Returns:
        Parsed date or None

    Example:
        d = parse_date("2025-11-28")
        d = parse_date(existing_date)  # passes through
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def parse_time(value: str | time | None) -> time | None:
    """
    Parse time from string or pass through if already time.

    Args:
        value: String to parse, time to pass through, or None

    Returns:
        Parsed time or None

    Example:
        t = parse_time("10:30:00")
        t = parse_time(existing_time)  # passes through
    """
    if value is None:
        return None
    if isinstance(value, time):
        return value
    return time.fromisoformat(value)


def parse_datetime_field(
    value: str | datetime | None,
    default: datetime | None = None,
) -> datetime | None:
    """
    Parse datetime field with optional default.

    Commonly used when parsing Neo4j results.

    Args:
        value: Value to parse
        default: Default if parsing fails or value is None

    Returns:
        Parsed datetime or default

    Example:
        created_at = parse_datetime_field(
            record.get("created_at"),
            default=datetime.now()
        )
    """
    if value is None:
        return default
    try:
        return parse_datetime(value)
    except (ValueError, TypeError):
        return default


# =============================================================================
# TIMESTAMP DICT HELPERS
# =============================================================================


def get_timestamp_tuple(
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    use_utc: bool = False,
) -> tuple[datetime, datetime]:
    """
    Get a (created_at, updated_at) tuple with defaults.

    Args:
        created_at: Existing created_at or None
        updated_at: Existing updated_at or None
        use_utc: Whether to use UTC for defaults

    Returns:
        Tuple of (created_at, updated_at)

    Example:
        created, updated = get_timestamp_tuple()
        # Both are now()

        created, updated = get_timestamp_tuple(existing_created)
        # created is preserved, updated is now()
    """
    current_time = now_utc() if use_utc else now_local()
    return (
        created_at or current_time,
        updated_at or current_time,
    )


def timestamp_dict(use_utc: bool = False) -> dict[str, str]:
    """
    Create a dict with current timestamp strings for created_at and updated_at.

    Useful when building Neo4j node properties.

    Args:
        use_utc: Whether to use UTC time

    Returns:
        Dict with created_at and updated_at ISO strings

    Example:
        props = {
            "uid": "task:123",
            "title": "My Task",
            **timestamp_dict()
        }
    """
    current_time = now_utc() if use_utc else now_local()
    iso_str = current_time.isoformat()
    return {
        "created_at": iso_str,
        "updated_at": iso_str,
    }


def update_timestamp_dict(use_utc: bool = False) -> dict[str, str]:
    """
    Create a dict with current timestamp string for updated_at only.

    Useful for Neo4j updates.

    Args:
        use_utc: Whether to use UTC time

    Returns:
        Dict with updated_at ISO string

    Example:
        updates = {
            "title": "Updated Title",
            **update_timestamp_dict()
        }
    """
    current_time = now_utc() if use_utc else now_local()
    return {"updated_at": current_time.isoformat()}


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
