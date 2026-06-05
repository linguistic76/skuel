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
from .goal_update_intent import GoalUpdateIntent

__all__ = [
    "GoalAnalyticsRequest",
    "GoalCreateRequest",
    "GoalFilterRequest",
    "GoalProgressUpdateRequest",
    "GoalUpdateIntent",
    "GoalUpdateRequest",
    "HabitEssentialityChangeRequest",
    "HabitSystemUpdateRequest",
    "IdentityBasedGoalRequest",
    "MilestoneCompleteRequest",
    "MilestoneCreateRequest",
    "SystemHealthCheckRequest",
]
