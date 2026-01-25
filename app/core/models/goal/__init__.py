"""
Goal Three-Tier Model Package
==============================

Exports all goal-related models following the three-tier architecture.
Goals provide direction and motivation for learning and behavior change.
"""

from .goal import (
    Goal,
    GoalStatus,
    GoalTimeframe,
    GoalType,
    HabitEssentiality,  # Atomic Habits integration
    MeasurementType,
)
from .goal import Milestone as EmbeddedMilestone  # Milestone embedded in Goal model
from .goal_converters import goal_create_request_to_domain, goal_create_request_to_dto
from .goal_dto import GoalDTO
from .goal_milestone_request import (
    StandaloneMilestoneCompleteRequest,
    StandaloneMilestoneCreateRequest,
    StandaloneMilestoneFilterRequest,
    StandaloneMilestoneUpdateRequest,
)
from .goal_request import (
    GoalAnalyticsRequest,
    GoalCreateRequest,
    GoalFilterRequest,
    GoalProgressUpdateRequest,
    GoalUpdateRequest,
    HabitEssentialityChangeRequest,
    # Atomic Habits request models
    HabitSystemUpdateRequest,
    IdentityBasedGoalRequest,
    MilestoneCompleteRequest,  # For embedded milestones in goals
    MilestoneCreateRequest,  # For embedded milestones in goals
    SystemHealthCheckRequest,
)

# Import three-tier standalone milestone models
from .milestone import Milestone, MilestoneDTO  # Standalone milestone management

__all__ = [
    "EmbeddedMilestone",  # Milestone within Goal model
    # Domain Models
    "Goal",
    "GoalAchievementContext",
    "GoalAnalyticsRequest",
    # Request Models - Goal
    "GoalCreateRequest",
    # DTOs
    "GoalDTO",
    "GoalFilterRequest",
    # Intelligence Models
    "GoalIntelligence",
    "GoalProgressUpdateRequest",
    "GoalStatus",
    "GoalTimeframe",
    # Enums
    "GoalType",
    "GoalUpdateRequest",
    "HabitEssentiality",  # Atomic Habits enum
    "HabitEssentialityChangeRequest",
    # Request Models - Atomic Habits
    "HabitSystemUpdateRequest",
    "IdentityBasedGoalRequest",
    "MeasurementType",
    "Milestone",  # Standalone milestone (three-tier)
    "MilestoneCompleteRequest",
    # Request Models - Embedded Milestones (within goals)
    "MilestoneCreateRequest",
    "MilestoneDTO",  # Standalone milestone DTO
    "MotivationLevel",
    "ObstacleReason",
    "StandaloneMilestoneCompleteRequest",
    # Request Models - Standalone Milestones (three-tier)
    "StandaloneMilestoneCreateRequest",
    "StandaloneMilestoneFilterRequest",
    "StandaloneMilestoneUpdateRequest",
    "SystemHealthCheckRequest",
    "goal_create_request_to_domain",
    # Converters
    "goal_create_request_to_dto",
]

# Intelligence models
from .goal_intelligence import (
    GoalAchievementContext,
    GoalIntelligence,
    MotivationLevel,
    ObstacleReason,
)
