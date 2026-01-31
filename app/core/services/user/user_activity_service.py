"""
User Activity Service - Activity Tracking
==========================================

Focused service handling user activity tracking and context invalidation.

Responsibilities:
- Activity state updates (knowledge views, task starts, habit practices)
- Conversation history management
- Context invalidation for event-driven architecture
- Active learner queries
- Activity update building

This service is part of the refactored UserService architecture:
- UserCoreService: CRUD + Auth
- UserProgressService: Learning progress tracking
- UserActivityService: Activity tracking (THIS FILE)
- UserContextBuilder: Context building
- UserStatsAggregator: Stats aggregation
- UserService: Facade coordinating all sub-services
"""

from typing import Any

from core.events import publish_event
from core.models.shared_enums import EntityType
from core.models.user import User
from core.services.protocols.infrastructure_protocols import UserOperations
from core.services.user.debounced_invalidator import DebouncedContextInvalidator
from core.services.user.user_context_cache import UserContextCache
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


# =============================================================================
# ACTIVITY & INVALIDATION CONSTANTS
# =============================================================================

# Pure mapping: (activity_type, action) -> User model field
# Makes valid combinations explicit and self-documenting
ACTIVITY_FIELD_MAP: dict[tuple[str, str], str] = {
    (EntityType.KNOWLEDGE.value, "viewed"): "recently_viewed_knowledge",
    (EntityType.KNOWLEDGE.value, "bookmarked"): "bookmarked_knowledge",
    (EntityType.TASK.value, "started"): "current_tasks",
    (EntityType.TASK.value, "completed"): "recently_completed_tasks",
    (EntityType.HABIT.value, "practiced"): "recently_practiced_habits",
}


class InvalidationReason:
    """
    Normalized reasons for context invalidation.

    Use these constants instead of free-form strings for:
    - Consistent analytics and monitoring
    - Easier grouping of invalidation patterns
    - Better dashboard filtering
    """

    ACTIVITY = "activity"
    TASK_COMPLETED = "task_completed"
    TASK_STARTED = "task_started"
    GOAL_ACHIEVED = "goal_achieved"
    GOAL_PROGRESS = "goal_progress"
    HABIT_PRACTICED = "habit_practiced"
    KNOWLEDGE_MASTERED = "knowledge_mastered"
    KNOWLEDGE_VIEWED = "knowledge_viewed"
    MANUAL = "manual"
    CACHE_EXPIRED = "cache_expired"


class UserActivityService:
    """
    User activity tracking and context management.

    This service handles tracking user activities and managing context state:
    - Recording user activity (views, completions, etc.)
    - Managing conversation history
    - Invalidating cached contexts when data changes
    - Querying active learners
    - Building activity update payloads

    Architecture:
    - Protocol-based repository dependency (UserOperations)
    - Returns Result[T] for error handling
    - Integrates with event-driven context invalidation
    - Performance monitoring for context operations


    Source Tag: "user_activity_explicit"
    - Format: "user_activity_explicit" for user-created relationships
    - Format: "user_activity_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    """

    def __init__(
        self,
        user_repo: UserOperations,
        event_bus=None,
        metrics_cache=None,
        invalidation_delay_ms: int = 100,
    ) -> None:
        """
        Initialize user activity service.

        Args:
            user_repo: Repository implementation for user persistence (protocol-based)
            event_bus: Event bus for publishing domain events (optional)
            metrics_cache: MetricsCache for performance tracking (optional)
            invalidation_delay_ms: Debounce delay for context invalidation (default 100ms).
                                   Set to 0 to disable debouncing.

        Raises:
            ValueError: If user_repo is None
        """
        if not user_repo:
            raise ValueError("User repository is required")
        self.repo = user_repo
        self.event_bus = event_bus
        self._metrics_cache = metrics_cache
        self._context_cache = UserContextCache()  # Event-driven cache invalidation

        # Debounced invalidation to collapse rapid event bursts (O(n) → O(1))
        self._invalidator = DebouncedContextInvalidator(
            invalidate_fn=self._do_invalidate,
            delay_ms=invalidation_delay_ms,
        )

    # ========================================================================
    # ACTIVITY TRACKING
    # ========================================================================

    @with_error_handling("update_user_activity", error_type="database", uid_param="user_uid")
    async def update_user_activity(
        self, user_uid: str, activity_type: str, entity_uid: str, action: str = "viewed"
    ) -> Result[bool]:
        """
        Update user's activity state.

        Records user interactions with domain entities (knowledge, tasks, habits).
        Updates activity lists like recently_viewed_knowledge, current_tasks, etc.

        Args:
            user_uid: User's unique identifier
            activity_type: Type of activity (knowledge, task, habit, etc.)
            entity_uid: UID of the entity
            action: Action performed (viewed, completed, started, bookmarked, etc.)

        Returns:
            Result[bool]: True if updated successfully

        Error cases:
            - Invalid activity/action pair → VALIDATION
            - Database operation fails → DATABASE

        Valid Activity/Action Pairs (see ACTIVITY_FIELD_MAP):
            - knowledge: viewed, bookmarked
            - task: started, completed
            - habit: practiced

        Eventual Consistency:
            Event publishing is fire-and-forget. If publish_event fails,
            the activity update has already succeeded. This is intentional -
            activity state is source of truth, events are notifications.
        """
        # Validate activity/action pair upfront (fail-fast)
        if (activity_type, action) not in ACTIVITY_FIELD_MAP:
            return Result.fail(
                Errors.validation(
                    message=f"Invalid activity/action pair: {activity_type}.{action}",
                    field="activity_type",
                )
            )

        # Build activity update (guaranteed non-empty due to validation above)
        activity_updates = self._build_activity_update(activity_type, entity_uid, action)

        result = await self.repo.update_user_activity(user_uid, activity_updates)

        if result.is_ok:
            logger.debug(
                f"Updated activity for user {user_uid}: {activity_type}.{action} -> {entity_uid}"
            )

            # Publish UserActivityRecorded event (eventual consistency - do NOT rollback on failure)
            # Activity update is source of truth; events are notifications
            try:
                from datetime import datetime

                from core.events import UserActivityRecorded

                event = UserActivityRecorded(
                    user_uid=user_uid,
                    occurred_at=datetime.now(),
                    activity_type=f"{activity_type}.{action}",
                    activity_context={
                        "entity_uid": entity_uid,
                        "activity_type": activity_type,
                        "action": action,
                    },
                )
                await publish_event(self.event_bus, event, logger)
            except Exception as e:
                # Log but do NOT fail - activity update already succeeded
                logger.warning(
                    f"Event publish failed for {activity_type}.{action} (user={user_uid}): {e}"
                )

        return result

    def _build_activity_update(
        self, activity_type: str, entity_uid: str, action: str
    ) -> dict[str, Any]:
        """
        Build activity update dictionary based on type and action.

        Pure function: maps (activity_type, action) to field update via ACTIVITY_FIELD_MAP.
        Total function: always returns a dict (empty if no matching field).

        Args:
            activity_type: Type of activity (knowledge, task, habit)
            entity_uid: UID of the entity
            action: Action performed

        Returns:
            Dictionary of field updates (empty dict if invalid activity/action pair)

        Valid Combinations (see ACTIVITY_FIELD_MAP):
            - knowledge.viewed → recently_viewed_knowledge
            - knowledge.bookmarked → bookmarked_knowledge
            - task.started → current_tasks
            - task.completed → recently_completed_tasks
            - habit.practiced → recently_practiced_habits
        """
        field = ACTIVITY_FIELD_MAP.get((activity_type, action))
        return {field: [entity_uid]} if field else {}

    # ========================================================================
    # CONVERSATION HISTORY
    # ========================================================================

    @with_error_handling("add_conversation_message", error_type="database", uid_param="user_uid")
    async def add_conversation_message(
        self, user_uid: str, role: str, content: str, metadata: dict | None = None
    ) -> Result[bool]:
        """
        Add message to user's conversation history.

        Stores conversation messages for AI assistant interactions (Askesis).

        Args:
            user_uid: User's unique identifier
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional message metadata (timestamps, tokens, etc.)

        Returns:
            Result[bool]: True if added successfully

        Error cases:
            - Database operation fails → DATABASE

        Note:
            - Used primarily by Askesis AI service
            - Maintains conversation context across sessions
            - Metadata can include tokens used, model version, etc.

        IMPORTANT - History Size Policy:
            Conversation history grows unbounded in this service. The repository
            layer MUST enforce limits to prevent unbounded growth:
            - Max messages per user (recommended: 200)
            - Max age (recommended: prune messages >30 days)
            See UserRepository.add_conversation_message for enforcement.
        """
        result = await self.repo.add_conversation_message(user_uid, role, content, metadata)

        if result.is_ok:
            logger.debug(f"Added conversation message for user {user_uid}: {role}")

        return result

    # ========================================================================
    # CONTEXT INVALIDATION (Event-Driven Architecture)
    # ========================================================================

    async def invalidate_context(
        self,
        user_uid: str,
        reason: str = InvalidationReason.MANUAL,
        affected_contexts: list[str] | None = None,
        *,
        immediate: bool = False,
    ) -> None:
        """
        Invalidate cached user context when domain events occur.

        This method is called by event handlers when tasks, goals, or habits
        change. By default, multiple rapid calls are debounced to reduce redundant
        invalidations.

        Example: Completing a task triggers TaskCompleted, GoalProgressUpdated,
        and KnowledgeApplied events - all three are collapsed into one invalidation.

        Args:
            user_uid: User's unique identifier
            reason: Why context was invalidated. Use InvalidationReason constants
                    for consistent analytics (e.g., InvalidationReason.TASK_COMPLETED)
            affected_contexts: Which contexts are affected (default: all)
            immediate: If True, bypass debouncing and invalidate immediately.
                       Use for POST→GET flows where correctness trumps performance.

        Context Types:
            - askesis: AI assistant context
            - search: Search recommendations context
            - recommendations: Learning recommendations
            - dashboard: Profile hub dashboard data

        Performance:
            - Debounced (default): Collapses 5-10 invalidations per user action to 1
            - Immediate: Forces synchronous invalidation (use sparingly)
        """
        if immediate:
            await self._do_invalidate(user_uid, reason, affected_contexts)
        else:
            await self._invalidator.invalidate(user_uid, reason, affected_contexts)

    async def _do_invalidate(
        self, user_uid: str, reason: str, affected_contexts: list[str] | None = None
    ) -> None:
        """
        Execute actual context invalidation (called by debouncer).

        This is the internal method that performs the real work.
        External callers should use invalidate_context() instead.
        """
        import time

        start_time = time.perf_counter()

        logger.debug(f"Executing context invalidation for user {user_uid} (reason: {reason})")

        # Invalidate the context cache (event-driven cache invalidation)
        self._context_cache.invalidate(user_uid)

        # Track invalidation performance (if metrics cache is available)
        if self._metrics_cache:
            duration_ms = (time.perf_counter() - start_time) * 1000
            await self._metrics_cache.record_context_invalidation(
                user_uid=user_uid,
                duration_ms=duration_ms,
                reason=reason,
                affected_contexts=affected_contexts
                or ["askesis", "search", "recommendations", "dashboard"],
            )

    async def flush_pending_invalidations(self, user_uid: str | None = None) -> Result[None]:
        """
        Immediately execute any pending debounced invalidations.

        Useful for testing or when you need to ensure invalidation completes
        before proceeding (e.g., before returning from an API call).

        Args:
            user_uid: If provided, only flush for this user.
                      If None, flush all pending invalidations.

        Returns:
            Result[None] indicating success.
        """
        return await self._invalidator.flush(user_uid)

    def get_invalidation_stats(self) -> dict[str, Any]:
        """
        Get debouncing statistics for monitoring.

        Returns:
            Dict with requests_received, requests_debounced, invalidations_executed,
            efficiency ratio, and pending count.
        """
        stats = self._invalidator.get_stats()
        stats["efficiency"] = self._invalidator.get_efficiency()
        stats["pending_count"] = self._invalidator.get_pending_count()
        return stats

    def get_valid_context(self, user_uid: str):
        """
        Get cached user context if still valid (not invalidated).

        Semantic: "get valid context" - returns context only if it hasn't been
        invalidated by domain events. Returns None for stale/invalidated contexts.

        Args:
            user_uid: User's unique identifier

        Returns:
            UserContext if valid and not invalidated, None otherwise
        """
        return self._context_cache.get(user_uid)

    def cache_context(self, user_uid: str, context) -> None:
        """
        Cache a freshly-built user context.

        Semantic: "cache context" - stores a fresh context that will be served
        until domain events trigger invalidation.

        Args:
            user_uid: User's unique identifier
            context: UserContext to cache
        """
        self._context_cache.set(user_uid, context)

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return self._context_cache.get_cache_stats()

    # ========================================================================
    # UTILITY QUERIES
    # ========================================================================

    @with_error_handling("get_active_learners", error_type="database")
    async def get_active_learners(
        self, since_hours: int = 24, limit: int = 100
    ) -> Result[list[User]]:
        """
        Get users who have been active recently.

        Queries for users based on last_active_at timestamp.
        Useful for engagement tracking and notifications.

        Args:
            since_hours: Hours since last activity (default: 24)
            limit: Maximum number of users to return (default: 100)

        Returns:
            Result[List[User]]: List of active users

        Error cases:
            - Database query fails → DATABASE

        Use Cases:
            - Daily engagement reports
            - Active user statistics
            - Notification targeting
            - Usage analytics
        """
        return await self.repo.get_active_learners(since_hours, limit)
