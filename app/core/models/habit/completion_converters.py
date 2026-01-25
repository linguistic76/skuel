"""
Habit Completion Converters
============================

Conversion functions between the three tiers of habit completion models:
- External (Pydantic) ↔ Transfer (DTO) ↔ Core (Domain)

These converters ensure smooth data flow throughout the application.
"""

from datetime import datetime
from typing import Any

from .completion import HabitCompletion
from .completion_dto import HabitCompletionDTO
from .habit_completion_request import HabitCompletionCreateRequest

# ============================================================================
# EXTERNAL → TRANSFER (Request → DTO)
# ============================================================================


def completion_create_request_to_dto(request: HabitCompletionCreateRequest) -> HabitCompletionDTO:
    """
    Convert HabitCompletionCreateRequest to HabitCompletionDTO.

    Args:
        request: Validated external request,

    Returns:
        DTO ready for service operations
    """
    return HabitCompletionDTO.create(
        habit_uid=request.habit_uid,
        completed_at=request.completed_at,
        notes=request.notes,
        quality=request.quality,
        duration_actual=request.duration_actual,
    )


# NOTE: completion_update_request_to_dto_updates() removed - use generic helper directly:
#   - from core.utils.converter_helpers import update_request_to_dict
#   - updates = update_request_to_dict(request)
#
# This eliminates domain-specific wrappers in favor of the generic pattern.
# The helper works for ANY domain's update request (Pydantic BaseModel).


# ============================================================================
# TRANSFER ↔ CORE (DTO ↔ Domain)
# ============================================================================


def completion_dto_to_domain(dto: HabitCompletionDTO) -> HabitCompletion:
    """
    Convert HabitCompletionDTO to HabitCompletion domain model.

    Args:
        dto: Transfer object,

    Returns:
        Immutable domain model with business logic
    """
    return HabitCompletion.from_dto(dto)


def completion_domain_to_dto(completion: HabitCompletion) -> HabitCompletionDTO:
    """
    Convert HabitCompletion domain model to HabitCompletionDTO.

    Args:
        completion: Domain model,

    Returns:
        Mutable DTO for transfer operations
    """
    return completion.to_dto()


# ============================================================================
# EXTERNAL → CORE (Direct conversion for read operations)
# ============================================================================


def completion_create_request_to_domain(request: HabitCompletionCreateRequest) -> HabitCompletion:
    """
    Direct conversion from create request to domain model.
    Useful for operations that don't need intermediate DTO manipulation.

    Args:
        request: Validated external request,

    Returns:
        Immutable domain model
    """
    dto = completion_create_request_to_dto(request)
    return completion_dto_to_domain(dto)


# ============================================================================
# DATABASE OPERATIONS (Dict ↔ DTO)
# ============================================================================


def completion_dict_to_dto(data: dict[str, Any]) -> HabitCompletionDTO:
    """
    Convert dictionary (from database) to HabitCompletionDTO.

    Args:
        data: Raw dictionary from database/Neo4j,

    Returns:
        DTO with parsed and validated data
    """
    return HabitCompletionDTO.from_dict(data)


def completion_dto_to_dict(dto: HabitCompletionDTO) -> dict[str, Any]:
    """
    Convert HabitCompletionDTO to dictionary for database storage.

    Args:
        dto: Transfer object,

    Returns:
        Dictionary ready for database operations
    """
    return dto.to_dict()


# ============================================================================
# BULK OPERATIONS
# ============================================================================


def completion_create_requests_to_dtos(
    requests: list[HabitCompletionCreateRequest],
) -> list[HabitCompletionDTO]:
    """
    Convert multiple create requests to DTOs.

    Args:
        requests: List of validated external requests,

    Returns:
        List of DTOs ready for bulk operations
    """
    return [completion_create_request_to_dto(request) for request in requests]


def completion_dtos_to_domains(dtos: list[HabitCompletionDTO]) -> list[HabitCompletion]:
    """
    Convert multiple DTOs to domain models.

    Args:
        dtos: List of transfer objects,

    Returns:
        List of immutable domain models
    """
    return [completion_dto_to_domain(dto) for dto in dtos]


def completion_dicts_to_domains(dicts: list[dict[str, Any]]) -> list[HabitCompletion]:
    """
    Convert multiple dictionaries directly to domain models.
    Useful for bulk database read operations.

    Args:
        dicts: List of raw dictionaries from database,

    Returns:
        List of immutable domain models
    """
    dtos = [completion_dict_to_dto(data) for data in dicts]
    return completion_dtos_to_domains(dtos)


# ============================================================================
# VALIDATION AND ERROR HANDLING
# ============================================================================


def validate_completion_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and clean completion data before conversion.

    Uses generic validation helpers from validation_helpers.py.

    Args:
        data: Raw data dictionary,

    Returns:
        Cleaned and validated data

    Raises:
        ValueError: If data is invalid
    """
    from core.utils.validation_helpers import (
        parse_datetime_fields,
        validate_required_fields,
    )

    # Validate required fields
    validate_required_fields(data, ["habit_uid"])

    # Validate quality (1-5 range)
    if "quality" in data and data["quality"] is not None:
        quality = data["quality"]
        if not isinstance(quality, int) or not (1 <= quality <= 5):
            raise ValueError("Quality must be an integer between 1 and 5")

    # Validate duration (non-negative)
    if "duration_actual" in data and data["duration_actual"] is not None:
        duration = data["duration_actual"]
        if not isinstance(duration, int) or duration < 0:
            raise ValueError("Duration must be a non-negative integer")

    # Parse datetime fields
    parse_datetime_fields(data, ["completed_at", "created_at", "updated_at"])

    return data


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def enrich_completion_dto_with_metadata(
    dto: HabitCompletionDTO, metadata: dict[str, Any]
) -> HabitCompletionDTO:
    """
    Add metadata to a completion DTO.

    Args:
        dto: Completion DTO to enrich,
        metadata: Additional metadata to add

    Returns:
        DTO with enriched metadata
    """
    dto.metadata.update(metadata)
    dto.updated_at = datetime.now()
    return dto


def extract_completion_summary(completion: HabitCompletion) -> dict[str, Any]:
    """
    Extract a summary of completion for analytics.

    Args:
        completion: Domain model,

    Returns:
        Summary dictionary with key metrics
    """
    return {
        "uid": completion.uid,
        "habit_uid": completion.habit_uid,
        "completed_at": completion.completed_at.isoformat(),
        "quality": completion.quality,
        "duration_actual": completion.duration_actual,
        "has_notes": completion.has_meaningful_notes(),
        "is_high_quality": completion.is_high_quality(),
        "completion_score": completion.completion_score(),
        "time_of_day": completion.completion_time_of_day(),
        "satisfaction_level": completion.satisfaction_level(),
    }
