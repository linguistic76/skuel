"""
Query Metrics Tracking - Prometheus First
==========================================

Metrics collection for query performance monitoring using Prometheus as primary source.

Replaces in-memory MetricsStore with QueryMetricsCache (Prometheus + in-memory cache).

Features:
- Prometheus as source of truth (production monitoring)
- In-memory cache for debugging (last 100 calls per operation)
- Thread-safe metrics storage
- Automatic statistics aggregation (min, max, avg, p95, p99)
- Decorator pattern for easy integration
- Compatible API with legacy MetricsStore

Usage:
    from core.utils.metrics import track_query_metrics, get_metrics_summary

    @track_query_metrics("get_knowledge_unit")
    async def get(self, uid: str) -> Result[KuDTO]:
        # Your code here
        ...

    # Get metrics
    summary = get_metrics_summary()

Phase 3.6 - January 2026 (Prometheus-first migration)
"""

import asyncio
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from core.ports import Result
from core.utils.logging import get_logger

logger = get_logger(__name__)

# ============================================================================
# Global Query Metrics Cache Instance
# ============================================================================

# Global query metrics cache (set during bootstrap)
_query_metrics_cache: Any = None  # Will be QueryMetricsCache instance


def set_query_metrics_cache(cache: Any) -> None:
    """
    Set global query metrics cache instance.

    Called during bootstrap to wire QueryMetricsCache.

    Args:
        cache: QueryMetricsCache instance
    """
    global _query_metrics_cache
    _query_metrics_cache = cache
    logger.info("Global query metrics cache set")


def get_query_metrics_cache() -> Any:
    """Get global query metrics cache instance."""
    return _query_metrics_cache


# ============================================================================
# Decorator for Automatic Tracking
# ============================================================================


def track_query_metrics(operation_name: str | None = None):
    """
    Decorator to automatically track query performance metrics.

    Writes to Prometheus (source of truth) and in-memory cache (debugging).

    Args:
        operation_name: Optional custom operation name (defaults to function name)

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
                if _query_metrics_cache:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    await _query_metrics_cache.record_timing(op_name, duration_ms, had_error)

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
                if _query_metrics_cache:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    _query_metrics_cache.record_timing_sync(op_name, duration_ms, had_error)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ============================================================================
# Public API (Compatible with Legacy MetricsStore)
# ============================================================================


def get_metrics(operation_name: str | None = None) -> dict[str, Any]:
    """
    Get cached metrics for specific operation or all operations.

    Args:
        operation_name: Optional operation name filter

    Returns:
        Dictionary of cached metrics data (last 100 calls per operation)
    """
    if not _query_metrics_cache:
        return {}
    return _query_metrics_cache.get_metrics_sync(operation_name)


def get_metrics_summary() -> dict[str, Any]:
    """
    Get summary of all collected metrics from cache.

    Note: This returns cache data (last 100 calls per operation).
    For complete metrics, query Prometheus.

    Returns:
        Dictionary with:
        - uptime_seconds: Time since metrics started
        - total_operations: Number of unique operations tracked
        - total_calls: Total number of calls (in cache)
        - total_errors: Total errors (in cache)
        - overall_error_rate: Percentage of calls that errored
        - slowest_operations: Top 5 slowest operations by average time
        - operations: Detailed metrics for each operation
        - cache_note: Reminder that data is from cache
    """
    if not _query_metrics_cache:
        return {
            "enabled": False,
            "cache_note": "Query metrics cache not initialized. Call set_query_metrics_cache() during bootstrap.",
        }
    return _query_metrics_cache.get_summary_sync()


def reset_metrics():
    """
    Reset cached metrics data.

    Note: This does NOT reset Prometheus metrics (they persist).
    Useful for testing.
    """
    if _query_metrics_cache:
        _query_metrics_cache.reset_sync()


def enable_metrics():
    """
    Enable metrics collection.

    Note: Prometheus metrics are always collected. This only affects cache.
    """
    if _query_metrics_cache:
        _query_metrics_cache.enabled = True
        logger.info("Query metrics cache enabled")


def disable_metrics():
    """
    Disable metrics collection.

    Note: Prometheus metrics are still collected. This only disables cache.
    """
    if _query_metrics_cache:
        _query_metrics_cache.enabled = False
        logger.info("Query metrics cache disabled")


# ============================================================================
# Context Manager for Manual Timing
# ============================================================================


class MetricsTimer:
    """
    Context manager for manual timing of operations.

    Writes to Prometheus and cache.

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

        if _query_metrics_cache:
            duration_ms = (time.perf_counter() - self.start_time) * 1000
            had_error = exc_type is not None
            _query_metrics_cache.record_timing_sync(self.operation_name, duration_ms, had_error)
        # Don't suppress exceptions (return None or False)


# Export public API (backward-compatible)
__all__ = [
    "MetricsTimer",
    "disable_metrics",
    "enable_metrics",
    "get_metrics",
    "get_metrics_summary",
    "reset_metrics",
    "set_query_metrics_cache",
    "track_query_metrics",
]
