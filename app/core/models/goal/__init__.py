"""
Goal domain models — Goal, GoalDTO, Milestone, requests.
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
