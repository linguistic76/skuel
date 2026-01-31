"""
Query Metrics Cache - Prometheus as Primary with In-Memory Cache
=================================================================

Lightweight in-memory cache for recent query/operation metrics, enabling debugging
without querying Prometheus while maintaining Prometheus as source of truth.

Replaces MetricsStore with Prometheus-first architecture.

Design Philosophy:
- Prometheus is THE source of truth (production monitoring)
- Cache provides debugging access (last 100 timings per operation)
- Direct writes (no bridge code, no export lag)
- Zero duplication (cache is lossy subset)

Phase 3.6 - January 2026 (Option D Pattern for Query Metrics)
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.utils.logging import get_logger

logger = get_logger(__name__)


# Helper functions
def _create_deque_100() -> deque[float]:
    """Create deque with maxlen=100 for recent timing tracking."""
    return deque(maxlen=100)


def _get_avg_time_ms(metrics_dict: dict[str, Any]) -> float:
    """Get avg_time_ms from metrics dict for sorting."""
    return metrics_dict.get("avg_time_ms", 0.0)


@dataclass
class CachedOperationMetrics:
    """Cached metrics for a single operation (debugging only)."""

    operation_name: str

    # Recent timings (last 100)
    recent_times: deque[float] = field(default_factory=_create_deque_100)

    # Error tracking
    error_count: int = 0

    # Timestamps
    first_called: datetime | None = None
    last_called: datetime | None = None

    def record_timing(self, duration_ms: float, had_error: bool = False) -> None:
        """Record a timing measurement in cache."""
        now = datetime.now(UTC)

        if self.first_called is None:
            self.first_called = now
        self.last_called = now

        self.recent_times.append(duration_ms)

        if had_error:
            self.error_count += 1

    @property
    def call_count(self) -> int:
        """Total calls tracked in cache (capped at deque size)."""
        return len(self.recent_times)

    @property
    def total_time_ms(self) -> float:
        """Total time for cached calls."""
        return sum(self.recent_times)

    @property
    def avg_time_ms(self) -> float:
        """Average execution time."""
        return self.total_time_ms / self.call_count if self.call_count > 0 else 0.0

    @property
    def min_time_ms(self) -> float | None:
        """Minimum time in cache."""
        return min(self.recent_times) if self.recent_times else None

    @property
    def max_time_ms(self) -> float | None:
        """Maximum time in cache."""
        return max(self.recent_times) if self.recent_times else None

    @property
    def p95_time_ms(self) -> float | None:
        """95th percentile execution time."""
        if len(self.recent_times) < 2:
            return None
        sorted_times = sorted(self.recent_times)
        index = int(len(sorted_times) * 0.95)
        return sorted_times[index]

    @property
    def p99_time_ms(self) -> float | None:
        """99th percentile execution time."""
        if len(self.recent_times) < 2:
            return None
        sorted_times = sorted(self.recent_times)
        index = int(len(sorted_times) * 0.99)
        return sorted_times[index]

    @property
    def error_rate(self) -> float:
        """Error rate as percentage."""
        return (self.error_count / self.call_count * 100) if self.call_count > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for debugging."""
        return {
            "operation_name": self.operation_name,
            "call_count": self.call_count,
            "total_time_ms": round(self.total_time_ms, 2),
            "avg_time_ms": round(self.avg_time_ms, 2),
            "min_time_ms": round(self.min_time_ms, 2) if self.min_time_ms else None,
            "max_time_ms": round(self.max_time_ms, 2) if self.max_time_ms else None,
            "p95_time_ms": round(self.p95_time_ms, 2) if self.p95_time_ms else None,
            "p99_time_ms": round(self.p99_time_ms, 2) if self.p99_time_ms else None,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 2),
            "last_called": self.last_called.isoformat() if self.last_called else None,
        }


class QueryMetricsCache:
    """
    Query metrics cache with Prometheus as primary source of truth.

    Design:
    - Write to Prometheus (source of truth for production)
    - Cache recent values in memory (last 100 per operation for debugging)
    - No bridge code needed (direct writes)
    - Cache is lossy (only last 100 timings)

    Compatible with MetricsStore API for easy migration.
    """

    def __init__(self, prometheus_metrics: Any, enabled: bool = True) -> None:
        """
        Initialize query metrics cache.

        Args:
            prometheus_metrics: PrometheusMetrics instance (source of truth)
            enabled: Enable/disable caching (Prometheus always updated)
        """
        self.prometheus_metrics = prometheus_metrics
        self.enabled = enabled
        self.start_time = datetime.now(UTC)

        # Cache storage (debugging only)
        self._operations: dict[str, CachedOperationMetrics] = {}

        logger.info(f"QueryMetricsCache initialized (cache_enabled={enabled})")

    async def record_timing(
        self, operation_name: str, duration_ms: float, had_error: bool = False
    ) -> None:
        """
        Record timing for an operation.

        Writes to Prometheus (source of truth) and updates cache (debugging).

        Args:
            operation_name: Name of the operation (e.g., "ku_search_by_title")
            duration_ms: Execution duration in milliseconds
            had_error: Whether the operation had an error
        """
        # Write to Prometheus (ALWAYS - source of truth)
        self.prometheus_metrics.queries.operation_calls_total.labels(
            operation_name=operation_name
        ).inc()

        self.prometheus_metrics.queries.operation_duration_seconds.labels(
            operation_name=operation_name
        ).observe(duration_ms / 1000.0)

        if had_error:
            self.prometheus_metrics.queries.operation_errors_total.labels(
                operation_name=operation_name
            ).inc()

        # Update cache (debugging only)
        if self.enabled:
            if operation_name not in self._operations:
                self._operations[operation_name] = CachedOperationMetrics(
                    operation_name=operation_name
                )
            self._operations[operation_name].record_timing(duration_ms, had_error)

    def record_timing_sync(
        self, operation_name: str, duration_ms: float, had_error: bool = False
    ) -> None:
        """
        Synchronous version of record_timing for non-async contexts.

        Note: Prometheus client is thread-safe and can be called synchronously.
        """
        # Write to Prometheus (ALWAYS - source of truth)
        self.prometheus_metrics.queries.operation_calls_total.labels(
            operation_name=operation_name
        ).inc()

        self.prometheus_metrics.queries.operation_duration_seconds.labels(
            operation_name=operation_name
        ).observe(duration_ms / 1000.0)

        if had_error:
            self.prometheus_metrics.queries.operation_errors_total.labels(
                operation_name=operation_name
            ).inc()

        # Update cache (debugging only)
        if self.enabled:
            if operation_name not in self._operations:
                self._operations[operation_name] = CachedOperationMetrics(
                    operation_name=operation_name
                )
            self._operations[operation_name].record_timing(duration_ms, had_error)

    async def get_metrics(self, operation_name: str | None = None) -> dict[str, Any]:
        """
        Get cached metrics for specific operation or all operations.

        Args:
            operation_name: Optional operation name filter

        Returns:
            Dictionary of cached metrics (last 100 calls per operation)
        """
        if not self.enabled:
            return {}

        if operation_name:
            if operation_name in self._operations:
                return self._operations[operation_name].to_dict()
            return {}

        # Return all metrics
        return {name: metrics.to_dict() for name, metrics in self._operations.items()}

    def get_metrics_sync(self, operation_name: str | None = None) -> dict[str, Any]:
        """Synchronous version of get_metrics."""
        if not self.enabled:
            return {}

        if operation_name:
            if operation_name in self._operations:
                return self._operations[operation_name].to_dict()
            return {}

        return {name: metrics.to_dict() for name, metrics in self._operations.items()}

    async def get_summary(self) -> dict[str, Any]:
        """
        Get summary of cached query metrics.

        Note: This is cache-only data (lossy). For complete metrics, query Prometheus.
        """
        if not self.enabled:
            return {
                "enabled": False,
                "cache_note": "Cache disabled. Query Prometheus for complete metrics.",
            }

        total_calls = sum(m.call_count for m in self._operations.values())
        total_errors = sum(m.error_count for m in self._operations.values())
        total_time = sum(m.total_time_ms for m in self._operations.values())

        # Get slowest operations (by average time)
        operations_by_avg_time = sorted(
            [m.to_dict() for m in self._operations.values()],
            key=_get_avg_time_ms,
            reverse=True,
        )

        uptime_seconds = (datetime.now(UTC) - self.start_time).total_seconds()

        return {
            "enabled": True,
            "cache_note": "Cache contains last 100 calls per operation. Query Prometheus for complete data.",
            "uptime_seconds": round(uptime_seconds, 2),
            "total_operations": len(self._operations),
            "total_calls": total_calls,
            "total_errors": total_errors,
            "overall_error_rate": round(
                (total_errors / total_calls * 100) if total_calls > 0 else 0.0, 2
            ),
            "total_time_ms": round(total_time, 2),
            "calls_per_second": round(total_calls / uptime_seconds, 2)
            if uptime_seconds > 0
            else 0.0,
            "slowest_operations": [
                {
                    "name": m["operation_name"],
                    "avg_time_ms": m["avg_time_ms"],
                    "call_count": m["call_count"],
                }
                for m in operations_by_avg_time[:5]
            ],
            "operations": {name: metrics.to_dict() for name, metrics in self._operations.items()},
        }

    def get_summary_sync(self) -> dict[str, Any]:
        """Synchronous version of get_summary."""
        if not self.enabled:
            return {
                "enabled": False,
                "cache_note": "Cache disabled. Query Prometheus for complete metrics.",
            }

        total_calls = sum(m.call_count for m in self._operations.values())
        total_errors = sum(m.error_count for m in self._operations.values())
        total_time = sum(m.total_time_ms for m in self._operations.values())

        operations_by_avg_time = sorted(
            [m.to_dict() for m in self._operations.values()],
            key=_get_avg_time_ms,
            reverse=True,
        )

        uptime_seconds = (datetime.now(UTC) - self.start_time).total_seconds()

        return {
            "enabled": True,
            "cache_note": "Cache contains last 100 calls per operation. Query Prometheus for complete data.",
            "uptime_seconds": round(uptime_seconds, 2),
            "total_operations": len(self._operations),
            "total_calls": total_calls,
            "total_errors": total_errors,
            "overall_error_rate": round(
                (total_errors / total_calls * 100) if total_calls > 0 else 0.0, 2
            ),
            "total_time_ms": round(total_time, 2),
            "calls_per_second": round(total_calls / uptime_seconds, 2)
            if uptime_seconds > 0
            else 0.0,
            "slowest_operations": [
                {
                    "name": m["operation_name"],
                    "avg_time_ms": m["avg_time_ms"],
                    "call_count": m["call_count"],
                }
                for m in operations_by_avg_time[:5]
            ],
            "operations": {name: metrics.to_dict() for name, metrics in self._operations.items()},
        }

    async def reset(self) -> None:
        """
        Reset cache (for testing).

        Note: This does NOT reset Prometheus metrics.
        """
        self._operations.clear()
        self.start_time = datetime.now(UTC)
        logger.info("QueryMetricsCache reset (Prometheus metrics unchanged)")

    def reset_sync(self) -> None:
        """Synchronous version of reset."""
        self._operations.clear()
        self.start_time = datetime.now(UTC)
        logger.info("QueryMetricsCache reset (Prometheus metrics unchanged)")


__all__ = ["QueryMetricsCache"]
