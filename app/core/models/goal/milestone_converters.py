"""
Milestone Converters
====================

Conversion functions between the three tiers of standalone milestone models:
- External (Pydantic) ↔ Transfer (DTO) ↔ Core (Domain)

These converters ensure smooth data flow throughout the application.

Note: This is for standalone milestone management. The Goal model
contains its own embedded milestone conversion logic.
"""

from datetime import datetime
from operator import attrgetter
from typing import Any

from .goal_milestone_request import (
    StandaloneMilestoneCompleteRequest,
    StandaloneMilestoneCreateRequest,
)
from .milestone_dto import MilestoneDTO
from .milestone_pure import Milestone

# ============================================================================
# EXTERNAL → TRANSFER (Request → DTO)
# ============================================================================


def milestone_create_request_to_dto(request: StandaloneMilestoneCreateRequest) -> MilestoneDTO:
    """
    Convert StandaloneMilestoneCreateRequest to MilestoneDTO.

    Args:
        request: Validated external request,

    Returns:
        DTO ready for service operations
    """
    return MilestoneDTO.create(
        goal_uid=request.goal_uid,
        title=request.title,
        description=request.description,
        target_date=request.target_date,
        order=request.order,
    )


# NOTE: milestone_update_request_to_dto_updates() removed - use generic helper directly:
#   - from core.utils.converter_helpers import update_request_to_dict
#   - updates = update_request_to_dict(request)
#
# This eliminates domain-specific wrappers in favor of the generic pattern.
# The helper works for ANY domain's update request (Pydantic BaseModel).


def milestone_complete_request_to_dto_updates(
    request: StandaloneMilestoneCompleteRequest,
) -> dict[str, Any]:
    """
    Convert StandaloneMilestoneCompleteRequest to update dictionary for DTO.

    Args:
        request: Validated completion request,

    Returns:
        Dictionary of fields to update for completion
    """
    updates = {
        "is_completed": True,
        "completed_date": request.completed_date,
        "updated_at": datetime.now(),
    }

    # Add completion notes to metadata if provided
    if request.notes:
        # We need to handle metadata carefully since it might not exist
        updates["metadata"] = {"completion_notes": request.notes}

    return updates


# ============================================================================
# TRANSFER ↔ CORE (DTO ↔ Domain)
# ============================================================================


def milestone_dto_to_domain(dto: MilestoneDTO) -> Milestone:
    """
    Convert MilestoneDTO to Milestone domain model.

    Args:
        dto: Transfer object,

    Returns:
        Immutable domain model with business logic
    """
    return Milestone.from_dto(dto)


def milestone_domain_to_dto(milestone: Milestone) -> MilestoneDTO:
    """
    Convert Milestone domain model to MilestoneDTO.

    Args:
        milestone: Domain model,

    Returns:
        Mutable DTO for transfer operations
    """
    return milestone.to_dto()


# ============================================================================
# EXTERNAL → CORE (Direct conversion for read operations)
# ============================================================================


def milestone_create_request_to_domain(request: StandaloneMilestoneCreateRequest) -> Milestone:
    """
    Direct conversion from create request to domain model.
    Useful for operations that don't need intermediate DTO manipulation.

    Args:
        request: Validated external request,

    Returns:
        Immutable domain model
    """
    dto = milestone_create_request_to_dto(request)
    return milestone_dto_to_domain(dto)


# ============================================================================
# DATABASE OPERATIONS (Dict ↔ DTO)
# ============================================================================


def milestone_dict_to_dto(data: dict[str, Any]) -> MilestoneDTO:
    """
    Convert dictionary (from database) to MilestoneDTO.

    Args:
        data: Raw dictionary from database/Neo4j,

    Returns:
        DTO with parsed and validated data
    """
    return MilestoneDTO.from_dict(data)


def milestone_dto_to_dict(dto: MilestoneDTO) -> dict[str, Any]:
    """
    Convert MilestoneDTO to dictionary for database storage.

    Args:
        dto: Transfer object,

    Returns:
        Dictionary ready for database operations
    """
    return dto.to_dict()


# ============================================================================
# BULK OPERATIONS
# ============================================================================


def milestone_create_requests_to_dtos(
    requests: list[StandaloneMilestoneCreateRequest],
) -> list[MilestoneDTO]:
    """
    Convert multiple create requests to DTOs.

    Args:
        requests: List of validated external requests,

    Returns:
        List of DTOs ready for bulk operations
    """
    return [milestone_create_request_to_dto(request) for request in requests]


def milestone_dtos_to_domains(dtos: list[MilestoneDTO]) -> list[Milestone]:
    """
    Convert multiple DTOs to domain models.

    Args:
        dtos: List of transfer objects,

    Returns:
        List of immutable domain models
    """
    return [milestone_dto_to_domain(dto) for dto in dtos]


def milestone_dicts_to_domains(dicts: list[dict[str, Any]]) -> list[Milestone]:
    """
    Convert multiple dictionaries directly to domain models.
    Useful for bulk database read operations.

    Args:
        dicts: List of raw dictionaries from database,

    Returns:
        List of immutable domain models
    """
    dtos = [milestone_dict_to_dto(data) for data in dicts]
    return milestone_dtos_to_domains(dtos)


# ============================================================================
# MILESTONE ORDERING AND MANAGEMENT
# ============================================================================


def reorder_milestones_dtos(dtos: list[MilestoneDTO], new_order: list[str]) -> list[MilestoneDTO]:
    """
    Reorder milestone DTOs based on new UID order.

    Args:
        dtos: List of milestone DTOs,
        new_order: List of UIDs in desired order

    Returns:
        List of DTOs with updated order values
    """
    # Create a mapping from UID to DTO
    dto_map = {dto.uid: dto for dto in dtos}

    # Update order based on position in new_order list
    reordered_dtos = []
    for i, uid in enumerate(new_order):
        if uid in dto_map:
            dto = dto_map[uid]
            dto.order = i
            dto.updated_at = datetime.now()
            reordered_dtos.append(dto)

    return reordered_dtos


def sort_milestones_by_priority(milestones: list[Milestone]) -> list[Milestone]:
    """
    Sort milestones by priority score (highest first).

    Args:
        milestones: List of milestone domain models,

    Returns:
        Sorted list with highest priority first
    """
    return sorted(milestones, key=attrgetter("priority_score"), reverse=True)


def sort_milestones_by_urgency(milestones: list[Milestone]) -> list[Milestone]:
    """
    Sort milestones by urgency (most urgent first).

    Args:
        milestones: List of milestone domain models,

    Returns:
        Sorted list with most urgent first
    """

    def urgency_sort_key(milestone: Milestone) -> tuple:
        """Create sort key for urgency ordering."""
        # Completed milestones go to the end
        if milestone.is_completed:
            return (2, 0)

        # Overdue and critical milestones first
        if milestone.is_critical():
            days = milestone.days_until_target()
            # Negative days (overdue) come first, then by how overdue
            return (0, days if days is not None else 9999)

        # Non-critical milestones by days remaining
        days = milestone.days_until_target()
        return (1, days if days is not None else 9999)

    return sorted(milestones, key=urgency_sort_key)


def group_milestones_by_goal(milestones: list[Milestone]) -> dict[str, list[Milestone]]:
    """
    Group milestones by their goal UID.

    Args:
        milestones: List of milestone domain models,

    Returns:
        Dictionary mapping goal UIDs to lists of milestones
    """
    groups = {}
    for milestone in milestones:
        goal_uid = milestone.goal_uid
        if goal_uid not in groups:
            groups[goal_uid] = []
        groups[goal_uid].append(milestone)

    return groups


# ============================================================================
# VALIDATION AND ERROR HANDLING
# ============================================================================


def validate_milestone_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and clean milestone data before conversion.

    Uses generic validation helpers from validation_helpers.py.

    Args:
        data: Raw data dictionary,

    Returns:
        Cleaned and validated data

    Raises:
        ValueError: If data is invalid
    """
    from core.utils.validation_helpers import (
        parse_date_fields,
        parse_datetime_fields,
        validate_required_fields,
    )

    # Validate required fields
    validate_required_fields(data, ["goal_uid", "title"])

    # Validate order (non-negative integer)
    if "order" in data and data["order"] is not None:
        order = data["order"]
        if not isinstance(order, int) or order < 0:
            raise ValueError("Order must be a non-negative integer")

    # Parse date and datetime fields
    parse_date_fields(data, ["target_date"])
    parse_datetime_fields(data, ["completed_date", "created_at", "updated_at"])

    return data


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def enrich_milestone_dto_with_metadata(dto: MilestoneDTO, metadata: dict[str, Any]) -> MilestoneDTO:
    """
    Add metadata to a milestone DTO.

    Args:
        dto: Milestone DTO to enrich,
        metadata: Additional metadata to add

    Returns:
        DTO with enriched metadata
    """
    dto.metadata.update(metadata)
    dto.updated_at = datetime.now()
    return dto


def extract_milestone_summary(milestone: Milestone) -> dict[str, Any]:
    """
    Extract a summary of milestone for analytics.

    Args:
        milestone: Domain model,

    Returns:
        Summary dictionary with key metrics
    """
    return {
        "uid": milestone.uid,
        "goal_uid": milestone.goal_uid,
        "title": milestone.title,
        "is_completed": milestone.is_completed,
        "is_overdue": milestone.is_overdue(),
        "urgency_level": milestone.urgency_level(),
        "priority_score": milestone.priority_score(),
        "progress_score": milestone.progress_score(),
        "days_until_target": milestone.days_until_target(),
        "time_performance": milestone.time_performance(),
        "order": milestone.order,
        "target_date": milestone.target_date.isoformat() if milestone.target_date else None,
        "completed_date": milestone.completed_date.isoformat()
        if milestone.completed_date
        else None,
    }


def calculate_goal_milestone_progress(milestones: list[Milestone]) -> dict[str, Any]:
    """
    Calculate aggregate progress for milestones belonging to a goal.

    Args:
        milestones: List of milestone domain models for a specific goal,

    Returns:
        Progress summary dictionary
    """
    if not milestones:
        return {
            "total_milestones": 0,
            "completed_milestones": 0,
            "completion_percentage": 0.0,
            "overdue_milestones": 0,
            "next_milestone": None,
            "average_progress_score": 0.0,
        }

    total = len(milestones)
    completed = sum(1 for m in milestones if m.is_completed)
    overdue = sum(1 for m in milestones if m.is_overdue())

    # Find next milestone (highest priority incomplete)
    incomplete_milestones = [m for m in milestones if not m.is_completed]
    next_milestone = None
    if incomplete_milestones:
        sorted_incomplete = sort_milestones_by_priority(incomplete_milestones)
        next_milestone = sorted_incomplete[0].uid

    # Calculate average progress score
    progress_scores = [m.progress_score() for m in milestones]
    avg_score = sum(progress_scores) / len(progress_scores) if progress_scores else 0.0

    return {
        "total_milestones": total,
        "completed_milestones": completed,
        "completion_percentage": (completed / total) * 100 if total > 0 else 0.0,
        "overdue_milestones": overdue,
        "next_milestone": next_milestone,
        "average_progress_score": avg_score,
    }
