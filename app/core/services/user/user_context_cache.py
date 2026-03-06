"""
User Context Cache - Performance Caching Layer
==============================================

*Status: INTEGRATED (as of 2025-12-07)*
*Caching Policy Updated: 2026-01-06*

This cache provides TTL-based caching with event-driven invalidation for
user context data. When domain events occur (task completed, goal achieved,
habit updated, etc.), the cache is automatically invalidated.

Features:
- TTL-based cache expiration (default 5 minutes)
- Event-driven invalidation via UserActivityService.invalidate_context()
- Automatic cleanup of expired contexts

Integration:
- UserActivityService owns the cache instance
- Domain events (TaskCompleted, GoalAchieved, etc.) trigger invalidate_context()
- Event subscriptions wired in services_bootstrap.py
- Use get_valid_context/cache_context for cache access

Architecture:
- UserActivityService._context_cache holds the cache instance
- invalidate_context() called by event handlers (see services_bootstrap.py)
- Context building happens in UserContextBuilder

CACHING POLICY
==============

TTL (Time-To-Live): 5 minutes (300 seconds)
-------------------------------------------
Rationale:
- UserContext contains ~240 fields aggregated from multiple domains
- Building context requires a MEGA-QUERY that hits many graph patterns
- 5 minutes balances freshness vs query cost
- Most user sessions have activity within 5-minute windows

When Cache is Invalidated:
--------------------------
The cache is invalidated IMMEDIATELY when any of these domain events occur:

    - TaskCreated, TaskCompleted, TaskUpdated, TaskDeleted
    - GoalCreated, GoalAchieved, GoalMilestoneReached, GoalProgressUpdated
    - HabitCreated, HabitCompleted, HabitStreakBroken, HabitStreakMilestone
    - EventCreated, EventCompleted, EventUpdated, EventDeleted
    - ChoiceCreated, ChoiceUpdated, ChoiceDeleted
    - PrincipleCreated, PrincipleUpdated, PrincipleDeleted, PrincipleStrengthChanged
    - ExpenseCreated, ExpenseUpdated, ExpenseDeleted, ExpensePaid
    - JournalCreated, JournalUpdated, JournalDeleted
    - KnowledgeCreated, LearningPathStarted, LearningPathCompleted

Event subscriptions are wired in services_bootstrap.py:
    event_bus.subscribe(TaskCompleted, user_activity_service.invalidate_context)

Storage: In-Memory (Per-Process)
--------------------------------
- Simple dict-based storage (no Redis/external cache)
- Each worker process has its own cache
- Sufficient for current scale (single-server deployment)
- If scaling to multiple servers, consider Redis with pub/sub invalidation

Cache Hit Rate Expectations:
----------------------------
- Expect ~80% hit rate during active user sessions
- Misses occur on: first load, after any domain mutation, after TTL expiry
- Monitoring: Use get_cache_stats() to track valid_count vs expired_count

Future Considerations:
----------------------
- Redis migration if scaling beyond single server
- Partial invalidation (only invalidate affected context sections)
- Warm-up on login (pre-build context before first request)
"""

from dataclasses import dataclass, field
from datetime import datetime

from core.services.user.unified_user_context import UserContext


@dataclass
class UserContextCache:
    """
    Manages cached user contexts for performance.

    Usage:
        cache = UserContextCache()
        context = cache.get(user_uid)
        if not context:
            context = await builder.build_complete_context(user_uid)
            cache.set(user_uid, context)
    """

    # Cache storage: user_uid -> UserContext
    _cache: dict[str, UserContext] = field(default_factory=dict)

    # Last update timestamps for monitoring
    _last_update: dict[str, datetime] = field(default_factory=dict)

    # TTL in seconds (5 minutes = 300s)
    # Rationale: Balances freshness vs MEGA-QUERY cost for ~240 field context
    # See module docstring for full caching policy documentation
    default_ttl: int = 300

    def get(self, user_uid: str) -> UserContext | None:
        """
        Get cached context if valid.

        Args:
            user_uid: User's unique identifier

        Returns:
            Cached context if valid, None otherwise
        """
        if user_uid in self._cache:
            context = self._cache[user_uid]
            if context.is_cached_valid():
                return context
        return None

    def set(self, user_uid: str, context: UserContext) -> None:
        """
        Cache a context.

        Args:
            user_uid: User's unique identifier
            context: Context to cache
        """
        context.last_refresh = datetime.now()
        self._cache[user_uid] = context
        self._last_update[user_uid] = datetime.now()

    def invalidate(self, user_uid: str) -> None:
        """
        Invalidate cached context.

        This is called when a user's state changes (task completed, habit updated, etc.)
        to ensure fresh data on next request.

        Args:
            user_uid: User's unique identifier
        """
        if user_uid in self._cache:
            del self._cache[user_uid]
            del self._last_update[user_uid]

    def invalidate_all(self) -> None:
        """Clear all cached contexts."""
        self._cache.clear()
        self._last_update.clear()

    def cleanup_expired(self) -> int:
        """
        Remove expired contexts.

        Returns:
            Number of contexts removed
        """
        expired = []

        for user_uid, context in self._cache.items():
            if not context.is_cached_valid():
                expired.append(user_uid)

        for user_uid in expired:
            self.invalidate(user_uid)

        return len(expired)

    def get_cache_stats(self) -> dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dict with cache_size, expired_count
        """
        expired_count = 0
        for context in self._cache.values():
            if not context.is_cached_valid():
                expired_count += 1

        return {
            "cache_size": len(self._cache),
            "valid_count": len(self._cache) - expired_count,
            "expired_count": expired_count,
        }


# =========================================================================
# EVENT-DRIVEN INVALIDATION (COMPLETED)
# =========================================================================
#
# Integration completed 2025-12-07:
# - UserActivityService._context_cache holds the cache instance
# - invalidate_context() calls self._context_cache.invalidate(user_uid)
# - Event subscriptions in services_bootstrap.py wire domain events:
#   - TaskCreated, TaskCompleted
#   - GoalCreated, GoalAchieved, GoalMilestoneReached, GoalProgressUpdated
#   - HabitCreated, HabitCompleted, HabitStreakBroken, HabitStreakMilestone
#   - PrincipleCreated, PrincipleUpdated, PrincipleDeleted, PrincipleStrengthChanged
#   - ChoiceCreated, ChoiceUpdated, ChoiceDeleted
#   - CalendarEventCreated, CalendarEventUpdated, CalendarEventCompleted, etc.
#   - ExpenseCreated, ExpenseUpdated, ExpenseDeleted, ExpensePaid
#   - JournalCreated, JournalUpdated, JournalDeleted
#   - KnowledgeCreated, LearningPathStarted


__all__ = ["UserContextCache"]
