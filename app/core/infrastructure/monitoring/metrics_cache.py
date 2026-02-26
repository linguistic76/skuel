"""
Metrics Cache - Prometheus as Primary with In-Memory Cache
===========================================================

Lightweight in-memory cache for recent Prometheus metrics, enabling debugging
without querying Prometheus while maintaining Prometheus as source of truth.

Design Philosophy:
- Prometheus is THE source of truth (production monitoring)
- Cache provides debugging access (development, testing)
- Direct writes (no bridge code, no 30s export lag)
- Zero duplication (cache is lossy - last 100 items only)

- January 2026 (Option D Implementation)
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.utils.logging import get_logger

logger = get_logger(__name__)


# Helper functions for dataclass default factories
def _create_deque_100() -> deque[dict[str, Any]]:
    """Create deque with maxlen=100 for recent metric tracking."""
    return deque(maxlen=100)


def _get_recent_avg_duration(item: dict[str, Any]) -> float:
    """Get recent_avg_duration_ms from dict for sorting."""
    return item.get("recent_avg_duration_ms", 0.0)


@dataclass
class CachedHandlerMetrics:
    """Cached metrics for a single event handler (debugging only)."""

    handler_name: str
    event_type: str

    # Recent executions (last 100)
    recent_executions: deque[dict[str, Any]] = field(default_factory=_create_deque_100)

    # Timestamps
    first_call_at: datetime | None = None
    last_call_at: datetime | None = None

    def record_execution(self, duration_ms: float, error: Exception | None = None) -> None:
        """Record a handler execution in cache."""
        now = datetime.now()

        if self.first_call_at is None:
            self.first_call_at = now
        self.last_call_at = now

        self.recent_executions.append(
            {
                "duration_ms": duration_ms,
                "timestamp": now.isoformat(),
                "error": str(error) if error else None,
            }
        )

    @property
    def total_calls(self) -> int:
        """Total calls tracked in cache (capped at deque size)."""
        return len(self.recent_executions)

    @property
    def recent_avg_duration_ms(self) -> float:
        """Average duration for recent calls."""
        if not self.recent_executions:
            return 0.0
        return sum(item["duration_ms"] for item in self.recent_executions) / len(
            self.recent_executions
        )

    @property
    def min_duration_ms(self) -> float:
        """Minimum duration in cache."""
        if not self.recent_executions:
            return 0.0
        return min(item["duration_ms"] for item in self.recent_executions)

    @property
    def max_duration_ms(self) -> float:
        """Maximum duration in cache."""
        if not self.recent_executions:
            return 0.0
        return max(item["duration_ms"] for item in self.recent_executions)

    @property
    def error_count(self) -> int:
        """Count of errors in cache."""
        return sum(1 for item in self.recent_executions if item.get("error"))

    @property
    def error_rate(self) -> float:
        """Error rate as percentage."""
        return (self.error_count / self.total_calls * 100) if self.total_calls > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for debugging."""
        return {
            "handler_name": self.handler_name,
            "event_type": self.event_type,
            "total_calls": self.total_calls,
            "recent_avg_duration_ms": round(self.recent_avg_duration_ms, 2),
            "min_duration_ms": round(self.min_duration_ms, 2),
            "max_duration_ms": round(self.max_duration_ms, 2),
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 2),
            "first_call_at": self.first_call_at.isoformat() if self.first_call_at else None,
            "last_call_at": self.last_call_at.isoformat() if self.last_call_at else None,
        }


@dataclass
class CachedEventMetrics:
    """Cached metrics for an event type (debugging only)."""

    event_type: str

    # Recent publications (last 100)
    recent_publications: deque[dict[str, Any]] = field(default_factory=_create_deque_100)

    # Timestamps
    first_published_at: datetime | None = None
    last_published_at: datetime | None = None

    def record_publication(self, duration_ms: float, handlers_called: int) -> None:
        """Record an event publication in cache."""
        now = datetime.now()

        if self.first_published_at is None:
            self.first_published_at = now
        self.last_published_at = now

        self.recent_publications.append(
            {
                "duration_ms": duration_ms,
                "handlers_called": handlers_called,
                "timestamp": now.isoformat(),
            }
        )

    @property
    def total_published(self) -> int:
        """Total publications in cache (capped at deque size)."""
        return len(self.recent_publications)

    @property
    def recent_avg_publish_duration_ms(self) -> float:
        """Average publish duration for recent events."""
        if not self.recent_publications:
            return 0.0
        return sum(item["duration_ms"] for item in self.recent_publications) / len(
            self.recent_publications
        )

    @property
    def avg_handlers_per_event(self) -> float:
        """Average handlers called per event."""
        if not self.recent_publications:
            return 0.0
        return sum(item["handlers_called"] for item in self.recent_publications) / len(
            self.recent_publications
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for debugging."""
        return {
            "event_type": self.event_type,
            "total_published": self.total_published,
            "recent_avg_publish_duration_ms": round(self.recent_avg_publish_duration_ms, 2),
            "avg_handlers_per_event": round(self.avg_handlers_per_event, 2),
            "first_published_at": self.first_published_at.isoformat()
            if self.first_published_at
            else None,
            "last_published_at": self.last_published_at.isoformat()
            if self.last_published_at
            else None,
        }


@dataclass
class CachedContextMetrics:
    """Cached context invalidation metrics (debugging only)."""

    user_uid: str

    # Recent invalidations (last 50)
    recent_invalidations: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=50))

    # Timestamps
    first_invalidation_at: datetime | None = None
    last_invalidation_at: datetime | None = None

    def record_invalidation(
        self, duration_ms: float, reason: str, affected_contexts: list[str]
    ) -> None:
        """Record a context invalidation in cache."""
        now = datetime.now()

        if self.first_invalidation_at is None:
            self.first_invalidation_at = now
        self.last_invalidation_at = now

        self.recent_invalidations.append(
            {
                "duration_ms": duration_ms,
                "reason": reason,
                "affected_contexts": affected_contexts,
                "timestamp": now.isoformat(),
            }
        )

    @property
    def total_invalidations(self) -> int:
        """Total invalidations in cache."""
        return len(self.recent_invalidations)

    @property
    def recent_avg_duration_ms(self) -> float:
        """Average invalidation duration."""
        if not self.recent_invalidations:
            return 0.0
        return sum(item["duration_ms"] for item in self.recent_invalidations) / len(
            self.recent_invalidations
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for debugging."""
        # Count invalidations by reason
        invalidations_by_reason: dict[str, int] = defaultdict(int)
        for item in self.recent_invalidations:
            invalidations_by_reason[item["reason"]] += 1

        return {
            "user_uid": self.user_uid,
            "total_invalidations": self.total_invalidations,
            "recent_avg_duration_ms": round(self.recent_avg_duration_ms, 2),
            "invalidations_by_reason": dict(invalidations_by_reason),
            "first_invalidation_at": self.first_invalidation_at.isoformat()
            if self.first_invalidation_at
            else None,
            "last_invalidation_at": self.last_invalidation_at.isoformat()
            if self.last_invalidation_at
            else None,
        }


class MetricsCache:
    """
    Metrics cache with Prometheus as primary source of truth.

    Design:
    - Write to Prometheus (source of truth for production)
    - Cache recent values in memory (debugging access for development)
    - No bridge code needed (direct writes)
    - Cache is lossy (last 100 items only)

    Thread-safe for async operations.
    """

    def __init__(self, prometheus_metrics: Any, enabled: bool = True) -> None:
        """
        Initialize metrics cache.

        Args:
            prometheus_metrics: PrometheusMetrics instance (source of truth)
            enabled: Enable/disable caching (Prometheus always updated)
        """
        self.prometheus_metrics = prometheus_metrics
        self.enabled = enabled

        # Cache storage (debugging only)
        self._handler_cache: dict[str, CachedHandlerMetrics] = {}
        self._event_cache: dict[str, CachedEventMetrics] = {}
        self._context_cache: dict[str, CachedContextMetrics] = {}

        logger.info(f"MetricsCache initialized (cache_enabled={enabled})")

    def _get_handler_key(self, event_type: str, handler_name: str) -> str:
        """Generate unique key for handler cache."""
        return f"{event_type}:{handler_name}"

    async def record_handler_execution(
        self, event_type: str, handler_name: str, duration_ms: float, error: Exception | None = None
    ) -> None:
        """
        Record a handler execution.

        Writes to Prometheus (source of truth) and updates cache (debugging).

        Args:
            event_type: Type of event handled
            handler_name: Name of the handler function
            duration_ms: Execution duration in milliseconds
            error: Exception if handler failed
        """
        # Write to Prometheus (ALWAYS - source of truth)
        self.prometheus_metrics.events.event_handler_duration_seconds.labels(
            event_type=event_type, handler=handler_name
        ).observe(duration_ms / 1000.0)

        self.prometheus_metrics.events.event_handler_calls_total.labels(
            event_type=event_type, handler=handler_name
        ).inc()

        if error:
            self.prometheus_metrics.events.event_handler_errors_total.labels(
                event_type=event_type, handler=handler_name
            ).inc()

        # Update cache (debugging only)
        if self.enabled:
            key = self._get_handler_key(event_type, handler_name)
            if key not in self._handler_cache:
                self._handler_cache[key] = CachedHandlerMetrics(
                    handler_name=handler_name, event_type=event_type
                )
            self._handler_cache[key].record_execution(duration_ms, error)

    async def record_event_publication(
        self, event_type: str, duration_ms: float, handlers_called: int
    ) -> None:
        """
        Record an event publication.

        Writes to Prometheus and updates cache.

        Args:
            event_type: Type of event published
            duration_ms: Time to publish and call all handlers
            handlers_called: Number of handlers invoked
        """
        # Write to Prometheus (source of truth)
        self.prometheus_metrics.events.events_published_total.labels(event_type=event_type).inc()

        self.prometheus_metrics.events.event_publish_duration_seconds.labels(
            event_type=event_type
        ).observe(duration_ms / 1000.0)

        # Update cache (debugging only)
        if self.enabled:
            if event_type not in self._event_cache:
                self._event_cache[event_type] = CachedEventMetrics(event_type=event_type)
            self._event_cache[event_type].record_publication(duration_ms, handlers_called)

    async def record_context_invalidation(
        self, user_uid: str, duration_ms: float, reason: str, affected_contexts: list[str]
    ) -> None:
        """
        Record a context invalidation.

        Writes to Prometheus and updates cache.

        Args:
            user_uid: User whose context was invalidated
            duration_ms: Invalidation duration
            reason: Why context was invalidated
            affected_contexts: Which contexts were affected
        """
        # Write to Prometheus (source of truth)
        self.prometheus_metrics.events.context_invalidations_total.inc()

        # Update cache (debugging only)
        if self.enabled:
            if user_uid not in self._context_cache:
                self._context_cache[user_uid] = CachedContextMetrics(user_uid=user_uid)
            self._context_cache[user_uid].record_invalidation(
                duration_ms, reason, affected_contexts
            )

    async def get_handler_metrics(self, event_type: str | None = None) -> list[dict[str, Any]]:
        """
        Get cached handler metrics for debugging.

        Args:
            event_type: Filter by event type (None = all handlers)

        Returns:
            List of handler metrics from cache (last 100 calls per handler)
        """
        if not self.enabled:
            return []

        if event_type:
            metrics = [
                m.to_dict() for m in self._handler_cache.values() if m.event_type == event_type
            ]
        else:
            metrics = [m.to_dict() for m in self._handler_cache.values()]

        # Sort by total calls (most active first)
        def get_total_calls(item: dict[str, Any]) -> int:
            return item.get("total_calls", 0)

        metrics.sort(key=get_total_calls, reverse=True)
        return metrics

    async def get_event_metrics(self) -> list[dict[str, Any]]:
        """Get cached event publication metrics for debugging."""
        if not self.enabled:
            return []

        metrics = [m.to_dict() for m in self._event_cache.values()]

        # Sort by total published (most active first)
        def get_total_published(item: dict[str, Any]) -> int:
            return item.get("total_published", 0)

        metrics.sort(key=get_total_published, reverse=True)
        return metrics

    async def get_context_invalidation_metrics(
        self, user_uid: str | None = None
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """
        Get cached context invalidation metrics.

        Args:
            user_uid: Get metrics for specific user (None = all users)

        Returns:
            Single user metrics dict, list of all users, or None
        """
        if not self.enabled:
            return [] if user_uid is None else None

        if user_uid:
            user_metrics = self._context_cache.get(user_uid)
            return user_metrics.to_dict() if user_metrics else None
        else:
            metrics_list = [m.to_dict() for m in self._context_cache.values()]

            # Sort by total invalidations
            def get_total_invalidations(item: dict[str, Any]) -> int:
                return item.get("total_invalidations", 0)

            metrics_list.sort(key=get_total_invalidations, reverse=True)
            return metrics_list

    async def get_slow_handlers(self, threshold_ms: float = 100.0) -> list[dict[str, Any]]:
        """
        Get list of slow handlers from cache.

        Args:
            threshold_ms: Duration threshold

        Returns:
            List of slow handlers (recent avg > threshold)
        """
        if not self.enabled:
            return []

        slow_handlers = [
            metrics.to_dict()
            for metrics in self._handler_cache.values()
            if metrics.recent_avg_duration_ms > threshold_ms
        ]

        # Sort by recent avg duration (slowest first)
        slow_handlers.sort(key=_get_recent_avg_duration, reverse=True)
        return slow_handlers

    async def get_summary(self) -> dict[str, Any]:
        """
        Get overall cache summary for debugging.

        Note: This is cache-only data (lossy). For complete metrics, query Prometheus.
        """
        if not self.enabled:
            return {
                "enabled": False,
                "cache_note": "Cache disabled. Query Prometheus for complete metrics.",
            }

        total_handler_calls = sum(m.total_calls for m in self._handler_cache.values())
        total_handler_errors = sum(m.error_count for m in self._handler_cache.values())
        total_events_published = sum(m.total_published for m in self._event_cache.values())
        total_invalidations = sum(m.total_invalidations for m in self._context_cache.values())

        return {
            "enabled": True,
            "cache_note": "Cache contains last 100 items. Query Prometheus for complete data.",
            "total_handlers_cached": len(self._handler_cache),
            "total_event_types_cached": len(self._event_cache),
            "total_users_tracked": len(self._context_cache),
            "cached_handler_calls": total_handler_calls,
            "cached_handler_errors": total_handler_errors,
            "cached_events_published": total_events_published,
            "cached_context_invalidations": total_invalidations,
            "cache_error_rate": round(
                (total_handler_errors / total_handler_calls * 100)
                if total_handler_calls > 0
                else 0.0,
                2,
            ),
        }

    async def reset(self) -> None:
        """
        Reset cache (for testing).

        Note: This does NOT reset Prometheus metrics.
        """
        self._handler_cache.clear()
        self._event_cache.clear()
        self._context_cache.clear()
        logger.info("MetricsCache reset (Prometheus metrics unchanged)")


__all__ = ["MetricsCache"]
