"""
Neo4j Temporal Type Utilities
=============================

Provides type-safe conversion from Neo4j temporal types to Python datetime types.

Neo4j returns its own temporal types (neo4j.time.Time, neo4j.time.Date, neo4j.time.DateTime)
which have the same interface as Python's datetime types but are different classes.
This module detects Neo4j types via module inspection (no neo4j import needed)
and converts them to standard Python datetime types.

Usage:
    from core.utils.neo4j_temporal import convert_neo4j_date, convert_neo4j_time

    # Convert Neo4j Date to Python date
    python_date = convert_neo4j_date(neo4j_date_value)

    # Convert Neo4j Time to Python time
    python_time = convert_neo4j_time(neo4j_time_value)
"""

from datetime import date, datetime, time
from typing import Any


def _is_neo4j_temporal(value: Any) -> bool:
    """Check if a value is a Neo4j temporal type (no import needed)."""
    return getattr(type(value), "__module__", "") == "neo4j.time"


def convert_neo4j_date(value: Any, default: date | None = None) -> date | None:
    """
    Convert a Neo4j Date to Python date.

    Args:
        value: Value that may be a Neo4j Date, Python date, or None
        default: Default value if conversion fails

    Returns:
        Python date or default value
    """
    if value is None:
        return default

    # Already a Python date
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    # Neo4j Date type — detected via module name
    if _is_neo4j_temporal(value) and type(value).__name__ == "Date":
        return date(value.year, value.month, value.day)

    return default


def convert_neo4j_time(value: Any, default: time | None = None) -> time | None:
    """
    Convert a Neo4j Time to Python time.

    Args:
        value: Value that may be a Neo4j Time, Python time, string, or None
        default: Default value if conversion fails

    Returns:
        Python time or default value
    """
    if value is None:
        return default

    # Already a Python time
    if isinstance(value, time):
        return value

    # String time value (e.g., "09:30:00")
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%H:%M:%S").time()
        except ValueError:
            try:
                return datetime.strptime(value, "%H:%M").time()
            except ValueError:
                return default

    # Neo4j Time type — detected via module name
    if _is_neo4j_temporal(value) and type(value).__name__ == "Time":
        return time(value.hour, value.minute, value.second or 0)

    return default


def convert_neo4j_datetime(value: Any, default: datetime | None = None) -> datetime | None:
    """
    Convert a Neo4j DateTime to Python datetime.

    Args:
        value: Value that may be a Neo4j DateTime, Python datetime, or None
        default: Default value if conversion fails

    Returns:
        Python datetime or default value
    """
    if value is None:
        return default

    # Already a Python datetime
    if isinstance(value, datetime):
        return value

    # Neo4j DateTime type — detected via module name
    if _is_neo4j_temporal(value) and type(value).__name__ == "DateTime":
        return datetime(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second or 0,
        )

    return default


def is_neo4j_date(value: Any) -> bool:
    """Check if value is a Neo4j Date type."""
    return _is_neo4j_temporal(value) and type(value).__name__ == "Date"


def is_neo4j_time(value: Any) -> bool:
    """Check if value is a Neo4j Time type."""
    return _is_neo4j_temporal(value) and type(value).__name__ == "Time"


def is_neo4j_datetime(value: Any) -> bool:
    """Check if value is a Neo4j DateTime type."""
    return _is_neo4j_temporal(value) and type(value).__name__ == "DateTime"
