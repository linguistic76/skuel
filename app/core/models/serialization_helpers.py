"""
Serialization Helpers
=====================

Centralized datetime serialization utilities.

Created: January 2026
Reason: Consolidate 5 duplicate _serialize_datetime implementations

Usage:
    from core.models.serialization_helpers import serialize_datetime_safe

    # View layer - use safe version for defensive serialization
    result = {"created_at": serialize_datetime_safe(journal.created_at)}
"""

from datetime import date, datetime
from typing import Any


def serialize_datetime_safe(datetime_value: Any) -> str | None:
    """
    Safely serialize datetime to ISO format string.

    Handles None, datetime, and falls back to str() for other types.
    Use in view transformations where type safety is not guaranteed.

    Args:
        datetime_value: datetime object, None, or other value

    Returns:
        ISO format string if datetime, None if None, str(value) otherwise
    """
    if datetime_value is None:
        return None
    if isinstance(datetime_value, datetime):
        return datetime_value.isoformat()
    return str(datetime_value)


def serialize_date_safe(date_value: Any) -> str | None:
    """
    Safely serialize date/datetime to ISO format string.

    Handles None, date, datetime, and falls back to str() for other types.

    Args:
        date_value: date/datetime object, None, or other value

    Returns:
        ISO format string if date/datetime, None if None, str(value) otherwise
    """
    if date_value is None:
        return None
    if isinstance(date_value, date | datetime):
        return date_value.isoformat()
    return str(date_value)
