"""
DTO Conversion Helpers
======================

Small, focused utility functions for common DTO operations.

Following SKUEL principles:
- Explicit over implicit
- Small, single-purpose functions
- No base class complexity
- Easy to understand and debug

These helpers eliminate repetitive boilerplate in DTO conversion methods
while preserving explicitness and clarity.

Version: 1.0.0
Date: 2025-10-21
"""

from datetime import date, datetime, time
from enum import Enum
from typing import Any

from core.services.protocols import EnumLike


def filter_deprecated_fields(data: dict, deprecated_fields: list[str]) -> None:
    """
    Remove deprecated fields from data dictionary in-place.

    Used during DTO from_dict() to handle backward compatibility with databases
    that still contain graph-native fields that have been migrated to relationships.

    Args:
        data: Dictionary to modify
        deprecated_fields: List of field names to remove

    Example:
        data = {'uid': '123', 'subtask_uids': ['a', 'b'], 'title': 'Task'}
        filter_deprecated_fields(data, ['subtask_uids'])
        # data is now {'uid': '123', 'title': 'Task'}

    Note: This is part of the graph-native migration pattern where relationship
    lists are removed from DTOs and queried dynamically via relationship services.
    """
    for field in deprecated_fields:
        data.pop(field, None)


def parse_datetime_field(data: dict, field_name: str) -> None:
    """
    Parse datetime field in-place if it's a string.

    Args:
        data: Dictionary to modify
        field_name: Field name to parse

    Example:
        data = {'created_at': '2025-10-21T10:30:00'}
        parse_datetime_field(data, 'created_at')
        # data['created_at'] is now datetime(2025, 10, 21, 10, 30, 0)
    """
    if field_name in data and isinstance(data[field_name], str):
        data[field_name] = datetime.fromisoformat(data[field_name])


def parse_date_field(data: dict, field_name: str) -> None:
    """
    Parse date field in-place if it's a string.

    Args:
        data: Dictionary to modify
        field_name: Field name to parse

    Example:
        data = {'due_date': '2025-10-21'}
        parse_date_field(data, 'due_date')
        # data['due_date'] is now date(2025, 10, 21)
    """
    if field_name in data and isinstance(data[field_name], str):
        data[field_name] = date.fromisoformat(data[field_name])


def parse_time_field(data: dict, field_name: str) -> None:
    """
    Parse time field in-place if it's a string.

    Args:
        data: Dictionary to modify
        field_name: Field name to parse

    Example:
        data = {'start_time': '10:30:00'}
        parse_time_field(data, 'start_time')
        # data['start_time'] is now time(10, 30, 0)
    """
    if field_name in data and isinstance(data[field_name], str):
        data[field_name] = time.fromisoformat(data[field_name])


def parse_enum_field(data: dict, field_name: str, enum_class: type[Enum]) -> None:
    """
    Parse enum field in-place if it's a string.

    Args:
        data: Dictionary to modify
        field_name: Field name to parse
        enum_class: Enum class to instantiate (must be type[Enum])

    Example:
        data = {'status': 'active'}
        parse_enum_field(data, 'status', KuStatus)
        # data['status'] is now KuStatus.ACTIVE
    """
    if field_name in data and isinstance(data[field_name], str):
        data[field_name] = enum_class(data[field_name])


def ensure_list_field(data: dict, field_name: str) -> None:
    """
    Ensure field is a list, converting None to [].

    Also converts tuples to lists (for frozen model compatibility).

    Args:
        data: Dictionary to modify
        field_name: Field name to ensure is a list

    Example:
        data = {'tags': None}
        ensure_list_field(data, 'tags')
        # data['tags'] is now []
    """
    if field_name in data:
        if data[field_name] is None:
            data[field_name] = []
        elif not isinstance(data[field_name], list):
            data[field_name] = list(data[field_name])


def ensure_dict_field(data: dict, field_name: str) -> None:
    """
    Ensure field is a dict, converting None to {}.

    Args:
        data: Dictionary to modify
        field_name: Field name to ensure is a dict

    Example:
        data = {'metadata': None}
        ensure_dict_field(data, 'metadata')
        # data['metadata'] is now {}
    """
    if field_name in data and data[field_name] is None:
        data[field_name] = {}


def serialize_datetime(value: datetime | None) -> str | None:
    """
    Serialize datetime to ISO format string.

    Args:
        value: Datetime to serialize

    Returns:
        ISO format string or None

    Example:
        serialize_datetime(datetime(2025, 10, 21, 10, 30))
        # Returns '2025-10-21T10:30:00'
    """
    if value and isinstance(value, datetime):
        return value.isoformat()
    return None


def serialize_date(value: date | None) -> str | None:
    """
    Serialize date to ISO format string.

    Args:
        value: Date to serialize

    Returns:
        ISO format string or None

    Example:
        serialize_date(date(2025, 10, 21))
        # Returns '2025-10-21'
    """
    if value and isinstance(value, date):
        return value.isoformat()
    return None


def serialize_time(value: time | None) -> str | None:
    """
    Serialize time to ISO format string.

    Args:
        value: Time to serialize

    Returns:
        ISO format string or None

    Example:
        serialize_time(time(10, 30))
        # Returns '10:30:00'
    """
    if value and isinstance(value, time):
        return value.isoformat()
    return None


def serialize_enum(value: Any) -> str | Any:
    """
    Serialize enum to its value string.

    Args:
        value: Enum to serialize

    Returns:
        Enum value or original value if not an enum

    Example:
        serialize_enum(KuStatus.ACTIVE)
        # Returns 'active'
    """
    if isinstance(value, EnumLike):
        return value.value
    return value


def convert_dates_to_iso(data: dict, field_names: list[str]) -> None:
    """
    Convert multiple date fields to ISO format in-place.

    Args:
        data: Dictionary to modify
        field_names: List of field names to convert

    Example:
        data = {
            'start_date': date(2025, 10, 21),
            'end_date': date(2025, 12, 31)
        }
        convert_dates_to_iso(data, ['start_date', 'end_date'])
        # Both fields are now ISO strings
    """
    for field_name in field_names:
        if field_name in data and isinstance(data[field_name], date):
            data[field_name] = data[field_name].isoformat()


def convert_datetimes_to_iso(data: dict, field_names: list[str]) -> None:
    """
    Convert multiple datetime fields to ISO format in-place.

    Args:
        data: Dictionary to modify
        field_names: List of field names to convert

    Example:
        data = {
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        convert_datetimes_to_iso(data, ['created_at', 'updated_at'])
        # Both fields are now ISO strings
    """
    for field_name in field_names:
        if field_name in data and isinstance(data[field_name], datetime):
            data[field_name] = data[field_name].isoformat()


def convert_enums_to_values(data: dict, field_names: list[str]) -> None:
    """
    Convert multiple enum fields to their values in-place.

    Args:
        data: Dictionary to modify
        field_names: List of field names to convert

    Example:
        data = {
            'status': KuStatus.ACTIVE,
            'priority': Priority.HIGH
        }
        convert_enums_to_values(data, ['status', 'priority'])
        # Both fields are now strings ('active', 'high')
    """
    for field_name in field_names:
        if field_name in data and isinstance(data[field_name], EnumLike):
            data[field_name] = data[field_name].value


# Batch parsing helpers for from_dict()


def parse_date_fields(data: dict, field_names: list[str]) -> None:
    """
    Parse multiple date fields in-place.

    Args:
        data: Dictionary to modify
        field_names: List of field names to parse
    """
    for field_name in field_names:
        parse_date_field(data, field_name)


def parse_datetime_fields(data: dict, field_names: list[str]) -> None:
    """
    Parse multiple datetime fields in-place.

    Args:
        data: Dictionary to modify
        field_names: List of field names to parse
    """
    for field_name in field_names:
        parse_datetime_field(data, field_name)


def parse_time_fields(data: dict, field_names: list[str]) -> None:
    """
    Parse multiple time fields in-place.

    Args:
        data: Dictionary to modify
        field_names: List of field names to parse
    """
    for field_name in field_names:
        parse_time_field(data, field_name)


def ensure_list_fields(data: dict, field_names: list[str]) -> None:
    """
    Ensure multiple fields are lists.

    Args:
        data: Dictionary to modify
        field_names: List of field names to ensure are lists
    """
    for field_name in field_names:
        ensure_list_field(data, field_name)


def ensure_dict_fields(data: dict, field_names: list[str]) -> None:
    """
    Ensure multiple fields are dicts.

    Args:
        data: Dictionary to modify
        field_names: List of field names to ensure are dicts
    """
    for field_name in field_names:
        ensure_dict_field(data, field_name)


# =============================================================================
# DTO UPDATE HELPERS
# =============================================================================


def update_from_dict(
    dto: Any,
    updates: dict[str, Any],
    *,
    enum_mappings: dict[str, type[Enum]] | None = None,
    skip_none: bool = True,
    allowed_fields: set[str] | None = None,
    blocked_fields: set[str] | None = None,
) -> None:
    """
    Update a DTO's fields from a dictionary.

    This is the canonical implementation for DTO update_from() methods.
    Consolidates 5 different patterns found across the codebase into one
    configurable function.

    Args:
        dto: The DTO instance to update
        updates: Dictionary of field names to values
        enum_mappings: Optional dict mapping field names to Enum classes for conversion
        skip_none: If True, skip updates where value is None (default: True)
        allowed_fields: If provided, only update fields in this set (whitelist)
        blocked_fields: If provided, never update fields in this set (blacklist)

    Examples:
        # Simple case (TaskDTO pattern)
        update_from_dict(self, updates)

        # With enum conversion (GoalDTO pattern)
        update_from_dict(self, updates, enum_mappings={
            "goal_type": GoalType,
            "status": KuStatus,
            "priority": Priority,
        })

        # With whitelist (KuDTO pattern)
        update_from_dict(self, updates, allowed_fields={
            "title", "content", "domain", "tags"
        })

        # With blacklist (MilestoneDTO pattern)
        update_from_dict(self, updates, blocked_fields={"uid", "goal_uid"})

    Note:
        Always updates `updated_at` field to datetime.now() if it exists.
    """
    from contextlib import suppress

    for key, value in updates.items():
        # Skip None values if configured
        if skip_none and value is None:
            continue

        # Apply whitelist filter
        if allowed_fields is not None and key not in allowed_fields:
            continue

        # Apply blacklist filter
        if blocked_fields is not None and key in blocked_fields:
            continue

        # Convert string to enum if mapping exists
        if enum_mappings and key in enum_mappings and isinstance(value, str):
            value = enum_mappings[key](value)

        # Set attribute, silently skip unknown fields
        with suppress(AttributeError):
            setattr(dto, key, value)

    # Always update timestamp if field exists
    with suppress(AttributeError):
        dto.updated_at = datetime.now()


# =============================================================================
# GENERIC DTO SERIALIZATION HELPERS
# =============================================================================


def dto_to_dict(
    obj: Any,
    *,
    enum_fields: list[str],
    date_fields: list[str] | None = None,
    datetime_fields: list[str] | None = None,
    time_fields: list[str] | None = None,
    nested_date_fields: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """
    Generic DTO to dictionary serialization.

    Consolidates the common pattern of asdict() + enum/date/datetime conversion
    that appears in 20+ DTOs. Keeps serialization explicit while eliminating
    duplicated conversion logic.

    Args:
        obj: Dataclass instance to serialize
        enum_fields: Fields containing enums to convert to values
        date_fields: Fields containing dates to convert to ISO format
        datetime_fields: Fields containing datetimes to convert to ISO format
        time_fields: Fields containing times to convert to ISO format
        nested_date_fields: Dict mapping list field name -> date field names within items
                           For handling nested objects like GoalDTO.milestones

    Returns:
        Dictionary with all fields serialized to JSON-compatible types

    Example:
        # TaskDTO
        return dto_to_dict(
            self,
            enum_fields=["status", "priority", "recurrence_pattern"],
            date_fields=["due_date", "scheduled_date", "completion_date"],
            datetime_fields=["created_at", "updated_at"],
        )

        # GoalDTO with nested milestones
        return dto_to_dict(
            self,
            enum_fields=["goal_type", "domain", "timeframe", "status", "priority"],
            date_fields=["start_date", "target_date", "achieved_date"],
            datetime_fields=["created_at", "updated_at", "last_progress_update"],
            nested_date_fields={"milestones": ["target_date", "achieved_date"]},
        )
    """
    from dataclasses import asdict

    data = asdict(obj)

    # Convert enums to their values
    convert_enums_to_values(data, enum_fields)

    # Convert dates to ISO format
    if date_fields:
        convert_dates_to_iso(data, date_fields)

    # Convert datetimes to ISO format
    if datetime_fields:
        convert_datetimes_to_iso(data, datetime_fields)

    # Convert times to ISO format
    if time_fields:
        for field_name in time_fields:
            if field_name in data and isinstance(data[field_name], time):
                data[field_name] = data[field_name].isoformat()

    # Handle nested objects (e.g., milestones in GoalDTO)
    if nested_date_fields:
        for list_field, fields in nested_date_fields.items():
            for item in data.get(list_field, []):
                convert_dates_to_iso(item, fields)

    return data


def dto_from_dict[T](
    cls: type[T],
    data: dict[str, Any],
    *,
    enum_fields: dict[str, type[Enum]],
    date_fields: list[str] | None = None,
    datetime_fields: list[str] | None = None,
    time_fields: list[str] | None = None,
    list_fields: list[str] | None = None,
    dict_fields: list[str] | None = None,
    deprecated_fields: list[str] | None = None,
) -> T:
    """
    Generic dictionary to DTO deserialization.

    Consolidates the common pattern of parse + ensure + construct that appears
    in 20+ DTOs. Keeps deserialization explicit while eliminating duplicated
    parsing logic.

    Args:
        cls: DTO class to instantiate
        data: Dictionary with field data (modified in-place for efficiency)
        enum_fields: Dict mapping field name -> Enum class for parsing
        date_fields: Fields to parse as date from ISO strings
        datetime_fields: Fields to parse as datetime from ISO strings
        time_fields: Fields to parse as time from ISO strings
        list_fields: Fields to ensure are lists (None -> [])
        dict_fields: Fields to ensure are dicts (None -> {})
        deprecated_fields: Fields to remove (backward compatibility)

    Returns:
        DTO instance of type cls

    Example:
        # TaskDTO
        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "status": KuStatus,
                "priority": Priority,
                "recurrence_pattern": RecurrencePattern,
            },
            date_fields=["due_date", "scheduled_date", "completion_date"],
            datetime_fields=["created_at", "updated_at"],
            list_fields=["tags", "knowledge_patterns_detected"],
            dict_fields=["metadata", "knowledge_confidence_scores"],
        )
    """
    from dataclasses import fields as dataclass_fields
    from dataclasses import is_dataclass

    # Filter deprecated fields first
    if deprecated_fields:
        filter_deprecated_fields(data, deprecated_fields)

    # Parse date/datetime/time strings
    if date_fields:
        parse_date_fields(data, date_fields)
    if datetime_fields:
        parse_datetime_fields(data, datetime_fields)
    if time_fields:
        parse_time_fields(data, time_fields)

    # Parse enums from string values
    for field_name, enum_class in enum_fields.items():
        parse_enum_field(data, field_name, enum_class)

    # Ensure collection fields are initialized
    if list_fields:
        ensure_list_fields(data, list_fields)
    if dict_fields:
        ensure_dict_fields(data, dict_fields)

    # Filter out fields that don't exist in the dataclass
    #
    # ARCHITECTURAL DECISION (2026-02-01):
    # Infrastructure fields (embeddings, indexes) are filtered out from DTOs.
    # Embeddings are stored in Neo4j for vector search but are NOT part of
    # the domain model. Application code doesn't need raw 1536-dim vectors.
    #
    # This handles cases where Neo4j returns extra properties that aren't
    # defined in the DTO:
    # - embedding: 1536-dimensional vector for semantic search
    # - embedding_version: OpenAI model version (e.g., "text-embedding-3-small")
    # - embedding_model: Model name
    # - embedding_updated_at: When embedding was last generated
    #
    # All Activity domains (Task, Goal, Habit, Event, Choice, Principle) have
    # embeddings stored in Neo4j but excluded from DTOs for consistency.
    #
    # See: /docs/patterns/three_tier_type_system.md
    if is_dataclass(cls):
        valid_field_names = {f.name for f in dataclass_fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_field_names}
        return cls(**filtered_data)

    return cls(**data)
