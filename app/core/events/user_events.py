"""
User Context Domain Events
===========================

Events published by UserService for user context and preference changes.

Event Catalog:
- user.context_invalidated - User context needs refresh
- user.preferences_changed - User preferences updated

Subscribers:
- AskesisService (refresh AI context)
- SearchService (refresh search personalization)
- RecommendationEngine (refresh recommendations)
"""

from dataclasses import dataclass
from datetime import datetime

from core.events.base import BaseEvent

# ============================================================================
# USER CONTEXT EVENTS
# ============================================================================


@dataclass(frozen=True)
class UserContextInvalidated(BaseEvent):
    """
    Published when user context needs to be refreshed.

    This event is triggered by state-changing operations in other domains:
    - Task completed/created/deleted
    - Goal achieved/updated
    - Habit completed
    - Learning progress updated

    Subscribers:
    - AskesisService (refresh AI context for personalized responses)
    - SearchService (refresh search personalization)
    - RecommendationEngine (refresh recommendation models)
    - DashboardService (refresh user dashboard)
    """

    user_uid: str
    occurred_at: datetime

    # What triggered the invalidation
    reason: str  # "task_completed", "goal_achieved", "habit_completed", etc.

    # Which contexts should be invalidated
    affected_contexts: list[str]  # ["askesis", "search", "recommendations", "dashboard"]

    # Optional: source entity that triggered invalidation
    source_entity_uid: str | None = None
    source_entity_type: str | None = None  # "task", "goal", "habit"

    @property
    def event_type(self) -> str:
        return "user.context_invalidated"


@dataclass(frozen=True)
class UserPreferencesChanged(BaseEvent):
    """
    Published when user preferences are updated.

    Subscribers:
    - PersonalizationEngine (adjust personalization)
    - NotificationService (update notification preferences)
    - UIService (update UI preferences)
    """

    user_uid: str
    occurred_at: datetime

    # Which preference fields changed
    changed_fields: list[str]

    # Optional: old/new values for important preferences
    notification_preferences_changed: bool = False
    theme_preferences_changed: bool = False
    privacy_preferences_changed: bool = False

    @property
    def event_type(self) -> str:
        return "user.preferences_changed"


# ============================================================================
# USER ACTIVITY EVENTS
# ============================================================================


@dataclass(frozen=True)
class UserActivityRecorded(BaseEvent):
    """
    Published when user activity is logged (optional analytics event).

    Subscribers:
    - AnalyticsEngine (user behavior patterns)
    - RecommendationEngine (activity-based recommendations)
    """

    user_uid: str
    occurred_at: datetime

    # Activity details
    activity_type: str  # "viewed_page", "completed_action", "searched", etc.
    activity_context: dict[str, str] | None = None

    @property
    def event_type(self) -> str:
        return "user.activity_recorded"


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
Publishing User Events:
=======================

# In UserService.invalidate_context()
async def invalidate_context(
    self,
    user_uid: str,
    reason: str = "manual",
    affected_contexts: list[str] | None = None
) -> None:
    '''Invalidate user context and publish event.'''

    # Clear cache
    await self._clear_context_cache(user_uid)

    # Publish event
    if self.event_bus:
        event = UserContextInvalidated(
            user_uid=user_uid,
            occurred_at=datetime.now(),
            reason=reason,
            affected_contexts=affected_contexts or ["askesis", "search", "recommendations"]
        )
        await self.event_bus.publish_async(event)
        self.logger.info(f"Context invalidated for user {user_uid}: {reason}")


# In UserService.update_preferences()
async def update_preferences(
    self,
    user_uid: str,
    updates: dict[str, Any]
) -> Result[User]:
    '''Update user preferences.'''

    result = await self.backend.update(user_uid, updates)

    if result.is_ok and self.event_bus:
        changed_fields = list(updates.keys())

        event = UserPreferencesChanged(
            user_uid=user_uid,
            occurred_at=datetime.now(),
            changed_fields=changed_fields,
            notification_preferences_changed="notification_preferences" in changed_fields,
            theme_preferences_changed="theme" in changed_fields,
            privacy_preferences_changed="privacy_settings" in changed_fields
        )
        await self.event_bus.publish_async(event)

    return result


Event Handlers (Subscribers):
=============================

# In TasksService - Publishing context invalidation
async def complete_task(self, uid: str) -> Result[Task]:
    result = await self.backend.complete(uid)

    if result.is_ok and self.event_bus:
        task = result.value

        # Publish TaskCompleted event
        task_event = TaskCompleted(
            task_uid=task.uid,
            user_uid=task.user_uid,
            occurred_at=datetime.now()
        )
        await self.event_bus.publish_async(task_event)

    return result


# In UserService - Subscribing to task events
async def handle_task_completed(self, event: TaskCompleted) -> None:
    '''Handle task completion by invalidating context.'''
    await self.invalidate_context(
        user_uid=event.user_uid,
        reason="task_completed",
        affected_contexts=["askesis", "search", "recommendations"]
    )


# In AskesisService - Handling context invalidation
async def handle_context_invalidated(self, event: UserContextInvalidated) -> None:
    '''Refresh AI context when user context invalidated.'''

    if "askesis" in event.affected_contexts:
        # Clear cached context
        await self._clear_cached_context(event.user_uid)

        self.logger.info(
            f"Askesis context refreshed for user {event.user_uid} "
            f"(reason: {event.reason})"
        )


# In SearchService - Handling context invalidation
async def handle_context_invalidated(self, event: UserContextInvalidated) -> None:
    '''Refresh search personalization when context invalidated.'''

    if "search" in event.affected_contexts:
        # Rebuild search index for user
        await self._rebuild_user_search_index(event.user_uid)

        self.logger.info(
            f"Search index refreshed for user {event.user_uid} "
            f"(reason: {event.reason})"
        )


# In RecommendationEngine - Handling context invalidation
async def handle_context_invalidated(self, event: UserContextInvalidated) -> None:
    '''Refresh recommendations when context invalidated.'''

    if "recommendations" in event.affected_contexts:
        # Clear recommendation cache
        await self._clear_recommendation_cache(event.user_uid)

        # Optionally: Pre-compute new recommendations
        # await self._precompute_recommendations(event.user_uid)

        self.logger.info(
            f"Recommendations refreshed for user {event.user_uid} "
            f"(reason: {event.reason})"
        )


# In NotificationService - Handling preference changes
async def handle_preferences_changed(self, event: UserPreferencesChanged) -> None:
    '''Update notification settings when preferences change.'''

    if event.notification_preferences_changed:
        # Reload notification preferences
        await self._reload_notification_preferences(event.user_uid)

        self.logger.info(
            f"Notification preferences reloaded for user {event.user_uid}"
        )


Bootstrap Wiring:
================

# In services_bootstrap.py
def _wire_event_subscribers(event_bus: EventBusOperations, services: Services):
    '''Wire all event subscribers.'''

    # User context invalidation on task events
    event_bus.subscribe(TaskCompleted, services.user_service.handle_task_completed)
    event_bus.subscribe(TaskCreated, services.user_service.handle_task_created)
    event_bus.subscribe(TaskDeleted, services.user_service.handle_task_deleted)

    # User context invalidation on goal events
    event_bus.subscribe(GoalAchieved, services.user_service.handle_goal_achieved)
    event_bus.subscribe(GoalProgressUpdated, services.user_service.handle_goal_updated)

    # User context invalidation on habit events
    event_bus.subscribe(HabitCompleted, services.user_service.handle_habit_completed)

    # Context refresh on invalidation
    event_bus.subscribe(UserContextInvalidated, services.askesis.handle_context_invalidated)
    event_bus.subscribe(UserContextInvalidated, services.search.handle_context_invalidated)
    event_bus.subscribe(UserContextInvalidated, services.recommendations.handle_context_invalidated)

    # Preference updates
    event_bus.subscribe(UserPreferencesChanged, services.notifications.handle_preferences_changed)

    logger.info("✅ User event subscribers wired")


Pattern: Automatic Context Invalidation
========================================

# Before (Direct dependency):
class TasksService:
    def __init__(self, backend, context_service):  # ← Direct dependency
        self.context_service = context_service

    async def complete_task(self, uid: str):
        result = await self.backend.complete(uid)
        if result.is_ok and self.context_service:
            await self.context_service.invalidate_context(...)  # ← Direct call
        return result


# After (Event-driven):
class TasksService:
    def __init__(self, backend, event_bus):  # ← Infrastructure only
        self.event_bus = event_bus

    async def complete_task(self, uid: str):
        result = await self.backend.complete(uid)
        if result.is_ok and self.event_bus:
            # Publish event - UserService handles invalidation
            await self.event_bus.publish_async(TaskCompleted(...))
        return result

class UserService:
    async def handle_task_completed(self, event: TaskCompleted):
        # UserService subscribes and handles context invalidation
        await self.invalidate_context(event.user_uid, reason="task_completed")
"""
