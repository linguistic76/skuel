"""
Goal Domain Events
==================

Events published by GoalsService for goal lifecycle operations.

Event Catalog:
- goal.created - Goal created
- goal.achieved - Goal achieved/completed
- goal.progress_updated - Goal progress percentage changed
- goal.abandoned - Goal abandoned/cancelled
- goal.recommendations_generated - Goal recommendations generated (after achievement)

Subscribers:
- UserService (context invalidation)
- AnalyticsEngine (goal success patterns)
- NotificationService (achievements, reminders)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID

# ============================================================================
# GOAL LIFECYCLE EVENTS
# ============================================================================


@dataclass(frozen=True)
class GoalCreated(BaseEvent):
    """
    Published when a goal is created.

    Subscribers:
    - Analytics (track goal creation patterns)
    - UserService (invalidate context)
    - RecommendationEngine (suggest related goals)
    """

    goal_uid: str
    user_uid: UserUID
    title: str
    domain: str | None
    target_date: datetime | None

    # Goal type context
    is_milestone: bool = False
    parent_goal_uid: str | None = None

    event_type: ClassVar[str] = "goal.created"


@dataclass(frozen=True)
class GoalUpdated(BaseEvent):
    """
    Published when goal node properties change (ADR-066 typed update path).

    Fired on every ``update_goal`` so user-context caches invalidate even for plain
    property edits (title, description, target_date) that have no more specific event.
    Progress-percentage and achievement changes additionally fire ``GoalProgressUpdated``
    / ``GoalAchieved``.

    Subscribers:
    - UserService (invalidate context)
    - Analytics (track update patterns)
    """

    goal_uid: str
    user_uid: UserUID
    updated_fields: list[str]

    event_type: ClassVar[str] = "goal.updated"


@dataclass(frozen=True)
class GoalAchieved(BaseEvent):
    """
    Published when a goal is marked as achieved.

    This is a HIGH-PRIORITY event triggering celebrations and analytics.

    Subscribers:
    - UserService (invalidate context)
    - AnalyticsEngine (goal success analysis)
    - AchievementService (badges, celebrations)
    - NotificationService (achievement notification)
    """

    goal_uid: str
    user_uid: UserUID

    # Performance metrics
    actual_duration_days: int | None = None
    planned_duration_days: int | None = None
    completed_ahead_of_schedule: bool = False

    # Related entities
    related_task_count: int = 0
    related_habit_count: int = 0

    event_type: ClassVar[str] = "goal.achieved"


@dataclass(frozen=True)
class GoalProgressUpdated(BaseEvent):
    """
    Published when goal progress percentage changes.

    Subscribers:
    - UserService (invalidate context if significant change)
    - Analytics (track progress velocity)
    - DashboardService (real-time progress updates)
    """

    goal_uid: str
    user_uid: UserUID
    old_progress: float  # 0.0 to 1.0
    new_progress: float  # 0.0 to 1.0

    # Context for what caused the progress update
    triggered_by_task_completion: bool = False
    triggered_by_habit_completion: bool = False
    triggered_by_manual_update: bool = False

    event_type: ClassVar[str] = "goal.progress_updated"

    @property
    def progress_delta(self) -> float:
        """Calculate progress change."""
        return self.new_progress - self.old_progress

    @property
    def is_significant_change(self) -> bool:
        """Is this a significant progress change (>10%)?"""
        return abs(self.progress_delta) >= 0.1


@dataclass(frozen=True)
class GoalAbandoned(BaseEvent):
    """
    Published when a goal is abandoned or cancelled.

    Subscribers:
    - UserService (invalidate context)
    - Analytics (understand abandonment patterns)
    - RecommendationEngine (avoid similar goals)
    """

    goal_uid: str
    user_uid: UserUID

    # Context for abandonment
    reason: str | None = None  # "no_longer_relevant", "too_difficult", "changed_priorities"
    progress_at_abandonment: float = 0.0
    days_active: int = 0

    event_type: ClassVar[str] = "goal.abandoned"


# ============================================================================
# GOAL RECOMMENDATION EVENTS
# ============================================================================


@dataclass(frozen=True)
class GoalRecommendationsGenerated(BaseEvent):
    """
    Published when goal recommendations are generated (typically after goal achievement).

    Subscribers:
    - NotificationService (show recommendations to user)
    - Analytics (track recommendation patterns)
    - UIService (display recommendations in goal completion flow)
    """

    goal_uid: str
    user_uid: UserUID

    # Recommendation data
    recommendations: list[
        dict
    ]  # List of recommendation dicts with title, description, rationale, confidence
    triggered_by_achievement: bool = False

    event_type: ClassVar[str] = "goal.recommendations_generated"

    @property
    def recommendation_count(self) -> int:
        """Number of recommendations generated."""
        return len(self.recommendations)


# ============================================================================
# GOAL MILESTONE EVENTS
# ============================================================================


@dataclass(frozen=True)
class GoalMilestoneReached(BaseEvent):
    """
    Published when a goal reaches a significant milestone.

    Subscribers:
    - NotificationService (milestone celebration)
    - Analytics (milestone achievement patterns)
    """

    goal_uid: str
    user_uid: UserUID
    milestone_percentage: float  # e.g., 0.25, 0.5, 0.75

    event_type: ClassVar[str] = "goal.milestone_reached"


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
Publishing Goal Events:
=======================

# In GoalsService.create()
async def create_goal(self, goal: Goal) -> Result[Goal]:
    result = await self.backend.create(goal)

    if result.is_ok and self.event_bus:
        event = GoalCreated(
            goal_uid=goal.uid,
            user_uid=goal.user_uid,
            title=goal.title,
            domain=goal.domain.value if goal.domain else None,
            target_date=goal.target_date,
        )
        await self.event_bus.publish_async(event)

    return result


# In GoalsCoreService.update_goal() — GoalAchieved fires on the status
# transition into COMPLETED (the ADR-066 typed update path is THE publisher)
async def update_goal(self, uid: str, intent: GoalUpdateIntent) -> Result[Goal]:
    result = await super().update(uid, intent)

    if result.is_ok and status_transitioned_to_completed:
        goal = result.value
        actual_days = (datetime.now() - goal.created_at).days if goal.created_at else None

        event = GoalAchieved(
            goal_uid=goal.uid,
            user_uid=goal.user_uid,
            actual_duration_days=actual_days,
        )
        await self.event_bus.publish_async(event)

    return result


# In GoalsService.update_progress()
async def update_progress(self, uid: str, new_progress: float) -> Result[Goal]:
    # Get current goal to capture old progress
    goal_result = await self.backend.get(uid)
    if goal_result.is_error:
        return goal_result

    old_progress = goal_result.value.progress or 0.0

    # Update progress
    result = await self.backend.update(uid, {"progress": new_progress})

    if result.is_ok and self.event_bus:
        event = GoalProgressUpdated(
            goal_uid=uid,
            user_uid=result.value.user_uid,
            old_progress=old_progress,
            new_progress=new_progress,
            triggered_by_manual_update=True
        )
        await self.event_bus.publish_async(event)

    return result


Subscribing to Goal Events:
===========================

# In UserService
async def handle_goal_achieved(self, event: GoalAchieved) -> None:
    '''Invalidate user context when goal achieved.'''
    await self.invalidate_context(event.user_uid)
    self.logger.info(f"Context invalidated for user {event.user_uid} (goal achieved)")


# In AchievementService
async def handle_goal_achieved(self, event: GoalAchieved) -> None:
    '''Award achievement badge when goal achieved.'''
    if event.completed_ahead_of_schedule:
        await self.award_badge(event.user_uid, "early_achiever")

    if event.actual_duration_days and event.actual_duration_days <= 30:
        await self.award_badge(event.user_uid, "sprint_master")


# In Analytics
async def handle_goal_abandoned(self, event: GoalAbandoned) -> None:
    '''Track goal abandonment patterns.'''
    await self.record_abandonment(
        user_uid=event.user_uid,
        goal_uid=event.goal_uid,
        reason=event.reason,
        progress=event.progress_at_abandonment
    )


# In Bootstrap
event_bus.subscribe(GoalAchieved, user_service.handle_goal_achieved)
event_bus.subscribe(GoalAchieved, achievement_service.handle_goal_achieved)
event_bus.subscribe(GoalProgressUpdated, dashboard_service.handle_progress_updated)
event_bus.subscribe(GoalAbandoned, analytics.handle_goal_abandoned)
"""
