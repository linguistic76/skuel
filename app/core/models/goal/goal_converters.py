"""
Goal Converters
===============

Conversion functions between the three tiers of goal models:
- External (Pydantic) ↔ Transfer (DTO) ↔ Core (Domain)

Follows the pattern established by task_converters.py.
"""

from typing import Any

from .goal import Goal
from .goal_dto import GoalDTO
from .goal_request import GoalCreateRequest

# ============================================================================
# EXTERNAL → TRANSFER (Request → DTO)
# ============================================================================


def goal_create_request_to_dto(request: GoalCreateRequest, user_uid: str) -> GoalDTO:
    """
    Convert GoalCreateRequest to GoalDTO.

    Args:
        request: Validated external request
        user_uid: User UID (from authentication context)

    Returns:
        DTO ready for service operations
    """
    return GoalDTO.create(
        user_uid=user_uid,
        title=request.title,
        description=request.description,
        vision_statement=request.vision_statement,
        goal_type=request.goal_type,
        domain=request.domain,
        timeframe=request.timeframe,
        measurement_type=request.measurement_type,
        target_value=request.target_value,
        unit_of_measurement=request.unit_of_measurement,
        start_date=request.start_date,
        target_date=request.target_date,
        parent_goal_uid=request.parent_goal_uid,
        inspired_by_choice_uid=request.inspired_by_choice_uid,
        why_important=request.why_important,
        success_criteria=request.success_criteria,
        potential_obstacles=request.potential_obstacles or [],
        strategies=request.strategies or [],
        priority=request.priority,
        tags=request.tags or [],
    )


def goal_create_request_to_domain(request: GoalCreateRequest, user_uid: str) -> Goal:
    """
    Direct conversion from create request to domain model.
    Useful for operations that don't need intermediate DTO manipulation.

    Args:
        request: Validated external request
        user_uid: User UID (from authentication context)

    Returns:
        Immutable domain model
    """
    dto = goal_create_request_to_dto(request, user_uid)
    return Goal.from_dto(dto)


# ============================================================================
# DATABASE OPERATIONS (Dict → DTO)
# ============================================================================


def goal_dict_to_dto(data: dict[str, Any]) -> GoalDTO:
    """
    Convert dictionary (from database) to GoalDTO.

    Args:
        data: Raw dictionary from database/Neo4j

    Returns:
        DTO with parsed and validated data
    """
    return GoalDTO.from_dict(data)
