"""
Debounced Context Invalidator
=============================

Performance optimization for event-driven context invalidation.

Problem:
When a user completes a task, multiple events fire:
1. TaskCompleted → invalidates context
2. GoalProgressUpdated (from task) → invalidates AGAIN
3. KnowledgeBulkApplied → invalidates AGAIN

This causes 3+ redundant cache invalidations in rapid succession.

Solution:
Debounce invalidation per user - wait a short delay before invalidating,
and cancel any pending invalidation if a new one arrives. This collapses
multiple invalidation requests into a single operation.

Performance Impact:
- Before: 5-10 invalidations per user action
- After: 1 invalidation per user action (after debounce delay)
"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


class DebouncedContextInvalidator:
    """
    Debounces context invalidation requests per user.

    When multiple events trigger invalidation for the same user in quick
    succession, only the final invalidation executes after the delay.

    Usage:
        invalidator = DebouncedContextInvalidator(
            invalidate_fn=user_activity_service._do_invalidate,
            delay_ms=100,
        )

        # These will be collapsed into a single invalidation
        await invalidator.invalidate("user.mike", "task_completed")
        await invalidator.invalidate("user.mike", "goal_progress_updated")
        await invalidator.invalidate("user.mike", "knowledge_applied")
        # Result: Only one _do_invalidate call after 100ms

    Thread Safety:
        This class is designed for single-threaded async use.
        All operations must be called from the same event loop.
    """

    def __init__(
        self,
        invalidate_fn: Callable[[str, str, list[str] | None], Coroutine[Any, Any, None]],
        delay_ms: int = 100,
    ) -> None:
        """
        Initialize debounced invalidator.

        Args:
            invalidate_fn: Async function to call for actual invalidation.
                           Signature: (user_uid, reason, affected_contexts) -> None
            delay_ms: Delay in milliseconds before executing invalidation.
                      Default 100ms provides good balance between responsiveness
                      and batching efficiency.
        """
        self._invalidate_fn = invalidate_fn
        self._delay_seconds = delay_ms / 1000
        self._pending: dict[str, asyncio.Task[None]] = {}
        self._pending_reasons: dict[str, list[str]] = {}
        self._stats = {
            "requests_received": 0,
            "requests_debounced": 0,
            "invalidations_executed": 0,
        }
        logger.debug(f"DebouncedContextInvalidator initialized (delay={delay_ms}ms)")

    async def invalidate(
        self,
        user_uid: str,
        reason: str = "event",
        affected_contexts: list[str] | None = None,
    ) -> None:
        """
        Request context invalidation for a user (debounced).

        If an invalidation is already pending for this user, it is cancelled
        and replaced with a new one. The actual invalidation only executes
        after the delay passes without any new requests.

        Args:
            user_uid: User whose context should be invalidated
            reason: Why invalidation was requested (for logging/metrics)
            affected_contexts: Which contexts are affected (passed to invalidate_fn)
        """
        self._stats["requests_received"] += 1

        # Track all reasons for debugging
        if user_uid not in self._pending_reasons:
            self._pending_reasons[user_uid] = []
        self._pending_reasons[user_uid].append(reason)

        # Cancel any pending invalidation for this user
        if user_uid in self._pending:
            self._pending[user_uid].cancel()
            self._stats["requests_debounced"] += 1
            logger.debug(
                f"Debounced invalidation for {user_uid} "
                f"(reasons so far: {self._pending_reasons[user_uid]})"
            )

        # Schedule new debounced invalidation
        self._pending[user_uid] = asyncio.create_task(
            self._delayed_invalidate(user_uid, reason, affected_contexts)
        )

    async def _delayed_invalidate(
        self,
        user_uid: str,
        reason: str,
        affected_contexts: list[str] | None,
    ) -> None:
        """
        Execute invalidation after delay.

        If cancelled before delay completes, no invalidation occurs.
        """
        try:
            await asyncio.sleep(self._delay_seconds)

            # Collect all reasons that were debounced
            all_reasons = self._pending_reasons.get(user_uid, [reason])
            combined_reason = (
                f"debounced({len(all_reasons)}): {', '.join(all_reasons[:3])}"
                if len(all_reasons) > 1
                else reason
            )

            # Execute actual invalidation
            await self._invalidate_fn(user_uid, combined_reason, affected_contexts)
            self._stats["invalidations_executed"] += 1

            logger.debug(
                f"Executed debounced invalidation for {user_uid} "
                f"(collapsed {len(all_reasons)} requests)"
            )

        except asyncio.CancelledError:
            # Expected when a new request replaces this one
            pass
        finally:
            # Cleanup
            self._pending.pop(user_uid, None)
            self._pending_reasons.pop(user_uid, None)

    async def flush(self, user_uid: str | None = None) -> Result[None]:
        """
        Immediately execute any pending invalidations.

        Useful for testing or when you need to ensure invalidation completes.

        Args:
            user_uid: If provided, only flush for this user.
                      If None, flush all pending invalidations.

        Returns:
            Result[None] indicating success.
        """
        if user_uid:
            if user_uid in self._pending:
                self._pending[user_uid].cancel()
                await self._invalidate_fn(
                    user_uid,
                    "flush",
                    None,
                )
                self._pending.pop(user_uid, None)
                self._pending_reasons.pop(user_uid, None)
        else:
            # Flush all
            for uid in list(self._pending.keys()):
                await self.flush(uid)
        return Result.ok(None)

    def get_pending_count(self) -> int:
        """Get number of pending invalidations."""
        return len(self._pending)

    def get_stats(self) -> dict[str, int]:
        """
        Get debouncing statistics.

        Returns:
            Dict with:
            - requests_received: Total invalidation requests
            - requests_debounced: Requests that were collapsed
            - invalidations_executed: Actual invalidations performed
        """
        return self._stats.copy()

    def get_efficiency(self) -> float:
        """
        Calculate debouncing efficiency (0.0 to 1.0).

        Higher is better - means more requests were collapsed.

        Returns:
            Ratio of debounced requests to total requests.
            Returns 0.0 if no requests received yet.
        """
        if self._stats["requests_received"] == 0:
            return 0.0
        return self._stats["requests_debounced"] / self._stats["requests_received"]
