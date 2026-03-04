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


def validate_field_name(name: str) -> bool:
    """Check that a field name is a safe Python/Cypher identifier (alphanumeric + underscore)."""
    return bool(_SAFE_FIELD_RE.match(name)) and len(name) <= 64


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
    except (TypeError, ValueError):
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
    except (ValueError, KeyError):
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


# ============================================================================
# DATA CLEANING HELPERS (Converter Pattern - Raises ValueError)
# ============================================================================
# These helpers are used in converters to validate/clean data dictionaries
# before DTO creation. They mutate the dict in place and raise ValueError.


def ensure_list_fields(data: dict[str, Any], field_names: list[str]) -> None:
    """
    Ensure specified fields are lists (convert or default to empty list).

    Mutates data dict in place. Used in converters for list field normalization.

    Args:
        data: Dictionary to validate (mutated in place)
        field_names: List of field names that should be lists

    Example:
        data = {"tags": None, "uids": "single"}
        ensure_list_fields(data, ["tags", "uids"])
        # data is now {"tags": [], "uids": []}
    """
    for field in field_names:
        if field in data and not isinstance(data[field], list | tuple):
            data[field] = []


def parse_datetime_fields(data: dict[str, Any], field_names: list[str]) -> None:
    """
    Parse datetime fields from ISO strings to datetime objects.

    Mutates data dict in place. Used in converters for datetime normalization.

    Args:
        data: Dictionary to validate (mutated in place)
        field_names: List of field names that should be datetimes

    Raises:
        ValueError: If datetime string is invalid

    Example:
        data = {"created_at": "2025-01-15T10:30:00"}
        parse_datetime_fields(data, ["created_at"])
        # data["created_at"] is now datetime object
    """
    for field in field_names:
        if field in data and isinstance(data[field], str):
            try:
                data[field] = datetime.fromisoformat(data[field])
            except ValueError:
                raise ValueError(f"Invalid datetime format for {field}") from None


def parse_date_fields(data: dict[str, Any], field_names: list[str]) -> None:
    """
    Parse date fields from ISO strings to date objects.

    Mutates data dict in place. Used in converters for date normalization.

    Args:
        data: Dictionary to validate (mutated in place)
        field_names: List of field names that should be dates

    Raises:
        ValueError: If date string is invalid

    Example:
        data = {"due_date": "2025-01-15"}
        parse_date_fields(data, ["due_date"])
        # data["due_date"] is now date object
    """
    from datetime import date

    for field in field_names:
        if field in data and isinstance(data[field], str):
            try:
                data[field] = date.fromisoformat(data[field])
            except ValueError:
                raise ValueError(f"Invalid date format for {field}") from None


def parse_time_fields(data: dict[str, Any], field_names: list[str]) -> None:
    """
    Parse time fields from ISO strings to time objects.

    Mutates data dict in place. Used in converters for time normalization.

    Args:
        data: Dictionary to validate (mutated in place)
        field_names: List of field names that should be times

    Raises:
        ValueError: If time string is invalid

    Example:
        data = {"start_time": "10:30:00"}
        parse_time_fields(data, ["start_time"])
        # data["start_time"] is now time object
    """
    from datetime import time

    for field in field_names:
        if field in data and isinstance(data[field], str):
            try:
                data[field] = time.fromisoformat(data[field])
            except ValueError:
                raise ValueError(f"Invalid time format for {field}") from None


def validate_required_fields(data: dict[str, Any], field_names: list[str]) -> None:
    """
    Validate that required fields exist and are not empty.

    Used in converters to ensure critical fields are present.

    Args:
        data: Dictionary to validate
        field_names: List of required field names

    Raises:
        ValueError: If any required field is missing or empty

    Example:
        data = {"uid": "abc", "title": ""}
        validate_required_fields(data, ["uid", "title"])
        # Raises ValueError: "title is required"
    """
    for field in field_names:
        if field not in data or not data[field]:
            raise ValueError(f"{field} is required")


def ensure_metadata_dicts(data: dict[str, Any], field_names: list[str]) -> None:
    """
    Ensure metadata fields are dictionaries (default to empty dict).

    Mutates data dict in place. Used in converters for metadata normalization.

    Args:
        data: Dictionary to validate (mutated in place)
        field_names: List of field names that should be dicts

    Example:
        data = {"metadata": None, "context": "invalid"}
        ensure_metadata_dicts(data, ["metadata", "context"])
        # data is now {"metadata": {}, "context": {}}
    """
    for field in field_names:
        if field in data and data[field] is not None and not isinstance(data[field], dict):
            data[field] = {}


def validate_numeric_range(
    data: dict[str, Any], field_name: str, min_val: float, max_val: float
) -> None:
    """
    Validate that a numeric field is within a specific range.

    Used in converters to ensure numeric constraints (e.g., scores 0-1).

    Args:
        data: Dictionary containing the field
        field_name: Name of the numeric field
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)

    Raises:
        ValueError: If value is outside range or not numeric

    Example:
        data = {"confidence": 1.5}
        validate_numeric_range(data, "confidence", 0.0, 1.0)
        # Raises ValueError: "confidence must be between 0.0 and 1.0"
    """
    if field_name in data and data[field_name] is not None:
        value = data[field_name]
        if not isinstance(value, int | float) or not (min_val <= value <= max_val):
            raise ValueError(f"{field_name} must be between {min_val} and {max_val}")


def validate_confidence_scores(
    data: dict[str, Any], field_name: str = "knowledge_confidence_scores"
) -> None:
    """
    Validate confidence score dictionaries (scores must be 0-1).

    Used in converters for knowledge/task confidence validation.

    Args:
        data: Dictionary containing the scores field
        field_name: Name of the confidence scores field

    Raises:
        ValueError: If scores dict is invalid or contains out-of-range values

    Example:
        data = {"knowledge_confidence_scores": {"ku1": 0.85, "ku2": 1.5}}
        validate_confidence_scores(data)
        # Raises ValueError: "Confidence score for ku2 must be between 0.0 and 1.0"
    """
    if field_name in data and data[field_name] is not None:
        scores = data[field_name]
        if not isinstance(scores, dict):
            raise ValueError(f"{field_name} must be a dictionary")

        for uid, score in scores.items():
            if not isinstance(score, int | float) or not (0.0 <= score <= 1.0):
                raise ValueError(f"Confidence score for {uid} must be between 0.0 and 1.0")
