"""
Performance Metrics Infrastructure
===================================

Lightweight performance monitoring for event system, context invalidation,
and handler bottleneck detection.

Features:
- Event processing time tracking
- Handler performance monitoring
- Context invalidation metrics
- Bottleneck detection
- In-memory metrics with configurable retention

Design Philosophy:
- Zero external dependencies (no Prometheus/StatsD required)
- Minimal overhead (< 1ms per event)
- Thread-safe for async operations
- Automatic cleanup of old metrics
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from core.utils.logging import get_logger

logger = get_logger(__name__)


# Helper functions for dataclass default factories
def _create_deque_100() -> deque[float]:
    """Create deque with maxlen=100 for recent duration tracking."""
    return deque(maxlen=100)


def _create_deque_50() -> deque[float]:
    """Create deque with maxlen=50 for recent duration tracking."""
    return deque(maxlen=50)


def _create_defaultdict_int() -> dict[str, int]:
    """Create defaultdict(int) for counting."""
    return defaultdict(int)


# Helper functions for sorting metrics
def _get_recent_avg_duration(metrics_dict: dict[str, Any]) -> float:
    """Get recent_avg_duration_ms from metrics dict for sorting."""
    return metrics_dict["recent_avg_duration_ms"]


def _get_total_calls(metrics_dict: dict[str, Any]) -> int:
    """Get total_calls from metrics dict for sorting."""
    return metrics_dict["total_calls"]


def _get_total_published(metrics_dict: dict[str, Any]) -> int:
    """Get total_published from metrics dict for sorting."""
    return metrics_dict["total_published"]


def _get_total_invalidations(metrics_dict: dict[str, Any]) -> int:
    """Get total_invalidations from metrics dict for sorting."""
    return metrics_dict["total_invalidations"]


@dataclass
class HandlerMetrics:
    """Performance metrics for a single event handler."""

    handler_name: str
    event_type: str

    # Timing metrics
    total_calls: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0

    # Recent performance (sliding window)
    recent_durations: deque[float] = field(default_factory=_create_deque_100)

    # Error tracking
    error_count: int = 0
    last_error: str | None = None
    last_error_at: datetime | None = None

    # Timestamps
    first_call_at: datetime | None = None
    last_call_at: datetime | None = None

    def record_execution(self, duration_ms: float, error: Exception | None = None) -> None:
        """Record a handler execution."""
        self.total_calls += 1
        self.total_duration_ms += duration_ms
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.recent_durations.append(duration_ms)

        now = datetime.now()
        if self.first_call_at is None:
            self.first_call_at = now
        self.last_call_at = now

        if error:
            self.error_count += 1
            self.last_error = str(error)
            self.last_error_at = now

    @property
    def avg_duration_ms(self) -> float:
        """Average duration across all calls."""
        return self.total_duration_ms / self.total_calls if self.total_calls > 0 else 0.0

    @property
    def recent_avg_duration_ms(self) -> float:
        """Average duration for recent calls (sliding window)."""
        return (
            sum(self.recent_durations) / len(self.recent_durations)
            if self.recent_durations
            else 0.0
        )

    @property
    def error_rate(self) -> float:
        """Error rate as percentage."""
        return (self.error_count / self.total_calls * 100) if self.total_calls > 0 else 0.0

    def is_slow(self, threshold_ms: float = 100.0) -> bool:
        """Check if handler is slow (recent avg > threshold)."""
        return self.recent_avg_duration_ms > threshold_ms

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "handler_name": self.handler_name,
            "event_type": self.event_type,
            "total_calls": self.total_calls,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "recent_avg_duration_ms": round(self.recent_avg_duration_ms, 2),
            "min_duration_ms": round(self.min_duration_ms, 2)
            if self.min_duration_ms != float("inf")
            else 0.0,
            "max_duration_ms": round(self.max_duration_ms, 2),
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 2),
            "is_slow": self.is_slow(),
            "first_call_at": self.first_call_at.isoformat() if self.first_call_at else None,
            "last_call_at": self.last_call_at.isoformat() if self.last_call_at else None,
        }


@dataclass
class EventMetrics:
    """Aggregated metrics for an event type."""

    event_type: str

    # Publication metrics
    total_published: int = 0
    total_handlers_called: int = 0

    # Timing metrics (event publishing overhead)
    total_publish_duration_ms: float = 0.0
    recent_publish_durations: deque[float] = field(default_factory=_create_deque_100)

    # Timestamps
    first_published_at: datetime | None = None
    last_published_at: datetime | None = None

    def record_publication(self, duration_ms: float, handlers_called: int) -> None:
        """Record an event publication."""
        self.total_published += 1
        self.total_handlers_called += handlers_called
        self.total_publish_duration_ms += duration_ms
        self.recent_publish_durations.append(duration_ms)

        now = datetime.now()
        if self.first_published_at is None:
            self.first_published_at = now
        self.last_published_at = now

    @property
    def avg_publish_duration_ms(self) -> float:
        """Average publish duration."""
        return (
            self.total_publish_duration_ms / self.total_published
            if self.total_published > 0
            else 0.0
        )

    @property
    def recent_avg_publish_duration_ms(self) -> float:
        """Recent average publish duration."""
        return (
            sum(self.recent_publish_durations) / len(self.recent_publish_durations)
            if self.recent_publish_durations
            else 0.0
        )

    @property
    def avg_handlers_per_event(self) -> float:
        """Average number of handlers called per event."""
        return (
            self.total_handlers_called / self.total_published if self.total_published > 0 else 0.0
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type,
            "total_published": self.total_published,
            "avg_publish_duration_ms": round(self.avg_publish_duration_ms, 2),
            "recent_avg_publish_duration_ms": round(self.recent_avg_publish_duration_ms, 2),
            "avg_handlers_per_event": round(self.avg_handlers_per_event, 2),
            "total_handlers_called": self.total_handlers_called,
            "first_published_at": self.first_published_at.isoformat()
            if self.first_published_at
            else None,
            "last_published_at": self.last_published_at.isoformat()
            if self.last_published_at
            else None,
        }


@dataclass
class ContextInvalidationMetrics:
    """Metrics for user context invalidation operations."""

    user_uid: str

    # Invalidation counts
    total_invalidations: int = 0
    invalidations_by_reason: dict[str, int] = field(default_factory=_create_defaultdict_int)

    # Timing metrics
    total_duration_ms: float = 0.0
    recent_durations: deque[float] = field(default_factory=_create_deque_50)

    # Affected contexts tracking
    affected_contexts_count: dict[str, int] = field(default_factory=_create_defaultdict_int)

    # Timestamps
    first_invalidation_at: datetime | None = None
    last_invalidation_at: datetime | None = None

    def record_invalidation(
        self, duration_ms: float, reason: str, affected_contexts: list[str]
    ) -> None:
        """Record a context invalidation."""
        self.total_invalidations += 1
        self.invalidations_by_reason[reason] += 1
        self.total_duration_ms += duration_ms
        self.recent_durations.append(duration_ms)

        for context in affected_contexts:
            self.affected_contexts_count[context] += 1

        now = datetime.now()
        if self.first_invalidation_at is None:
            self.first_invalidation_at = now
        self.last_invalidation_at = now

    @property
    def avg_duration_ms(self) -> float:
        """Average invalidation duration."""
        return (
            self.total_duration_ms / self.total_invalidations
            if self.total_invalidations > 0
            else 0.0
        )

    @property
    def recent_avg_duration_ms(self) -> float:
        """Recent average invalidation duration."""
        return (
            sum(self.recent_durations) / len(self.recent_durations)
            if self.recent_durations
            else 0.0
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "user_uid": self.user_uid,
            "total_invalidations": self.total_invalidations,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "recent_avg_duration_ms": round(self.recent_avg_duration_ms, 2),
            "invalidations_by_reason": dict(self.invalidations_by_reason),
            "affected_contexts_count": dict(self.affected_contexts_count),
            "first_invalidation_at": self.first_invalidation_at.isoformat()
            if self.first_invalidation_at
            else None,
            "last_invalidation_at": self.last_invalidation_at.isoformat()
            if self.last_invalidation_at
            else None,
        }


class PerformanceMonitor:
    """
    Performance monitoring system for event processing and context invalidation.

    Thread-safe for async operations. Minimal overhead design.
    """

    def __init__(
        self,
        enabled: bool = True,
        slow_handler_threshold_ms: float = 100.0,
        retention_hours: int = 24,
    ) -> None:
        """
        Initialize performance monitor.

        Args:
            enabled: Enable/disable monitoring (set False for production if needed),
            slow_handler_threshold_ms: Threshold for slow handler detection,
            retention_hours: How long to retain metrics (for cleanup)
        """
        self.enabled = enabled
        self.slow_handler_threshold_ms = slow_handler_threshold_ms
        self.retention_hours = retention_hours

        # Metrics storage
        self._handler_metrics: dict[str, HandlerMetrics] = {}  # key: "event_type:handler_name"
        self._event_metrics: dict[str, EventMetrics] = {}  # key: event_type
        self._context_metrics: dict[str, ContextInvalidationMetrics] = {}  # key: user_uid

        # Lock for thread safety
        self._lock = asyncio.Lock()

        logger.info(
            f"Performance monitor initialized (enabled={enabled}, "
            f"slow_threshold={slow_handler_threshold_ms}ms)"
        )

    def _get_handler_key(self, event_type: str, handler_name: str) -> str:
        """Generate unique key for handler metrics."""
        return f"{event_type}:{handler_name}"

    async def record_handler_execution(
        self, event_type: str, handler_name: str, duration_ms: float, error: Exception | None = None
    ) -> None:
        """
        Record a handler execution.

        Args:
            event_type: Type of event handled,
            handler_name: Name of the handler function,
            duration_ms: Execution duration in milliseconds,
            error: Exception if handler failed
        """
        if not self.enabled:
            return

        async with self._lock:
            key = self._get_handler_key(event_type, handler_name)

            if key not in self._handler_metrics:
                self._handler_metrics[key] = HandlerMetrics(
                    handler_name=handler_name, event_type=event_type
                )

            self._handler_metrics[key].record_execution(duration_ms, error)

            # Log warning for slow handlers
            if duration_ms > self.slow_handler_threshold_ms:
                logger.warning(
                    f"Slow handler detected: {handler_name} for {event_type} "
                    f"({duration_ms:.2f}ms > {self.slow_handler_threshold_ms}ms)"
                )

    async def record_event_publication(
        self, event_type: str, duration_ms: float, handlers_called: int
    ) -> None:
        """
        Record an event publication.

        Args:
            event_type: Type of event published,
            duration_ms: Time to publish and call all handlers,
            handlers_called: Number of handlers invoked
        """
        if not self.enabled:
            return

        async with self._lock:
            if event_type not in self._event_metrics:
                self._event_metrics[event_type] = EventMetrics(event_type=event_type)

            self._event_metrics[event_type].record_publication(duration_ms, handlers_called)

    async def record_context_invalidation(
        self, user_uid: str, duration_ms: float, reason: str, affected_contexts: list[str]
    ) -> None:
        """
        Record a context invalidation operation.

        Args:
            user_uid: User whose context was invalidated,
            duration_ms: Invalidation duration,
            reason: Why context was invalidated,
            affected_contexts: Which contexts were affected
        """
        if not self.enabled:
            return

        async with self._lock:
            if user_uid not in self._context_metrics:
                self._context_metrics[user_uid] = ContextInvalidationMetrics(user_uid=user_uid)

            self._context_metrics[user_uid].record_invalidation(
                duration_ms=duration_ms, reason=reason, affected_contexts=affected_contexts
            )

    async def get_slow_handlers(self, threshold_ms: float | None = None) -> list[dict[str, Any]]:
        """
        Get list of slow handlers.

        Args:
            threshold_ms: Custom threshold (uses default if None)

        Returns:
            List of slow handler metrics
        """
        threshold = threshold_ms if threshold_ms is not None else self.slow_handler_threshold_ms

        async with self._lock:
            slow_handlers = [
                metrics.to_dict()
                for metrics in self._handler_metrics.values()
                if metrics.recent_avg_duration_ms > threshold
            ]

        # Sort by recent avg duration (slowest first)
        slow_handlers.sort(key=_get_recent_avg_duration, reverse=True)
        return slow_handlers

    async def get_handler_metrics(self, event_type: str | None = None) -> list[dict[str, Any]]:
        """
        Get handler metrics, optionally filtered by event type.

        Args:
            event_type: Filter by event type (None = all handlers),

        Returns:
            List of handler metrics
        """
        async with self._lock:
            if event_type:
                metrics = [
                    m.to_dict()
                    for m in self._handler_metrics.values()
                    if m.event_type == event_type
                ]
            else:
                metrics = [m.to_dict() for m in self._handler_metrics.values()]

        # Sort by total calls (most active first)
        metrics.sort(key=_get_total_calls, reverse=True)
        return metrics

    async def get_event_metrics(self) -> list[dict[str, Any]]:
        """Get event publication metrics."""
        async with self._lock:
            metrics = [m.to_dict() for m in self._event_metrics.values()]

        # Sort by total published (most active first)
        metrics.sort(key=_get_total_published, reverse=True)
        return metrics

    async def get_context_invalidation_metrics(
        self, user_uid: str | None = None
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """
        Get context invalidation metrics.

        Args:
            user_uid: Get metrics for specific user (None = all users),

        Returns:
            Single user metrics dict, list of all users, or None
        """
        async with self._lock:
            if user_uid:
                user_metrics = self._context_metrics.get(user_uid)
                return user_metrics.to_dict() if user_metrics else None
            else:
                metrics_list = [m.to_dict() for m in self._context_metrics.values()]

        # Sort by total invalidations (most active first)
        metrics_list.sort(key=_get_total_invalidations, reverse=True)
        return metrics_list

    async def get_summary(self) -> dict[str, Any]:
        """Get overall performance summary."""
        async with self._lock:
            total_handlers = len(self._handler_metrics)
            total_events = len(self._event_metrics)
            total_users_tracked = len(self._context_metrics)

            slow_handlers = sum(
                1
                for m in self._handler_metrics.values()
                if m.recent_avg_duration_ms > self.slow_handler_threshold_ms
            )

            total_handler_calls = sum(m.total_calls for m in self._handler_metrics.values())
            total_handler_errors = sum(m.error_count for m in self._handler_metrics.values())
            total_events_published = sum(m.total_published for m in self._event_metrics.values())
            total_invalidations = sum(m.total_invalidations for m in self._context_metrics.values())

        return {
            "enabled": self.enabled,
            "slow_handler_threshold_ms": self.slow_handler_threshold_ms,
            "total_handlers_monitored": total_handlers,
            "total_event_types": total_events,
            "total_users_tracked": total_users_tracked,
            "slow_handlers_count": slow_handlers,
            "total_handler_calls": total_handler_calls,
            "total_handler_errors": total_handler_errors,
            "total_events_published": total_events_published,
            "total_context_invalidations": total_invalidations,
            "error_rate": round(
                (total_handler_errors / total_handler_calls * 100)
                if total_handler_calls > 0
                else 0.0,
                2,
            ),
        }

    async def cleanup_old_metrics(self) -> None:
        """Remove metrics older than retention period."""
        if not self.enabled:
            return

        cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)

        async with self._lock:
            # Cleanup handler metrics
            keys_to_remove = [
                key
                for key, metrics in self._handler_metrics.items()
                if metrics.last_call_at and metrics.last_call_at < cutoff_time
            ]
            for key in keys_to_remove:
                del self._handler_metrics[key]

            # Cleanup event metrics
            event_types_to_remove = [
                event_type
                for event_type, metrics in self._event_metrics.items()
                if metrics.last_published_at and metrics.last_published_at < cutoff_time
            ]
            for event_type in event_types_to_remove:
                del self._event_metrics[event_type]

            # Cleanup context metrics
            users_to_remove = [
                user_uid
                for user_uid, metrics in self._context_metrics.items()
                if metrics.last_invalidation_at and metrics.last_invalidation_at < cutoff_time
            ]
            for user_uid in users_to_remove:
                del self._context_metrics[user_uid]

        if keys_to_remove or event_types_to_remove or users_to_remove:
            logger.info(
                f"Cleaned up old metrics: {len(keys_to_remove)} handlers, "
                f"{len(event_types_to_remove)} events, {len(users_to_remove)} users"
            )

    async def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        async with self._lock:
            self._handler_metrics.clear()
            self._event_metrics.clear()
            self._context_metrics.clear()

        logger.info("Performance metrics reset")


# ============================================================================
# GLOBAL MONITOR INSTANCE
# ============================================================================

_performance_monitor: PerformanceMonitor | None = None


def get_performance_monitor(
    enabled: bool = True, slow_handler_threshold_ms: float = 100.0, retention_hours: int = 24
) -> PerformanceMonitor:
    """
    Get global performance monitor instance (singleton pattern).

    Args:
        enabled: Enable monitoring,
        slow_handler_threshold_ms: Threshold for slow handler detection,
        retention_hours: Metrics retention period

    Returns:
        Global PerformanceMonitor instance
    """
    global _performance_monitor

    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor(
            enabled=enabled,
            slow_handler_threshold_ms=slow_handler_threshold_ms,
            retention_hours=retention_hours,
        )

    return _performance_monitor


def reset_performance_monitor() -> None:
    """Reset global performance monitor (for testing)."""
    global _performance_monitor
    _performance_monitor = None
