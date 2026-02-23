"""
Goal Request Models Package
============================

After Ku unification, Goal domain models (Goal, GoalDTO) moved to the unified
Ku model. This package now only contains Pydantic request models for goal API
endpoints.

Domain model: core.models.ku.goal.Goal (with ku_type='goal')
DTO: core.models.ku.goal_dto.GoalDTO
Enums: core.models.enums.ku_enums (GoalType, GoalTimeframe, MeasurementType, EntityStatus)
"""

from .goal_request import (
    GoalAnalyticsRequest,
    GoalCreateRequest,
    GoalFilterRequest,
    GoalProgressUpdateRequest,
    GoalUpdateRequest,
    HabitEssentialityChangeRequest,
    HabitSystemUpdateRequest,
    IdentityBasedGoalRequest,
    MilestoneCompleteRequest,
    MilestoneCreateRequest,
    SystemHealthCheckRequest,
)

__all__ = [
    "GoalAnalyticsRequest",
    "GoalCreateRequest",
    "GoalFilterRequest",
    "GoalProgressUpdateRequest",
    "GoalUpdateRequest",
    "HabitEssentialityChangeRequest",
    "HabitSystemUpdateRequest",
    "IdentityBasedGoalRequest",
    "MilestoneCompleteRequest",
    "MilestoneCreateRequest",
    "SystemHealthCheckRequest",
]
