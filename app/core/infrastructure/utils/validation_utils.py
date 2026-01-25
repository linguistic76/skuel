"""
Validation Utilities
====================

Common validation functions for domain models.
Ensures consistent validation across the system.
"""

from datetime import UTC, datetime
from typing import Any

# Protocols


class ValidationHelper:
    """Common validation functions for models"""

    @staticmethod
    def validate_required_fields(obj: Any, required_fields: list[str]) -> list[str]:
        """
        Check that required fields are present and non-empty.

        Args:
            obj: Object to validate
            required_fields: List of field names to check

        Returns:
            List of validation error messages
        """
        errors = []
        for field in required_fields:
            if getattr(obj, field, object()) is object():
                errors.append(f"Missing required field: {field}")
            else:
                value = getattr(obj, field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    errors.append(f"{field} cannot be empty")
        return errors

    @staticmethod
    def validate_string_length(
        value: str, field_name: str, min_length: int | None = None, max_length: int | None = None
    ) -> list[str]:
        """
        Validate string length constraints.

        Args:
            value: String to validate,
            field_name: Name for error messages,
            min_length: Minimum allowed length,
            max_length: Maximum allowed length

        Returns:
            List of validation error messages
        """
        errors = []
        if min_length and len(value) < min_length:
            errors.append(f"{field_name} must be at least {min_length} characters")
        if max_length and len(value) > max_length:
            errors.append(f"{field_name} cannot exceed {max_length} characters")
        return errors

    @staticmethod
    def validate_percentage(value: float, field_name: str) -> list[str]:
        """
        Validate percentage is in valid range.

        Args:
            value: Percentage value
            field_name: Name for error messages

        Returns:
            List of validation error messages
        """
        errors = []
        if value < 0:
            errors.append(f"{field_name} cannot be negative")
        if value > 100:
            errors.append(f"{field_name} cannot exceed 100%")
        return errors

    @staticmethod
    def validate_datetime_utc(dt: datetime, field_name: str) -> list[str]:
        """
        Validate datetime is timezone-aware and in UTC.

        Args:
            dt: Datetime to validate
            field_name: Name for error messages

        Returns:
            List of validation error messages
        """
        errors = []
        if dt.tzinfo is None:
            errors.append(f"{field_name} must be timezone-aware")
        elif dt.tzinfo != UTC:
            errors.append(f"{field_name} must be in UTC")
        return errors

    @staticmethod
    def ensure_utc(dt: datetime) -> datetime:
        """
        Convert datetime to UTC if needed.

        Args:
            dt: Datetime to convert

        Returns:
            UTC datetime
        """
        if dt.tzinfo is None:
            # Assume naive datetime is UTC
            return dt.replace(tzinfo=UTC)
        else:
            # Convert to UTC
            return dt.astimezone(UTC)
