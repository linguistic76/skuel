"""
Reusable Pydantic field validators for SKUEL domain models.

This module provides composable validator mixins that can be added to any
Pydantic model to enforce consistent validation rules across the codebase.

Usage:
    from core.utils.validators import UIDValidator, DateRangeValidator

    class TaskCreateRequest(BaseModel, UIDValidator, DateRangeValidator):
        uid: str  # Automatically validated by UIDValidator
        start_date: date
        end_date: date
        # DateRangeValidator ensures end_date >= start_date
"""

import re
from datetime import date, datetime

from pydantic import field_validator, model_validator


class UIDValidator:
    """
    Reusable UID validation for all SKUEL entities.

    Enforces the pattern: prefix:kebab-case-name

    Valid examples:
        - task:review-calculus
        - goal:master-fundamentals
        - ku:derivative-rules
        - lp:calculus-101

    Invalid examples:
        - Task:Review (uppercase not allowed)
        - task_review (underscore not allowed, must use hyphen)
        - task:Review Calculus (spaces not allowed)
    """

    @field_validator("uid")
    @classmethod
    def validate_uid_format(cls, v: str) -> str:
        """Ensure UID follows pattern: prefix:kebab-case-name"""
        if not isinstance(v, str):
            raise ValueError(f"UID must be a string, got: {type(v).__name__}")

        if not re.match(r"^[a-z]+:[a-z0-9-]+$", v):
            raise ValueError(
                f"UID must match pattern 'prefix:kebab-case-name' "
                f"(lowercase letters, numbers, hyphens only), got: '{v}'"
            )

        # Ensure no leading/trailing hyphens in the name part
        prefix, name = v.split(":", 1)
        if name.startswith("-") or name.endswith("-"):
            raise ValueError(f"UID name cannot start or end with hyphen, got: '{v}'")

        # Ensure no consecutive hyphens
        if "--" in name:
            raise ValueError(f"UID name cannot contain consecutive hyphens, got: '{v}'")

        return v


class DateRangeValidator:
    """
    Validates that end_date is not before start_date.

    Works with both date and datetime fields.
    Handles optional fields gracefully (None values are allowed).
    """

    @model_validator(mode="after")
    def validate_date_range(self) -> "DateRangeValidator":
        """Ensure end_date >= start_date when both are present"""
        start = getattr(self, "start_date", None) or getattr(self, "scheduled_date", None)
        end = getattr(self, "end_date", None) or getattr(self, "due_date", None)

        if (
            start
            and end
            and (
                (isinstance(start, datetime) and isinstance(end, datetime))
                or (isinstance(start, date) and isinstance(end, date))
            )
            and end < start
        ):
            raise ValueError(f"end_date ({end}) cannot be before start_date ({start})")

        return self


class TimeRangeValidator:
    """
    Validates that end_time is after start_time for events.

    Handles time strings in HH:MM format or datetime objects.
    """

    @model_validator(mode="after")
    def validate_time_range(self) -> "TimeRangeValidator":
        """Ensure end_time > start_time when both are present"""
        start_time = getattr(self, "start_time", None)
        end_time = getattr(self, "end_time", None)

        if start_time and end_time:
            # Convert string times to comparable format if needed
            if isinstance(start_time, str) and isinstance(end_time, str):
                # Assume HH:MM format
                start_parts = start_time.split(":")
                end_parts = end_time.split(":")

                start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
                end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])

                if end_minutes <= start_minutes:
                    raise ValueError(
                        f"end_time ({end_time}) must be after start_time ({start_time})"
                    )

            # Handle datetime comparison
            elif isinstance(start_time, datetime) and isinstance(end_time, datetime):
                if end_time <= start_time:
                    raise ValueError(
                        f"end_time ({end_time}) must be after start_time ({start_time})"
                    )

        return self


class DurationValidator:
    """
    Validates that duration_minutes is a positive integer.

    Optionally enforces maximum duration limits.
    """

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration(cls, v: int | None) -> int | None:
        """Ensure duration is positive and reasonable"""
        if v is None:
            return v

        if not isinstance(v, int):
            raise ValueError(f"duration_minutes must be an integer, got: {type(v).__name__}")

        if v <= 0:
            raise ValueError(f"duration_minutes must be positive, got: {v}")

        # Optional: Set a reasonable maximum (24 hours = 1440 minutes)
        if v > 1440:
            raise ValueError(f"duration_minutes exceeds maximum (1440), got: {v}")

        return v


class PriorityValidator:
    """
    Validates priority field values.

    Ensures priority is one of: low, medium, high, urgent
    """

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        """Ensure priority is a valid value"""
        if v is None:
            return v

        valid_priorities = {"low", "medium", "high", "urgent"}

        if v not in valid_priorities:
            raise ValueError(f"priority must be one of {valid_priorities}, got: '{v}'")

        return v


class PercentageValidator:
    """
    Validates percentage fields (0.0 to 100.0).

    Works with fields like: completion_percentage, target_value, current_value
    """

    @field_validator(
        "completion_percentage", "target_value", "current_value", "progress_percentage"
    )
    @classmethod
    def validate_percentage(cls, v: float | None, info) -> float | None:
        """Ensure percentage is between 0 and 100"""
        if v is None:
            return v

        if not isinstance(v, int | float):
            raise ValueError(f"{info.field_name} must be a number, got: {type(v).__name__}")

        if v < 0.0 or v > 100.0:
            raise ValueError(f"{info.field_name} must be between 0 and 100, got: {v}")

        return float(v)


class EmailValidator:
    """
    Validates email address format.

    Basic email validation - for production use, consider pydantic's EmailStr.
    """

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str | None) -> str | None:
        """Ensure email has basic valid format"""
        if v is None:
            return v

        # Basic email regex - not RFC-compliant but catches common errors
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        if not re.match(email_pattern, v):
            raise ValueError(f"Invalid email format: '{v}'")

        return v.lower()  # Normalize to lowercase


class RecurrenceRuleValidator:
    """
    Validates iCalendar RRULE format for recurring events/habits.

    Ensures recurrence_rule/recurrence_pattern follows basic RRULE syntax.
    """

    @field_validator("recurrence_rule", "recurrence_pattern")
    @classmethod
    def validate_recurrence_rule(cls, v: str | None, info) -> str | None:
        """Ensure recurrence rule follows RRULE format"""
        if v is None:
            return v

        # Must start with FREQ=
        if not v.startswith("FREQ="):
            raise ValueError(f"{info.field_name} must start with 'FREQ=', got: '{v}'")

        # Validate FREQ value
        valid_frequencies = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}
        freq_part = v.split(";")[0]
        freq_value = freq_part.split("=")[1]

        if freq_value not in valid_frequencies:
            raise ValueError(f"FREQ must be one of {valid_frequencies}, got: '{freq_value}'")

        return v


class PositiveIntegerValidator:
    """
    Validates that integer fields are positive.

    Works with fields like: streak_target_days, recurrence_count, participant_count
    """

    @field_validator(
        "streak_target_days",
        "recurrence_count",
        "participant_count",
        "current_streak",
        "longest_streak",
    )
    @classmethod
    def validate_positive_integer(cls, v: int | None, info) -> int | None:
        """Ensure integer field is non-negative"""
        if v is None:
            return v

        if not isinstance(v, int):
            raise ValueError(f"{info.field_name} must be an integer, got: {type(v).__name__}")

        if v < 0:
            raise ValueError(f"{info.field_name} must be non-negative, got: {v}")

        return v


# Composite validators combining multiple checks


class TaskValidator(UIDValidator, DateRangeValidator, DurationValidator, PriorityValidator):
    """Composite validator for Task domain models"""

    pass


class EventValidator(UIDValidator, DateRangeValidator, TimeRangeValidator, DurationValidator):
    """Composite validator for Event domain models"""

    pass


class HabitValidator(
    UIDValidator, DurationValidator, RecurrenceRuleValidator, PositiveIntegerValidator
):
    """Composite validator for Habit domain models"""

    pass


class GoalValidator(UIDValidator, DateRangeValidator, PercentageValidator):
    """Composite validator for Goal domain models"""

    pass
