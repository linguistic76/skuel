"""
Shared Validation Rules (Tier 1 - External)
============================================

Reusable Pydantic validators for request models across all domains.
Eliminates duplication of common validation patterns.

DRY Principle:
- Future date validation (tasks, goals, events, milestones)
- Required string validation (titles, names, descriptions)
- List length validation (tags, criteria, options)
- Range validation (scores, percentages, durations)
- Date range validation (start_date < end_date)

Usage:
    from core.models.validation_rules import (
        validate_future_date,
        validate_required_string,
        validate_list_max_length,
        validate_date_range,
    )

    class TaskCreateRequest(BaseModel):
        title: str = Field(...)
        due_date: date | None = None
        tags: list[str] = Field(default_factory=list)

        # Apply validators
        _validate_title = validate_required_string("title")
        _validate_due_date = validate_future_date("due_date")
        _validate_tags = validate_list_max_length("tags", max_length=20)
"""

from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any

from pydantic import ValidationInfo, field_validator

# =============================================================================
# FUTURE DATE VALIDATORS
# =============================================================================


def validate_future_date(*field_names: str) -> Callable:
    """
    Create a validator that ensures date fields are not in the past.

    Works with both `date` and `datetime` types.

    Args:
        *field_names: Names of fields to validate

    Returns:
        Pydantic field validator

    Example:
        class TaskCreateRequest(BaseModel):
            due_date: date | None = None
            scheduled_date: date | None = None

            _validate_dates = validate_future_date("due_date", "scheduled_date")
    """

    @field_validator(*field_names)
    def _validate_future_date(cls, v: date | datetime | None) -> date | datetime | None:
        if v is None:
            return v

        if isinstance(v, datetime):
            if v <= datetime.now():
                raise ValueError("Date/time cannot be in the past")
        elif isinstance(v, date) and v < date.today():
            raise ValueError("Date cannot be in the past")

        return v

    return _validate_future_date


def validate_future_date_or_today(*field_names: str) -> Callable:
    """
    Create a validator that ensures date fields are today or in the future.

    Args:
        *field_names: Names of fields to validate

    Returns:
        Pydantic field validator

    Example:
        class EventCreateRequest(BaseModel):
            event_date: date

            _validate_event_date = validate_future_date_or_today("event_date")
    """

    @field_validator(*field_names)
    def _validate_future_or_today(cls, v: date | datetime | None) -> date | datetime | None:
        if v is None:
            return v

        today = date.today()
        check_date = v.date() if isinstance(v, datetime) else v

        if check_date < today:
            raise ValueError("Date must be today or in the future")

        return v

    return _validate_future_or_today


def validate_past_date(*field_names: str) -> Callable:
    """
    Create a validator that ensures date fields are not in the future.

    Useful for completion dates, decision dates, etc.

    Args:
        *field_names: Names of fields to validate

    Returns:
        Pydantic field validator

    Example:
        class ChoiceDecisionRequest(BaseModel):
            decided_at: datetime | None = None

            _validate_decided_at = validate_past_date("decided_at")
    """

    @field_validator(*field_names)
    def _validate_past_date(cls, v: date | datetime | None) -> date | datetime | None:
        if v is None:
            return v

        if isinstance(v, datetime):
            if v > datetime.now():
                raise ValueError("Date/time cannot be in the future")
        elif isinstance(v, date) and v > date.today():
            raise ValueError("Date cannot be in the future")

        return v

    return _validate_past_date


# =============================================================================
# STRING VALIDATORS
# =============================================================================


def validate_required_string(*field_names: str, min_length: int = 1) -> Callable:
    """
    Create a validator that ensures string fields are not empty after stripping.

    Args:
        *field_names: Names of fields to validate
        min_length: Minimum length after stripping (default: 1)

    Returns:
        Pydantic field validator that also strips whitespace

    Example:
        class GoalCreateRequest(BaseModel):
            title: str

            _validate_title = validate_required_string("title")
    """

    @field_validator(*field_names)
    def _validate_required_string(cls, v: str | None) -> str | None:
        if v is None:
            return v

        stripped = v.strip()
        if len(stripped) < min_length:
            if min_length == 1:
                raise ValueError("Field cannot be empty")
            else:
                raise ValueError(f"Field must be at least {min_length} characters")

        return stripped

    return _validate_required_string


def validate_identity_format(*field_names: str) -> Callable:
    """
    Create a validator for identity statements (e.g., "I am a writer").

    Args:
        *field_names: Names of fields to validate

    Returns:
        Pydantic field validator

    Example:
        class IdentityGoalRequest(BaseModel):
            target_identity: str

            _validate_identity = validate_identity_format("target_identity")
    """

    @field_validator(*field_names)
    def _validate_identity_format(cls, v: str) -> str:
        v = v.strip()
        if not v.lower().startswith("i am "):
            raise ValueError("Identity statement should start with 'I am' (e.g., 'I am a writer')")
        return v

    return _validate_identity_format


def validate_email(*field_names: str) -> Callable:
    """
    Create a basic email format validator.

    Args:
        *field_names: Names of fields to validate

    Returns:
        Pydantic field validator

    Example:
        class AttendeeRequest(BaseModel):
            email: str

            _validate_email = validate_email("email")
    """

    @field_validator(*field_names)
    def _validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v:
            raise ValueError("Invalid email format")
        return v.lower()

    return _validate_email


# =============================================================================
# LIST VALIDATORS
# =============================================================================


def validate_list_max_length(*field_names: str, max_length: int) -> Callable:
    """
    Create a validator that ensures list fields don't exceed max length.

    Args:
        *field_names: Names of fields to validate
        max_length: Maximum allowed list length

    Returns:
        Pydantic field validator

    Example:
        class TaskCreateRequest(BaseModel):
            tags: list[str] = Field(default_factory=list)

            _validate_tags = validate_list_max_length("tags", max_length=20)
    """

    @field_validator(*field_names)
    def _validate_list_max_length(cls, v: list | None) -> list | None:
        if v is not None and len(v) > max_length:
            raise ValueError(f"Maximum {max_length} items allowed")
        return v

    return _validate_list_max_length


def validate_list_no_duplicates(*field_names: str) -> Callable:
    """
    Create a validator that ensures list fields have no duplicates.

    Args:
        *field_names: Names of fields to validate

    Returns:
        Pydantic field validator

    Example:
        class HabitSystemRequest(BaseModel):
            essential_habit_uids: list[str]

            _validate_no_dups = validate_list_no_duplicates("essential_habit_uids")
    """

    @field_validator(*field_names)
    def _validate_no_duplicates(cls, v: list | None) -> list | None:
        if v is not None:
            seen = set()
            duplicates = set()
            for item in v:
                if item in seen:
                    duplicates.add(item)
                seen.add(item)
            if duplicates:
                raise ValueError(f"Duplicate items not allowed: {duplicates}")
        return v

    return _validate_no_duplicates


# =============================================================================
# DATE RANGE VALIDATORS (Model Validators)
# =============================================================================


def validate_date_after(
    later_field: str,
    earlier_field: str,
    allow_equal: bool = False,
) -> Callable:
    """
    Create a model validator that ensures one date is after another.

    Must be used as a model_validator, not field_validator.

    Args:
        later_field: Name of field that should be later
        earlier_field: Name of field that should be earlier
        allow_equal: Whether to allow equal dates (default: False)

    Returns:
        Pydantic model validator

    Example:
        class GoalCreateRequest(BaseModel):
            start_date: date | None = None
            target_date: date | None = None

            @model_validator(mode="after")
            def validate_date_order(self):
                return _validate_date_after_impl(
                    self, "target_date", "start_date", allow_equal=False
                )
    """

    # Return a helper that can be called inside a model_validator
    def validator_impl(instance: Any) -> Any:
        later_value = getattr(instance, later_field, None)
        earlier_value = getattr(instance, earlier_field, None)

        if later_value is not None and earlier_value is not None:
            if allow_equal:
                if later_value < earlier_value:
                    raise ValueError(f"{later_field} must be on or after {earlier_field}")
            else:
                if later_value <= earlier_value:
                    raise ValueError(f"{later_field} must be after {earlier_field}")

        return instance

    return validator_impl


def validate_time_after(
    later_field: str,
    earlier_field: str,
) -> Callable:
    """
    Create a validator helper for time ordering (e.g., end_time after start_time).

    Args:
        later_field: Name of field that should be later
        earlier_field: Name of field that should be earlier

    Returns:
        Validator helper function

    Example:
        class EventCreateRequest(BaseModel):
            start_time: time
            end_time: time

            @field_validator("end_time")
            @classmethod
            def validate_end_time(cls, v, info: ValidationInfo):
                start = info.data.get("start_time")
                if start and v <= start:
                    raise ValueError("End time must be after start time")
                return v
    """

    @field_validator(later_field)
    def _validate_time_order(cls, v: time | None, info: ValidationInfo) -> time | None:
        if v is None:
            return v

        earlier_value = info.data.get(earlier_field)
        if earlier_value and v <= earlier_value:
            raise ValueError(
                f"{later_field.replace('_', ' ').title()} must be after {earlier_field.replace('_', ' ')}"
            )

        return v

    return _validate_time_order


# =============================================================================
# RECURRENCE VALIDATORS
# =============================================================================


def validate_recurrence_end_after_start(
    recurrence_end_field: str,
    start_field: str,
) -> Callable:
    """
    Create a validator that ensures recurrence end is after the start date.

    Args:
        recurrence_end_field: Name of recurrence end date field
        start_field: Name of start/due date field

    Returns:
        Pydantic field validator

    Example:
        class TaskCreateRequest(BaseModel):
            due_date: date | None = None
            recurrence_end_date: date | None = None

            _validate_recurrence = validate_recurrence_end_after_start(
                "recurrence_end_date", "due_date"
            )
    """

    @field_validator(recurrence_end_field)
    def _validate_recurrence_end(cls, v: date | None, info: ValidationInfo) -> date | None:
        if v is None:
            return v

        start_value = info.data.get(start_field)
        if start_value and v <= start_value:
            raise ValueError(f"Recurrence end must be after {start_field.replace('_', ' ')}")

        return v

    return _validate_recurrence_end


# =============================================================================
# CONDITIONAL VALIDATORS
# =============================================================================


def validate_required_when(
    field_name: str,
    condition_field: str,
    condition_value: Any,
    default_value: Any = None,
) -> Callable:
    """
    Create a validator that sets a default when a condition is met.

    Args:
        field_name: Name of field to validate
        condition_field: Name of field to check for condition
        condition_value: Value that triggers the requirement
        default_value: Default value to set if field is None

    Returns:
        Pydantic field validator

    Example:
        class TaskStatusRequest(BaseModel):
            status: ActivityStatus
            completion_date: date | None = None

            # Auto-set completion_date when status is COMPLETED
            _validate_completion = validate_required_when(
                "completion_date",
                condition_field="status",
                condition_value=ActivityStatus.COMPLETED,
                default_value=date.today
            )
    """

    @field_validator(field_name)
    def _validate_required_when(cls, v: Any, info: ValidationInfo) -> Any:
        condition_met = info.data.get(condition_field) == condition_value

        if condition_met and v is None:
            if callable(default_value):
                return default_value()
            return default_value

        return v

    return _validate_required_when


def validate_url_when_online(
    url_field: str,
    online_field: str = "is_online",
) -> Callable:
    """
    Create a validator that requires URL when online flag is True.

    Args:
        url_field: Name of URL field
        online_field: Name of boolean online flag field

    Returns:
        Pydantic field validator

    Example:
        class EventCreateRequest(BaseModel):
            is_online: bool = False
            meeting_url: str | None = None

            _validate_url = validate_url_when_online("meeting_url")
    """

    @field_validator(url_field)
    def _validate_url_when_online(cls, v: str | None, info: ValidationInfo) -> str | None:
        is_online = info.data.get(online_field, False)
        if is_online and not v:
            raise ValueError("URL is required for online events")
        return v

    return _validate_url_when_online


# =============================================================================
# SCORE/PERCENTAGE VALIDATORS
# =============================================================================


def validate_percentage(*field_names: str) -> Callable:
    """
    Create a validator that ensures values are valid percentages (0-100).

    Args:
        *field_names: Names of fields to validate

    Returns:
        Pydantic field validator

    Example:
        class GoalCreateRequest(BaseModel):
            target_value: float | None = None

            _validate_percentage = validate_percentage("target_value")
    """

    @field_validator(*field_names)
    def _validate_percentage(cls, v: float | None) -> float | None:
        if v is not None and (v < 0 or v > 100):
            raise ValueError("Percentage must be between 0 and 100")
        return v

    return _validate_percentage


def validate_score_0_to_1(*field_names: str) -> Callable:
    """
    Create a validator that ensures values are in 0-1 range.

    Args:
        *field_names: Names of fields to validate

    Returns:
        Pydantic field validator

    Example:
        class ChoiceOptionRequest(BaseModel):
            feasibility_score: float

            _validate_score = validate_score_0_to_1("feasibility_score")
    """

    @field_validator(*field_names)
    def _validate_score(cls, v: float | None) -> float | None:
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError("Score must be between 0.0 and 1.0")
        return v

    return _validate_score


# =============================================================================
# DOMAIN-SPECIFIC VALIDATORS
# =============================================================================


def validate_habit_duration_by_difficulty(
    duration_field: str = "duration_minutes",
    difficulty_field: str = "difficulty",
) -> Callable:
    """
    Validate habit duration based on difficulty level.

    - Trivial: max 2 minutes
    - Easy: max 5 minutes
    - Others: no restriction

    Args:
        duration_field: Name of duration field
        difficulty_field: Name of difficulty field

    Returns:
        Pydantic field validator
    """

    @field_validator(duration_field)
    def _validate_duration_by_difficulty(cls, v: int | None, info: ValidationInfo) -> int | None:
        if v is None:
            return v

        # Import here to avoid circular imports
        from core.models.enums.ku_enums import HabitDifficulty

        difficulty = info.data.get(difficulty_field)

        if difficulty == HabitDifficulty.TRIVIAL and v > 2:
            raise ValueError("Trivial habits should be 2 minutes or less")
        elif difficulty == HabitDifficulty.EASY and v > 5:
            raise ValueError("Easy habits should be 5 minutes or less")

        return v

    return _validate_duration_by_difficulty


def validate_habit_target_days_by_pattern(
    target_days_field: str = "target_days_per_week",
    pattern_field: str = "recurrence_pattern",
) -> Callable:
    """
    Validate target days based on recurrence pattern.

    - Daily: at least 5 days
    - Weekly: exactly 1 day

    Args:
        target_days_field: Name of target days field
        pattern_field: Name of recurrence pattern field

    Returns:
        Pydantic field validator
    """

    @field_validator(target_days_field)
    def _validate_target_days(cls, v: int | None, info: ValidationInfo) -> int | None:
        if v is None:
            return v

        from core.models.enums import RecurrencePattern

        pattern = info.data.get(pattern_field)

        if pattern == RecurrencePattern.DAILY and v < 5:
            raise ValueError("Daily habits should target at least 5 days per week")
        elif pattern == RecurrencePattern.WEEKLY and v > 1:
            raise ValueError("Weekly habits should target 1 day per week")

        return v

    return _validate_target_days


def validate_timeframe_date_alignment() -> Callable:
    """
    Create a model validator that checks goal timeframe aligns with dates.

    Returns:
        Validator helper function to use in model_validator

    Example:
        class GoalCreateRequest(BaseModel):
            start_date: date | None = None
            target_date: date | None = None
            timeframe: GoalTimeframe

            @model_validator(mode="after")
            def validate_alignment(self):
                return _validate_timeframe_alignment_impl(self)
    """

    def validator_impl(instance: Any) -> Any:
        # Import here to avoid circular imports
        from core.models.enums.ku_enums import GoalTimeframe

        start_date = getattr(instance, "start_date", None) or date.today()
        target_date = getattr(instance, "target_date", None)
        timeframe = getattr(instance, "timeframe", None)

        if target_date and timeframe:
            days_diff = (target_date - start_date).days

            limits = {
                GoalTimeframe.DAILY: (1, "Daily goals should complete within 1 day"),
                GoalTimeframe.WEEKLY: (7, "Weekly goals should complete within 7 days"),
                GoalTimeframe.MONTHLY: (31, "Monthly goals should complete within 31 days"),
                GoalTimeframe.QUARTERLY: (92, "Quarterly goals should complete within 92 days"),
                GoalTimeframe.YEARLY: (365, "Yearly goals should complete within 365 days"),
            }

            if timeframe in limits:
                max_days, message = limits[timeframe]
                if days_diff > max_days:
                    raise ValueError(message)

        return instance

    return validator_impl


# =============================================================================
# WEIGHTS/PREFERENCES VALIDATORS
# =============================================================================


def validate_weights_sum_to_one(
    field_name: str,
    required_keys: set[str] | None = None,
    tolerance: float = 0.05,
) -> Callable:
    """
    Create a validator that ensures weight dict values sum to 1.0.

    Args:
        field_name: Name of weights dict field
        required_keys: Set of required keys (optional)
        tolerance: Allowed deviation from 1.0 (default: 0.05)

    Returns:
        Pydantic field validator

    Example:
        class RankingRequest(BaseModel):
            weights: dict[str, float]

            _validate_weights = validate_weights_sum_to_one(
                "weights",
                required_keys={"impact", "feasibility", "risk"}
            )
    """

    @field_validator(field_name)
    def _validate_weights(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is None:
            return v

        # Check required keys
        if required_keys:
            missing = required_keys - v.keys()
            if missing:
                raise ValueError(f"Missing required keys: {missing}")

        # Check all values are in valid range
        for key, weight in v.items():
            if not (0.0 <= weight <= 1.0):
                raise ValueError(f"Weight '{key}' must be between 0.0 and 1.0")

        # Check sum
        total = sum(v.values())
        if not (1.0 - tolerance <= total <= 1.0 + tolerance):
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        return v

    return _validate_weights
