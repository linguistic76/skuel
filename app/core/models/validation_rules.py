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

from collections.abc import Callable, Mapping
from datetime import date, datetime, time

from pydantic import BaseModel, ValidationInfo, field_validator

from core.constants import EventSpan
from core.utils.timestamp_helpers import as_utc, now_utc, today_in
from core.utils.zone_context import current_zone

# =============================================================================
# FUTURE DATE VALIDATORS
# =============================================================================


def validate_future_date(*field_names: str) -> Callable:
    """
    Create a validator that ensures date fields are not in the past.

    Works with both `date` and `datetime` types. A `date` is compared with today
    in the current zone; a `datetime` is an instant — a ``ClientDateTime``
    field's value is already on the stored clock when this runs — compared as
    aware UTC with now.

    **Ingestion-context relaxation (G10, Arc E):** validation context
    ``{"allow_past_dates": True}`` skips the check. Interactive creation
    (constructor / FastHTML-Pydantic auto-validation) passes no context, so
    the guard stands there; the EXTRACT_ACTIVITIES converters pass the
    context via ``model_validate`` because historical vault notes
    legitimately carry past dates — rejecting them made those notes
    permanently unable to create their activities.

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
    def _validate_future_date(
        cls, v: date | datetime | None, info: ValidationInfo
    ) -> date | datetime | None:
        if v is None:
            return v

        if info.context and info.context.get("allow_past_dates"):
            return v

        if isinstance(v, datetime):
            if as_utc(v) <= now_utc():
                raise ValueError("Date/time cannot be in the past")
        elif isinstance(v, date) and v < today_in(current_zone()):
            raise ValueError("Date cannot be in the past")

        return v

    return _validate_future_date


def validate_past_date(*field_names: str) -> Callable:
    """
    Create a validator that ensures date fields are not in the future.

    Useful for completion dates, decision dates, etc. Compares as
    ``validate_future_date`` does: a `date` with today in the current zone, a
    `datetime` as the instant it names.

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
            if as_utc(v) > now_utc():
                raise ValueError("Date/time cannot be in the future")
        elif isinstance(v, date) and v > today_in(current_zone()):
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
    def validator_impl[M: BaseModel](instance: M) -> M:
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


ONLINE_URL_REQUIRED = "URL is required for online events"


def validate_url_when_online(
    url_field: str = "meeting_url",
    online_field: str = "is_online",
) -> Callable:
    """
    Create a model validator helper that requires a URL when the online flag is set.

    Must be called from a ``model_validator(mode="after")``, not attached as a
    field validator: Pydantic does not validate an omitted field's default, so a
    field validator on the URL never runs for a request that leaves the key out —
    exactly the request this rule exists to refuse. After validation every field
    holds a value, sent or defaulted, so the check sees the whole request.

    An empty string counts as missing.

    Args:
        url_field: Name of URL field
        online_field: Name of boolean online flag field

    Returns:
        A callable taking the validated model instance and returning it unchanged,
        raising ``ValueError`` when the instance is online without a URL.

    Example:
        class EventCreateRequest(BaseModel):
            is_online: bool = False
            meeting_url: str | None = None

            @model_validator(mode="after")
            def _require_url_when_online(self) -> Self:
                return validate_url_when_online("meeting_url", "is_online")(self)
    """

    def validator_impl[M: BaseModel](instance: M) -> M:
        if getattr(instance, online_field, False) and not getattr(instance, url_field, None):
            raise ValueError(ONLINE_URL_REQUIRED)
        return instance

    return validator_impl


def patch_leaves_online_without_url(
    changes: Mapping[str, object], *, is_online: bool, meeting_url: str | None
) -> bool:
    """
    Whether a partial update would leave an entity online without a meeting URL.

    The update-side half of ``validate_url_when_online``: a patch carries only the
    fields it changes, so the rule is judged on the merged state — each field from
    the patch when the patch names it, else the stored value (``is_online`` /
    ``meeting_url``). A patch that names neither field returns ``False`` whatever
    the stored state, so a status change or a reschedule never trips over an
    entity already stored online without a URL.

    Args:
        changes: The materialized patch (``to_changes()``)
        is_online: The stored online flag
        meeting_url: The stored meeting URL

    Returns:
        True when the patch touches either field and the merged state is online
        with no URL (``None`` or ``""``).
    """
    if "is_online" not in changes and "meeting_url" not in changes:
        return False
    merged_online = changes.get("is_online", is_online)
    merged_url = changes.get("meeting_url", meeting_url)
    return bool(merged_online) and not merged_url


def event_span_error(start_time: time | None, end_time: time | None) -> str | None:
    """
    Why an event's span is out of bounds, or ``None`` when it is within them.

    The span is ``end_time - start_time`` on the event's day, and must lie within
    ``EventSpan.MIN_MINUTES`` - ``EventSpan.MAX_MINUTES``. An end before the start is
    a negative span, so it is refused as too short. With either time missing there
    is no span to judge, and the result is ``None``.

    Args:
        start_time: The event's start time
        end_time: The event's end time

    Returns:
        The refusal message, or ``None``.
    """
    if start_time is None or end_time is None:
        return None
    span = (end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)
    if span < EventSpan.MIN_MINUTES:
        return f"Event must last at least {EventSpan.MIN_MINUTES} minutes"
    if span > EventSpan.MAX_MINUTES:
        return (
            f"Event must last at most {EventSpan.MAX_MINUTES // 60} hours. "
            "Use a multi-day event or split it into sessions."
        )
    return None


def patch_span_error(
    changes: Mapping[str, object], *, start_time: time | None, end_time: time | None
) -> str | None:
    """
    Why a partial update would leave an event's span out of bounds, or ``None``.

    The update-side half of ``event_span_error``, judged on the merged state — each
    time from the patch when the patch names it, else the stored one. A patch that
    names neither ``start_time`` nor ``end_time`` returns ``None`` whatever the stored
    span, so a status change or a date move never trips over an event already stored
    out of bounds.

    Args:
        changes: The materialized patch (``to_changes()``)
        start_time: The stored start time
        end_time: The stored end time

    Returns:
        The refusal message, or ``None``.
    """
    if "start_time" not in changes and "end_time" not in changes:
        return None
    merged_start = changes.get("start_time", start_time)
    merged_end = changes.get("end_time", end_time)
    return event_span_error(
        merged_start if isinstance(merged_start, time) else None,
        merged_end if isinstance(merged_end, time) else None,
    )


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
        from core.models.enums.habit_enums import HabitDifficulty

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

    def validator_impl[M: BaseModel](instance: M) -> M:
        # Import here to avoid circular imports
        from core.models.enums.goal_enums import GoalTimeframe

        start_date = getattr(instance, "start_date", None) or today_in(current_zone())
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
