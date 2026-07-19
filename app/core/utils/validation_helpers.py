"""
Validation Helpers - Reusable Field Validation Logic
====================================================

This module provides standalone validation functions used across SKUEL.

Extracted from base_service.py to promote reusability in:
- Services (via BaseService wrapper methods)
- Routes (direct validation of request parameters)
- Utilities (data processing pipelines)
- Tests (validation logic testing)

All functions return Result[T] for consistent error handling.

Philosophy:
- Pure validation functions (no side effects)
- User-friendly error messages
- Type-safe return values
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from enum import Enum

# ============================================================================
# CYPHER INJECTION PREVENTION
# ============================================================================

_SAFE_FIELD_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Operators safe to interpolate into Cypher comparison fragments.
# Must match QueryConstraint.operator values used by query_optimizer + cypher fragment builders.
_SAFE_CYPHER_OPERATORS = frozenset(
    {
        "=",
        "<>",
        "!=",
        "<",
        ">",
        "<=",
        ">=",
        "CONTAINS",
        "STARTS WITH",
        "ENDS WITH",
        "IN",
    }
)

_SAFE_SORT_DIRECTIONS = frozenset({"ASC", "DESC"})


def validate_field_name(name: str) -> bool:
    """Check that a field name is a safe Python/Cypher identifier (alphanumeric + underscore)."""
    return bool(_SAFE_FIELD_RE.match(name)) and len(name) <= 64


def validate_cypher_operator(op: str) -> bool:
    """Check that a Cypher comparison operator is on the allowlist (case-sensitive).

    Belongs to the same defense-in-depth layer as `validate_field_name`: any string
    interpolated into a Cypher fragment must pass through one of these gates.
    """
    return op in _SAFE_CYPHER_OPERATORS


def validate_sort_direction(direction: str) -> bool:
    """Check that an ORDER BY direction is ASC or DESC (case-insensitive)."""
    return direction.upper() in _SAFE_SORT_DIRECTIONS


def validate_relationship_type(name: str) -> bool:
    """
    Check that a relationship type is safe for Cypher interpolation.

    Accepts either a known RelationshipName enum value or a safe identifier.
    """
    from core.models.relationship_names import RelationshipName

    # Fast path: known enum value
    try:
        RelationshipName(name)
        return True
    except ValueError:
        pass

    # Fallback: safe identifier pattern (e.g. custom relationship types)
    return validate_field_name(name)


def validate_required(value: Any, field_name: str) -> Result[Any]:
    """
    Validate that a field is present and not empty.

    Args:
        value: The value to validate
        field_name: Name of the field (for error messages)

    Returns:
        Result.ok(value) if valid, Result.fail() with validation error if not

    Example:
        result = validate_required(user_input, "email")
        if result.is_error:
            return result  # Propagate validation error
        email = result.value  # Guaranteed non-empty
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return Result.fail(
            Errors.validation(
                message=f"{field_name} is required",
                field=field_name,
                user_message=f"Please provide a valid {field_name.replace('_', ' ')}",
            )
        )
    return Result.ok(value)


def validate_positive(value: Any, field_name: str) -> Result[float]:
    """
    Validate that a number is positive.

    Args:
        value: The value to validate (will be converted to float)
        field_name: Name of the field (for error messages)

    Returns:
        Result.ok(float_value) if valid positive number
        Result.fail() with validation error if not

    Example:
        result = validate_positive(amount, "price")
        if result.is_error:
            return result  # Propagate validation error
        price = result.value  # Guaranteed positive float
    """
    if value is None:
        return Result.fail(Errors.validation(message=f"{field_name} is required", field=field_name))

    try:
        num_value = float(value)
        if num_value <= 0:
            return Result.fail(
                Errors.validation(
                    message=f"{field_name} must be positive",
                    field=field_name,
                    user_message=f"{field_name.replace('_', ' ')} must be greater than zero",
                )
            )
        return Result.ok(num_value)
    except (TypeError, ValueError):  # fmt: skip
        return Result.fail(
            Errors.validation(message=f"{field_name} must be a number", field=field_name)
        )


def validate_enum(value: Any, enum_class: type[Enum], field_name: str) -> Result[Any]:
    """
    Validate that a value is a valid enum member.

    Handles:
    - None values (returns Ok(None) for optional enums)
    - Enum instances (validates they're correct type)
    - String values (converts to enum)

    Args:
        value: The value to validate
        enum_class: The enum class to validate against (must be type[Enum])
        field_name: Name of the field (for error messages)

    Returns:
        Result.ok(enum_value) if valid
        Result.fail() with validation error if not

    Example:
        result = validate_enum(status_str, TaskStatus, "status")
        if result.is_error:
            return result  # Propagate validation error
        status = result.value  # Guaranteed valid TaskStatus enum
    """
    if value is None:
        return Result.ok(None)  # Optional enum

    if isinstance(value, enum_class):
        return Result.ok(value)

    try:
        # Try to construct enum from string
        if isinstance(value, str):
            return Result.ok(enum_class(value))
        else:
            valid_values = ", ".join(str(e.value) for e in enum_class)
            return Result.fail(
                Errors.validation(
                    message=f"Invalid {field_name}. Valid values: {valid_values}",
                    field=field_name,
                )
            )
    except (ValueError, KeyError):  # fmt: skip
        valid_values = ", ".join(str(e.value) for e in enum_class)
        return Result.fail(
            Errors.validation(
                message=f"Invalid {field_name}: {value}. Valid values: {valid_values}",
                field=field_name,
            )
        )


def validate_date_range(start_date: Any, end_date: Any, field_prefix: str = "") -> Result[bool]:
    """
    Validate that end date is after start date.

    Handles both date and datetime objects (converts datetime to date).

    Args:
        start_date: The start date (date or datetime)
        end_date: The end date (date or datetime)
        field_prefix: Optional prefix for field names in error messages

    Returns:
        Result.ok(True) if valid range
        Result.fail() with validation error if end < start

    Example:
        result = validate_date_range(start, end, "event_")
        if result.is_error:
            return result  # Propagate validation error
        # Guaranteed: end_date >= start_date
    """
    if start_date and end_date:
        # Handle both date and datetime objects
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()

        if end_date < start_date:
            return Result.fail(
                Errors.validation(
                    message=f"{field_prefix}end_date cannot be before {field_prefix}start_date",
                    field=f"{field_prefix}date_range",
                    user_message="End date must be after start date",
                )
            )

    return Result.ok(True)


def parse_timeframe_days(timeframe: str, default: int = 90) -> int:
    """Parse a timeframe string like "30d" into an integer number of days.

    Supports the "{N}d" format (e.g., "7d", "30d", "90d").
    Returns the default if the format is unrecognized or parsing fails.

    Args:
        timeframe: Timeframe string (e.g., "90d")
        default: Fallback value if parsing fails

    Returns:
        Number of days as integer
    """
    if timeframe.endswith("d"):
        try:
            return int(timeframe[:-1])
        except ValueError:
            return default
    return default
