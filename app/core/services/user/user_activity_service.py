"""
User Activity Service - Activity Tracking
==========================================

Focused service handling user activity tracking and context invalidation.

Responsibilities:
- Conversation history management
- Context invalidation for event-driven architecture
- Active learner queries

This service is part of the refactored UserService architecture:
- UserCoreService: CRUD + Auth
- UserProgressService: Learning progress tracking
- UserActivityService: Activity tracking (THIS FILE)
- UserContextBuilder: Context building
- UserStatsAggregator: Stats aggregation
- UserService: Facade coordinating all sub-services
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.user.unified_user_context import RichUserContext

from core.models.type_hints import UserUID
from core.models.user import User
from core.ports.infrastructure_protocols import UserActivityOperations
from core.services.user.debounced_invalidator import DebouncedContextInvalidator
from core.services.user.user_context_cache import UserContextCache
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


# =============================================================================
# INVALIDATION CONSTANTS
# =============================================================================


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
    PREFERENCES_UPDATED = "preferences_updated"
    DISPLAY_NAME_UPDATED = "display_name_updated"
    MANUAL = "manual"
    CACHE_EXPIRED = "cache_expired"


class UserActivityService:
    """
    User activity tracking and context management.

    This service manages a user's conversation history and context state:
    - Managing conversation history
    - Invalidating cached contexts when data changes
    - Querying active learners

    Architecture:
    - Protocol-based repository dependency (UserOperations)
    - Integrates with event-driven context invalidation
    - Performance monitoring for context operations
    """

    def __init__(
        self,
        user_repo: UserActivityOperations,
        metrics_cache=None,
        invalidation_delay_ms: int = 100,
    ) -> None:
        """
        Initialize user activity service.

        Args:
            user_repo: Repository implementation for user persistence (protocol-based)
            metrics_cache: MetricsCache for performance tracking (optional)
            invalidation_delay_ms: Debounce delay for context invalidation (default 100ms).
                                   Set to 0 to disable debouncing.

        Raises:
            ValueError: If user_repo is None
        """
        if not user_repo:
            raise ValueError("User repository is required")
        self.repo = user_repo
        self._metrics_cache = metrics_cache
        self._context_cache = UserContextCache()  # Event-driven cache invalidation

        # Debounced invalidation to collapse rapid event bursts (O(n) → O(1))
        self._invalidator = DebouncedContextInvalidator(
            invalidate_fn=self._do_invalidate,
            delay_ms=invalidation_delay_ms,
        )

    # ========================================================================
    # CONVERSATION HISTORY
    # ========================================================================

    @with_error_handling("add_conversation_message", error_type="database", uid_param="user_uid")
    async def add_conversation_message(
        self, user_uid: UserUID, role: str, content: str, metadata: dict | None = None
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

    async def invalidate_context(  # skuel-lint: disable=SKUEL005 -- fire-and-forget cache invalidation from event handlers
        self,
        user_uid: UserUID,
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
            self._invalidator.invalidate(user_uid, reason, affected_contexts)

    async def _do_invalidate(  # skuel-lint: disable=SKUEL029 -- DebouncedContextInvalidator callback: typed Coroutine and awaited at debounced_invalidator.py:139
        self, user_uid: UserUID, reason: str, affected_contexts: list[str] | None = None
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
            self._metrics_cache.record_context_invalidation(
                user_uid=user_uid,
                duration_ms=duration_ms,
                reason=reason,
                affected_contexts=affected_contexts
                or ["askesis", "search", "recommendations", "dashboard"],
            )

    def get_valid_context(self, user_uid: UserUID) -> RichUserContext | None:
        """
        Get cached rich user context if still valid (not invalidated).

        Semantic: "get valid context" - returns context only if it hasn't been
        invalidated by domain events. Returns None for stale/invalidated contexts.

        Only rich contexts are cached (see ``UserContextCache`` docstring).

        Args:
            user_uid: User's unique identifier

        Returns:
            RichUserContext if valid and not invalidated, None otherwise
        """
        return self._context_cache.get(user_uid)

    def cache_context(self, user_uid: UserUID, context: RichUserContext) -> None:
        """
        Cache a freshly-built rich user context.

        Semantic: "cache context" - stores a fresh context that will be served
        until domain events trigger invalidation. Only rich contexts are cached.

        Args:
            user_uid: User's unique identifier
            context: RichUserContext to cache
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
