"""
JSON Encoder Functions for Pydantic Models
==========================================

Named encoder functions to replace lambda expressions in Pydantic Config classes.
Following clean code principle: no lambdas, only named functions.
"""

from datetime import date, datetime, time
from typing import Any

from core.services.protocols import get_enum_value


def encode_enum_value(v: Any) -> Any:
    """Encode enum-like object to its value."""
    return get_enum_value(v)


def encode_date_isoformat(v: date) -> str:
    """Encode date to ISO format string."""
    return v.isoformat()


def encode_datetime_isoformat(v: datetime) -> str:
    """Encode datetime to ISO format string."""
    return v.isoformat()


def encode_time_isoformat(v: time) -> str:
    """Encode time to ISO format string."""
    return v.isoformat()


def encode_optional_time_isoformat(v: time | None) -> str | None:
    """Encode optional time to ISO format string."""
    return v.isoformat() if v else None


def encode_optional_datetime_isoformat(v: datetime | None) -> str | None:
    """Encode optional datetime to ISO format string."""
    return v.isoformat() if v else None


def encode_activity_type_value(v: Any) -> str:
    """Encode ActivityType enum to its string value."""
    from core.services.protocols import EnumLike

    return str(v.value) if isinstance(v, EnumLike) else str(v)


def encode_domain_value(v: Any) -> str:
    """Encode Domain enum to its string value."""
    return get_enum_value(v)
