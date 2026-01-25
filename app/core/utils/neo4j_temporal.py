"""
Neo4j Temporal Type Utilities
=============================

Provides type-safe conversion from Neo4j temporal types to Python datetime types.

Neo4j returns its own temporal types (neo4j.time.Time, neo4j.time.Date, neo4j.time.DateTime)
which have the same interface as Python's datetime types but are different classes.
This module provides explicit isinstance() checks for proper type-safe conversion.

Usage:
    from core.utils.neo4j_temporal import convert_neo4j_date, convert_neo4j_time

    # Convert Neo4j Date to Python date
    python_date = convert_neo4j_date(neo4j_date_value)

    # Convert Neo4j Time to Python time
    python_time = convert_neo4j_time(neo4j_time_value)
"""

from datetime import date, datetime, time
from typing import Any

# Import Neo4j temporal types for isinstance() checks
try:
    from neo4j.time import Date as Neo4jDate
    from neo4j.time import DateTime as Neo4jDateTime
    from neo4j.time import Time as Neo4jTime

    NEO4J_TYPES_AVAILABLE = True
except ImportError:
    # Fallback if neo4j is not installed (for testing)
    Neo4jDate = type(None)  # type: ignore[misc, assignment]
    Neo4jTime = type(None)  # type: ignore[misc, assignment]
    Neo4jDateTime = type(None)  # type: ignore[misc, assignment]
    NEO4J_TYPES_AVAILABLE = False


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

    # Neo4j Date type
    if NEO4J_TYPES_AVAILABLE and isinstance(value, Neo4jDate):
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

    # Neo4j Time type
    if NEO4J_TYPES_AVAILABLE and isinstance(value, Neo4jTime):
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

    # Neo4j DateTime type
    if NEO4J_TYPES_AVAILABLE and isinstance(value, Neo4jDateTime):
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
    return NEO4J_TYPES_AVAILABLE and isinstance(value, Neo4jDate)


def is_neo4j_time(value: Any) -> bool:
    """Check if value is a Neo4j Time type."""
    return NEO4J_TYPES_AVAILABLE and isinstance(value, Neo4jTime)


def is_neo4j_datetime(value: Any) -> bool:
    """Check if value is a Neo4j DateTime type."""
    return NEO4J_TYPES_AVAILABLE and isinstance(value, Neo4jDateTime)
