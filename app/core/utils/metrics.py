"""
Query Metrics Tracking
======================

Lightweight metrics collection for query performance monitoring.

Features:
- Thread-safe metrics storage
- Automatic statistics aggregation (min, max, avg, p95, p99)
- Decorator pattern for easy integration
- Zero-overhead when disabled
- Per-operation tracking

Usage:
    from core.utils.metrics import track_query_metrics, get_metrics_summary

    @track_query_metrics("get_knowledge_unit")
    async def get(self, uid: str) -> Result[KuDTO]:
        # Your code here
        ...

    # Get metrics
    summary = get_metrics_summary()
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import wraps
from threading import Lock
from typing import Any

from core.services.protocols import Result
from core.utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Metrics Storage
# ============================================================================


@dataclass
class OperationMetrics:
    """Metrics for a single operation type."""

    operation_name: str
    call_count: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float | None = None
    max_time_ms: float | None = None
    recent_times: list[float] = field(default_factory=list)  # Last 100 calls
    error_count: int = 0
    last_called: datetime | None = None

    def add_timing(self, duration_ms: float, had_error: bool = False):
        """Record a new timing measurement."""
        self.call_count += 1
        self.total_time_ms += duration_ms
        self.last_called = datetime.now(UTC)

        if had_error:
            self.error_count += 1

        # Update min/max
        if self.min_time_ms is None or duration_ms < self.min_time_ms:
            self.min_time_ms = duration_ms
        if self.max_time_ms is None or duration_ms > self.max_time_ms:
            self.max_time_ms = duration_ms

        # Keep last 100 timings for percentile calculations
        self.recent_times.append(duration_ms)
        if len(self.recent_times) > 100:
            self.recent_times.pop(0)

    @property
    def avg_time_ms(self) -> float:
        """Average execution time."""
        return self.total_time_ms / self.call_count if self.call_count > 0 else 0.0

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
        """Convert to dictionary for serialization."""
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


class MetricsStore:
    """
    Thread-safe storage for metrics data.

    Singleton pattern - one global metrics store per process.
    """

    _instance: "MetricsStore | None" = None
    _lock: Lock = Lock()
    _initialized: bool = False

    def __new__(cls) -> "MetricsStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._metrics: dict[str, OperationMetrics] = {}
        self._data_lock = Lock()
        self._enabled = True
        self._start_time = datetime.now(UTC)
        self._initialized = True

        logger.info("MetricsStore initialized")

    def record_timing(
        self, operation_name: str, duration_ms: float, had_error: bool = False
    ) -> None:
        """Record timing for an operation."""
        if not self._enabled:
            return

        with self._data_lock:
            if operation_name not in self._metrics:
                self._metrics[operation_name] = OperationMetrics(operation_name)

            self._metrics[operation_name].add_timing(duration_ms, had_error)

    def get_metrics(self, operation_name: str | None = None) -> dict[str, Any]:
        """
        Get metrics for specific operation or all operations.

        Args:
            operation_name: Optional operation name filter

        Returns:
            Dictionary of metrics
        """
        with self._data_lock:
            if operation_name:
                if operation_name in self._metrics:
                    return self._metrics[operation_name].to_dict()
                return {}

            # Return all metrics
            return {name: metrics.to_dict() for name, metrics in self._metrics.items()}

    def get_summary(self) -> dict[str, Any]:
        """Get summary of all metrics."""
        with self._data_lock:
            total_calls = sum(m.call_count for m in self._metrics.values())
            total_errors = sum(m.error_count for m in self._metrics.values())
            total_time = sum(m.total_time_ms for m in self._metrics.values())

            # Get slowest operations
            from core.utils.sort_functions import get_avg_time_ms

            operations_by_avg_time = sorted(
                self._metrics.values(), key=get_avg_time_ms, reverse=True
            )

            uptime_seconds = (datetime.now(UTC) - self._start_time).total_seconds()

            return {
                "uptime_seconds": round(uptime_seconds, 2),
                "total_operations": len(self._metrics),
                "total_calls": total_calls,
                "total_errors": total_errors,
                "overall_error_rate": round(
                    (total_errors / total_calls * 100) if total_calls > 0 else 0.0, 2
                ),
                "total_time_ms": round(total_time, 2),
                "calls_per_second": round(total_calls / uptime_seconds, 2)
                if uptime_seconds > 0
                else 0,
                "slowest_operations": [
                    {
                        "name": m.operation_name,
                        "avg_time_ms": round(m.avg_time_ms, 2),
                        "call_count": m.call_count,
                    }
                    for m in operations_by_avg_time[:5]
                ],
                "operations": {name: metrics.to_dict() for name, metrics in self._metrics.items()},
            }

    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._data_lock:
            self._metrics.clear()
            self._start_time = datetime.now(UTC)
            logger.info("Metrics reset")

    def enable(self) -> None:
        """Enable metrics collection."""
        self._enabled = True
        logger.info("Metrics enabled")

    def disable(self) -> None:
        """Disable metrics collection."""
        self._enabled = False
        logger.info("Metrics disabled")


# Global metrics store instance
_metrics_store = MetricsStore()


# ============================================================================
# Decorator for Automatic Tracking
# ============================================================================


def track_query_metrics(operation_name: str | None = None):
    """
    Decorator to automatically track query performance metrics.

    Args:
        operation_name: Optional custom operation name (defaults to function name),

    Usage:
        @track_query_metrics("get_knowledge_unit")
        async def get(self, uid: str) -> Result[KuDTO]:
            ...

        @track_query_metrics()  # Uses function name
        async def search(self, query: str):
            ...
    """

    def decorator(func: Callable) -> Callable:
        # Determine operation name
        op_name = operation_name or func.__name__

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Async function wrapper."""
            start_time = time.perf_counter()
            had_error = False

            try:
                result = await func(*args, **kwargs)

                # Check if Result pattern indicates error (Protocol-based)
                if isinstance(result, Result):
                    had_error = result.is_error

                return result

            except Exception:
                had_error = True
                raise

            finally:
                # Record timing
                duration_ms = (time.perf_counter() - start_time) * 1000
                _metrics_store.record_timing(op_name, duration_ms, had_error)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Sync function wrapper."""
            start_time = time.perf_counter()
            had_error = False

            try:
                result = func(*args, **kwargs)

                # Check if Result pattern indicates error (Protocol-based)
                if isinstance(result, Result):
                    had_error = result.is_error

                return result

            except Exception:
                had_error = True
                raise

            finally:
                # Record timing
                duration_ms = (time.perf_counter() - start_time) * 1000
                _metrics_store.record_timing(op_name, duration_ms, had_error)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ============================================================================
# Public API
# ============================================================================


def get_metrics(operation_name: str | None = None) -> dict[str, Any]:
    """
    Get metrics for specific operation or all operations.

    Args:
        operation_name: Optional operation name filter,

    Returns:
        Dictionary of metrics data
    """
    return _metrics_store.get_metrics(operation_name)


def get_metrics_summary() -> dict[str, Any]:
    """
    Get summary of all collected metrics.

    Returns:
        Dictionary with:
        - uptime_seconds: Time since metrics started
        - total_operations: Number of unique operations tracked
        - total_calls: Total number of calls across all operations
        - total_errors: Total errors across all operations
        - overall_error_rate: Percentage of calls that errored
        - slowest_operations: Top 5 slowest operations by average time
        - operations: Detailed metrics for each operation
    """
    return _metrics_store.get_summary()


def reset_metrics():
    """Reset all metrics data. Useful for testing."""
    _metrics_store.reset()


def enable_metrics():
    """Enable metrics collection."""
    _metrics_store.enable()


def disable_metrics():
    """Disable metrics collection."""
    _metrics_store.disable()


# ============================================================================
# Context Manager for Manual Timing
# ============================================================================


class MetricsTimer:
    """
    Context manager for manual timing of operations.

    Usage:
        with MetricsTimer("custom_operation"):
            # Your code here
            process_data()
    """

    def __init__(self, operation_name: str) -> None:
        self.operation_name = operation_name
        self.start_time: float | None = None
        self.had_error = False

    def __enter__(self) -> "MetricsTimer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # start_time guaranteed to be set by __enter__ (context manager contract)
        if self.start_time is None:
            return  # Should never happen in proper context manager use
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        had_error = exc_type is not None
        _metrics_store.record_timing(self.operation_name, duration_ms, had_error)
        # Don't suppress exceptions (return None or False)


# Export public API
__all__ = [
    "MetricsTimer",
    "OperationMetrics",
    "disable_metrics",
    "enable_metrics",
    "get_metrics",
    "get_metrics_summary",
    "reset_metrics",
    "track_query_metrics",
]
