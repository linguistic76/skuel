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

- January 2026 (Option D Pattern for Query Metrics)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypedDict, cast

from core.utils.logging import get_logger

logger = get_logger(__name__)


class OperationMetricsDict(TypedDict):
    """Typed shape returned by CachedOperationMetrics.to_dict()."""

    operation_name: str
    call_count: int
    total_time_ms: float
    avg_time_ms: float
    min_time_ms: float | None
    max_time_ms: float | None
    p95_time_ms: float | None
    p99_time_ms: float | None
    error_count: int
    error_rate: float
    last_called: str | None


class SlowOperationSummary(TypedDict):
    """One entry in the slowest_operations list."""

    name: str
    avg_time_ms: float
    call_count: int


class QueryMetricsSummaryDict(TypedDict, total=False):
    """Shape returned by QueryMetricsCache._get_summary().

    total=False: disabled case populates only enabled + cache_note;
    enabled case populates all fields.
    """

    enabled: bool
    cache_note: str
    uptime_seconds: float
    total_operations: int
    total_calls: int
    total_errors: int
    overall_error_rate: float
    total_time_ms: float
    calls_per_second: float
    slowest_operations: list[SlowOperationSummary]
    operations: dict[str, OperationMetricsDict]


# Helper functions
def _create_deque_100() -> deque[float]:
    """Create deque with maxlen=100 for recent timing tracking."""
    return deque(maxlen=100)


def _get_avg_time_ms(metrics_dict: OperationMetricsDict) -> float:
    """Get avg_time_ms from metrics dict for sorting."""
    return metrics_dict["avg_time_ms"]


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

    def to_dict(self) -> OperationMetricsDict:
        """Convert to dictionary for debugging."""
        return OperationMetricsDict(
            operation_name=self.operation_name,
            call_count=self.call_count,
            total_time_ms=round(self.total_time_ms, 2),
            avg_time_ms=round(self.avg_time_ms, 2),
            min_time_ms=round(self.min_time_ms, 2) if self.min_time_ms else None,
            max_time_ms=round(self.max_time_ms, 2) if self.max_time_ms else None,
            p95_time_ms=round(self.p95_time_ms, 2) if self.p95_time_ms else None,
            p99_time_ms=round(self.p99_time_ms, 2) if self.p99_time_ms else None,
            error_count=self.error_count,
            error_rate=round(self.error_rate, 2),
            last_called=self.last_called.isoformat() if self.last_called else None,
        )


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

    def record_timing(
        self, operation_name: str, duration_ms: float, had_error: bool = False
    ) -> None:
        """
        Record timing for an operation.

        Writes to Prometheus (source of truth) and updates cache (debugging).
        Synchronous — the Prometheus client is thread-safe and the cache is
        in-memory, so async and sync contexts share this one method.

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

    def _get_one_metric(self, operation_name: str) -> OperationMetricsDict | None:
        """Return metrics for a single operation, or None if disabled / not found."""
        if not self.enabled:
            return None
        op = self._operations.get(operation_name)
        return op.to_dict() if op else None

    def _get_all_metrics(self) -> dict[str, OperationMetricsDict]:
        """Return metrics for every tracked operation, or {} if disabled."""
        if not self.enabled:
            return {}
        return {name: m.to_dict() for name, m in self._operations.items()}

    def get_metrics(self, operation_name: str | None = None) -> dict[str, Any]:
        """Get cached metrics for specific operation or all operations."""
        if operation_name is not None:
            result = self._get_one_metric(operation_name)
            return (
                cast("dict[str, Any]", result) if result is not None else {}
            )  # boundary: public-api — callers in metrics.py expect dict[str, Any]
        return self._get_all_metrics()

    def get_summary(self) -> QueryMetricsSummaryDict:
        """Get summary of cached query metrics."""
        if not self.enabled:
            return QueryMetricsSummaryDict(
                enabled=False,
                cache_note="Cache disabled. Query Prometheus for complete metrics.",
            )

        total_calls = sum(m.call_count for m in self._operations.values())
        total_errors = sum(m.error_count for m in self._operations.values())
        total_time = sum(m.total_time_ms for m in self._operations.values())
        uptime_seconds = (datetime.now(UTC) - self.start_time).total_seconds()

        operations_by_avg_time = sorted(
            [m.to_dict() for m in self._operations.values()],
            key=_get_avg_time_ms,
            reverse=True,
        )

        return QueryMetricsSummaryDict(
            enabled=True,
            cache_note="Cache contains last 100 calls per operation. Query Prometheus for complete data.",
            uptime_seconds=round(uptime_seconds, 2),
            total_operations=len(self._operations),
            total_calls=total_calls,
            total_errors=total_errors,
            overall_error_rate=round(
                (total_errors / total_calls * 100) if total_calls > 0 else 0.0, 2
            ),
            total_time_ms=round(total_time, 2),
            calls_per_second=round(total_calls / uptime_seconds, 2) if uptime_seconds > 0 else 0.0,
            slowest_operations=[
                SlowOperationSummary(
                    name=m["operation_name"],
                    avg_time_ms=m["avg_time_ms"],
                    call_count=m["call_count"],
                )
                for m in operations_by_avg_time[:5]
            ],
            operations=self._get_all_metrics(),
        )

    def reset(self) -> None:
        """Reset cache (for testing). Does NOT reset Prometheus metrics."""
        self._operations.clear()
        self.start_time = datetime.now(UTC)
        logger.info("QueryMetricsCache reset (Prometheus metrics unchanged)")


__all__ = [
    "OperationMetricsDict",
    "QueryMetricsCache",
    "QueryMetricsSummaryDict",
    "SlowOperationSummary",
]
